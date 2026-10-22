import os, shlex, shutil, subprocess
from pathlib import Path
from config import Config

EXIT_WRAPPER = 'ef="$1"; shift; "$@"; echo $? > "$ef"'

def project_src(p): return Config.PROJECTS_DIR / str(p.owner_id) / str(p.id)
def venv_dir(p): return Config.VENVS_DIR / str(p.id)
def venv_python(p): return venv_dir(p) / "bin" / "python"
def log_path(p): return Config.LOGS_DIR / f"{p.id}.log"
def exit_path(p): return Config.RUNTIME_DIR / f"{p.id}.exit"
def fifo_path(p): return Config.RUNTIME_DIR / f"{p.id}.stdin"

def docker_available():
    if not shutil.which(Config.DOCKER_BIN): return False, "docker not found"
    try:
        r = subprocess.run([Config.DOCKER_BIN, "info", "--format", "{{.ServerVersion}}"],
                           capture_output=True, text=True, timeout=15)
        return (r.returncode == 0, r.stderr.strip() or "ok")
    except Exception as e:
        return False, str(e)

def _client_env():
    drop = {"SECRET_KEY","ENCRYPTION_KEY","ADMIN_EMAIL","DATABASE_URL"}
    return {k:v for k,v in os.environ.items() if k not in drop}

def _docker_base(p, name, interactive, venv_rw, envfile=None, tmp="256m"):
    uid = os.getuid() if hasattr(os,"getuid") else 1000
    gid = os.getgid() if hasattr(os,"getgid") else 1000
    a = [Config.DOCKER_BIN, "run", "--rm"]
    if interactive: a.append("-i")
    if name: a += ["--name", name]
    a += ["--label","glory=1","--user",f"{uid}:{gid}",
          "--memory",f"{Config.PROJECT_MEM_MB}m","--memory-swap",f"{Config.PROJECT_MEM_MB}m",
          "--cpus",str(Config.PROJECT_CPUS),"--pids-limit",str(Config.PROJECT_PIDS),
          "--cap-drop","ALL","--security-opt","no-new-privileges","--read-only",
          "--tmpfs",f"/tmp:rw,size={tmp},mode=1777",
          "--network",Config.DOCKER_NETWORK,
          "-e","HOME=/tmp","-e","PYTHONUNBUFFERED=1",
          "-v",f"{project_src(p)}:/app",
          "-v",f"{venv_dir(p)}:/venv{'' if venv_rw else ':ro'}",
          "-w","/app"]
    if envfile: a += ["--env-file", str(envfile)]
    return a

def build_run(p, envvars):
    startup = p.startup
    exitf = str(exit_path(p))
    image = p.image or Config.DOCKER_IMAGE
    if Config.SANDBOX_MODE == "docker":
        envfile = None
        if envvars:
            envfile = Config.RUNTIME_DIR / f"{p.id}.env"
            fd = os.open(envfile, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd,"w") as f:
                for k,v in envvars.items(): f.write(f"{k}={v}\n")
        argv = _docker_base(p, f"glory-{p.id}", True, False, envfile) + \
               [image, "/venv/bin/python", "-u", f"/app/{startup}"]
        if p.args: argv += shlex.split(p.args)
        return ["/bin/sh","-c",EXIT_WRAPPER,"sh",exitf]+argv, _client_env(), None, envfile
    argv = [str(venv_python(p)), "-u", startup]
    if p.args: argv += shlex.split(p.args)
    return (["/bin/sh","-c",EXIT_WRAPPER,"sh",exitf]+argv,
            {"PATH":f"{venv_dir(p)}/bin:/usr/local/bin:/usr/bin:/bin",
             "HOME":str(project_src(p)),"PYTHONUNBUFFERED":"1",**envvars}, None, None)

def build_pip(p, args):
    image = p.image or Config.DOCKER_IMAGE
    if Config.SANDBOX_MODE == "docker":
        name = f"glorypip-{p.id}-{os.getpid()}"
        return _docker_base(p, name, False, True, tmp="1g") + \
               [image, "/venv/bin/python", "-m", "pip", *args,
                "--disable-pip-version-check"], _client_env(), name
    return [str(venv_python(p)), "-m", "pip", *args, "--disable-pip-version-check"], \
           _client_env(), None

def build_venv(p):
    image = p.image or Config.DOCKER_IMAGE
    if Config.SANDBOX_MODE == "docker":
        return _docker_base(p, None, False, True) + \
               [image, "python", "-m", "venv", "/venv"], _client_env()
    return [os.sys.executable, "-m", "venv", str(venv_dir(p))], _client_env()