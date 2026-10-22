import asyncio, errno, os, signal, stat, subprocess, threading, time
import psutil
from config import Config
from database import db, Project
from services import sandbox
from services.logs import LOGS

class ProcessManager:
    def __init__(self):
        self.popens = {}
        self.locks = {}
        self.pending = []
        self._lock = threading.RLock()

    def lock(self, pid):
        with self._lock:
            return self.locks.setdefault(pid, threading.RLock())

    def is_alive(self, p):
        po = self.popens.get(p.id)
        if po is not None and po.pid == p.pid:
            return po.poll() is None
        if not p.pid: return False
        try:
            pr = psutil.Process(p.pid)
            if p.pid_ctime and abs(pr.create_time() - p.pid_ctime) > 1.5: return False
            return pr.status() != psutil.STATUS_ZOMBIE
        except psutil.Error:
            return False

    def fresh(self, pid):
        p = db.session.get(Project, pid)
        if p and p.status == "running" and not self.is_alive(p):
            return self.finalize(pid)
        return p

    def read_exit(self, p):
        try: return int(sandbox.exit_path(p).read_text().strip())
        except (OSError, ValueError): return None

    def finalize(self, pid, expected=False, forced_code=None, notify=True):
        p = db.session.get(Project, pid)
        if not p or p.status != "running": return p
        code = self.read_exit(p)
        po = self.popens.pop(pid, None)
        if code is None and po is not None and po.poll() is not None:
            code = po.returncode
        if code is None: code = forced_code
        status = "stopped" if (expected or code == 0) else "crashed"
        p.status = status; p.ended_at = time.time(); p.exit_code = code
        p.pid = None; p.pid_ctime = None
        if status == "stopped": p.desired = False
        else: p.crash_count = (p.crash_count or 0) + 1
        db.session.commit()
        LOGS.marker(p, f"process {status}, exit {code}")
        if not expected and notify: self.pending.append(pid)
        return p

    def start(self, p, manual=True):
        with self.lock(p.id):
            db.session.refresh(p)
            if self.is_alive(p): return False, "Already running."
            if p.status == "running": self.finalize(p.id, notify=False)
            if not p.startup: return False, "No startup file set."
            if Config.SANDBOX_MODE != "docker" and not Config.ALLOW_UNSANDBOXED_USERS:
                return False, "Unsandboxed mode disabled."
            src = sandbox.project_src(p)
            target = src / p.startup
            if not target.is_file(): return False, f"Startup not found: {p.startup}"
            ok, msg = _ensure_venv(p)
            if not ok: return False, "venv: " + msg
            if Config.SANDBOX_MODE == "docker":
                subprocess.run([Config.DOCKER_BIN,"rm","-f",f"glory-{p.id}"],
                               capture_output=True, timeout=30)
            try: sandbox.exit_path(p).unlink()
            except OSError: pass
            fifo = sandbox.fifo_path(p)
            try:
                if fifo.exists() and not stat.S_ISFIFO(fifo.stat().st_mode): fifo.unlink()
                if not fifo.exists(): os.mkfifo(fifo, 0o600)
            except OSError as e: return False, f"fifo: {e}"
            envvars = {r.key: __import__("security").dec(r.value_enc)
                       for r in p.__dict__ if False}  # replaced below
            from database import EnvVar
            envvars = {r.key: __import__("security").dec(r.value_enc)
                       for r in EnvVar.query.filter_by(project_id=p.id).all()}
            cmd, env, preexec, envfile = sandbox.build_run(p, envvars)
            LOGS.marker(p, f"starting {p.startup} ({Config.SANDBOX_MODE})")
            fd = os.open(fifo, os.O_RDWR)
            logf = open(sandbox.log_path(p), "ab", buffering=0)
            try:
                proc = subprocess.Popen(cmd, stdin=fd, stdout=logf, stderr=subprocess.STDOUT,
                                        cwd=str(src), env=env, start_new_session=True,
                                        close_fds=True, preexec_fn=preexec)
            except OSError as e:
                LOGS.marker(p, f"launch failed: {e}")
                return False, f"launch: {e}"
            finally:
                os.close(fd); logf.close()
            try: ctime = psutil.Process(proc.pid).create_time()
            except psutil.Error: ctime = time.time()
            self.popens[p.id] = proc
            p.status = "running"; p.pid = proc.pid; p.pid_ctime = ctime
            p.started_at = time.time(); p.ended_at = None; p.exit_code = None
            p.desired = True
            p.container = f"glory-{p.id}" if Config.SANDBOX_MODE == "docker" else None
            if manual: p.restart_count = 0
            db.session.commit()
            if envfile:
                threading.Timer(15, lambda: envfile.unlink(missing_ok=True)).start()
            time.sleep(1.5)
            if proc.poll() is not None:
                self.finalize(p.id, notify=False)
                err = LOGS.last_error(p) or "\n".join(LOGS.tail_lines(p, 3))
                return False, f"Exited immediately ({proc.returncode}).\n{err}"
            return True, f"Started (PID {proc.pid})."

    def stop(self, p, force=False):
        with self.lock(p.id):
            db.session.refresh(p)
            p.desired = False; db.session.commit()
            if not self.is_alive(p):
                if p.status == "running": self.finalize(p.id, notify=False)
                return False, "Not running."
            pid, ctime = p.pid, p.pid_ctime
            if Config.SANDBOX_MODE == "docker" and p.container:
                subprocess.run([Config.DOCKER_BIN, "kill" if force else "stop",
                                *([] if force else ["-t","10"]), p.container],
                               capture_output=True, timeout=40)
            sig = signal.SIGKILL if force else signal.SIGTERM
            try: os.killpg(pid, sig)
            except OSError: pass
            deadline = time.time() + (3 if force else 12)
            while time.time() < deadline and self.is_alive(p):
                time.sleep(0.25)
            if self.is_alive(p):
                try: os.killpg(pid, signal.SIGKILL)
                except OSError: pass
                time.sleep(0.5)
            self.finalize(p.id, expected=True,
                          forced_code=-int(signal.SIGKILL if force else signal.SIGTERM))
            if Config.SANDBOX_MODE == "docker":
                subprocess.run([Config.DOCKER_BIN,"rm","-f",f"glory-{p.id}"],
                               capture_output=True, timeout=20)
            return True, "Killed." if force else "Stopped."

    def restart(self, p):
        if self.is_alive(p): self.stop(p)
        return self.start(p)

    def write_stdin(self, p, text):
        if not self.is_alive(p): return False, "Not running."
        fifo = sandbox.fifo_path(p)
        if not fifo.exists(): return False, "stdin pipe missing (restart)."
        try: fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
        except OSError as e:
            return False, "no reader." if e.errno == errno.ENXIO else str(e)
        try:
            n = os.write(fd, (text + "\n").encode())
        except BlockingIOError:
            return False, "pipe full."
        finally: os.close(fd)
        LOGS.marker(p, f"{n} bytes to stdin")
        return True, f"{n} bytes written."

def _ensure_venv(p):
    if os.path.lexists(sandbox.venv_python(p)): return True, "ok"
    import shutil
    shutil.rmtree(sandbox.venv_dir(p), ignore_errors=True)
    sandbox.venv_dir(p).mkdir(parents=True, exist_ok=True)
    cmd, env = sandbox.build_venv(p)
    r = subprocess.run(cmd, cwd=str(sandbox.project_src(p)), env=env,
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0 or not os.path.lexists(sandbox.venv_python(p)):
        shutil.rmtree(sandbox.venv_dir(p), ignore_errors=True)
        return False, (r.stdout + r.stderr)[-1500:]
    return True, "ok"

PM = ProcessManager()