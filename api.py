import os, json, shutil, tempfile, threading, time
from pathlib import Path
from flask import Blueprint, request, jsonify, Response, stream_with_context, send_file, g
from auth import login_required, current_user
from config import Config
from database import db, Project, EnvVar, Backup, AuditLog
from services import sandbox, files as FS, monitoring, backups as BK
from services.archive import safe_extract, ZipError
from services.process_manager import PM
from services.packages import PKG
from services.logs import LOGS

api = Blueprint("api", __name__, url_prefix="/api")

def _own(pid):
    u = current_user()
    p = db.session.get(Project, int(pid))
    if not p: return None, (jsonify({"error":"not found"}), 404)
    if p.owner_id != u.id and not u.is_admin:
        return None, (jsonify({"error":"forbidden"}), 403)
    return PM.fresh(pid) or p, None

def _audit(action, detail=""):
    u = current_user()
    db.session.add(AuditLog(user_id=u.id if u else None, action=action,
                            detail=detail, ip=request.remote_addr))
    db.session.commit()

# ---------- dashboard / system ----------
@api.get("/dashboard/stats")
@login_required
def stats():
    u = current_user()
    projs = [PM.fresh(r.id) or r for r in Project.query.filter_by(owner_id=u.id).all()]
    from collections import Counter
    c = Counter(p.status for p in projs)
    return jsonify({
        "projects": {"total": len(projs), "running": c["running"],
                     "stopped": c["stopped"], "crashed": c["crashed"], "new": c["new"]},
        "host": monitoring.host_stats(),
        "limits": {"max_projects": u.max_projects or Config.MAX_PROJECTS_PER_USER,
                   "mem_mb": Config.PROJECT_MEM_MB, "cpus": Config.PROJECT_CPUS},
    })

@api.get("/system/health")
@login_required
def health():
    ok, msg = sandbox.docker_available() if Config.SANDBOX_MODE == "docker" else (True, "process mode")
    return jsonify({"sandbox_mode": Config.SANDBOX_MODE, "docker": {"available": ok, "message": msg}})

# ---------- projects ----------
@api.get("/projects")
@login_required
def list_projects():
    u = current_user()
    projs = [PM.fresh(r.id) or r for r in Project.query.filter_by(owner_id=u.id).all()]
    return jsonify([_proj_json(p) for p in projs])

def _proj_json(p):
    return {"id": p.id, "name": p.name, "startup": p.startup, "args": p.args,
            "status": p.status, "exit_code": p.exit_code, "pid": p.pid,
            "uptime": (time.time() - p.started_at) if p.status == "running" and p.started_at else 0,
            "auto_restart": p.auto_restart, "restart_every_h": p.restart_every_h,
            "restart_count": p.restart_count, "crash_count": p.crash_count}

@api.post("/projects")
@login_required
def create_project():
    u = current_user()
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()[:60]
    if not name or not name.replace("_","").replace("-","").replace(" ","").isalnum():
        return jsonify({"error":"Invalid project name"}), 400
    limit = u.max_projects if u.max_projects is not None else Config.MAX_PROJECTS_PER_USER
    if Project.query.filter_by(owner_id=u.id).count() >= limit:
        return jsonify({"error":f"Project limit reached ({limit})"}), 400
    if Project.query.filter_by(owner_id=u.id, name=name).first():
        return jsonify({"error":"Project name already used"}), 409
    p = Project(owner_id=u.id, name=name, sandbox=Config.SANDBOX_MODE,
                auto_restart=bool(data.get("auto_restart", True)))
    db.session.add(p); db.session.commit()
    sandbox.project_src(p).mkdir(parents=True, exist_ok=True)
    _audit("project.create", f"{p.id} {name}")
    return jsonify(_proj_json(p)), 201

@api.get("/projects/<int:pid>")
@login_required
def get_project(pid):
    p, err = _own(pid)
    if err: return err
    data = _proj_json(p)
    data["usage"] = monitoring.project_usage(p) if p.status == "running" else {"cpu":"-","mem":"-"}
    data["last_error"] = LOGS.last_error(p)
    data["files"] = [f for f in os.listdir(sandbox.project_src(p))] if sandbox.project_src(p).exists() else []
    data["requirements"] = (sandbox.project_src(p) / "requirements.txt").exists()
    return jsonify(data)

@api.delete("/projects/<int:pid>")
@login_required
def delete_project(pid):
    p, err = _own(pid)
    if err: return err
    PM.stop(p, force=True)
    src = sandbox.project_src(p)
    if src.exists():
        BK.create(p)
        shutil.rmtree(src, ignore_errors=True)
    shutil.rmtree(sandbox.venv_dir(p), ignore_errors=True)
    for f in (sandbox.log_path(p), sandbox.exit_path(p), sandbox.fifo_path(p)):
        try: f.unlink()
        except OSError: pass
    db.session.delete(p); db.session.commit()
    _audit("project.delete", str(pid))
    return jsonify({"ok": True})

# ---------- lifecycle ----------
@api.post("/projects/<int:pid>/start")
@login_required
def start(pid):
    p, err = _own(pid)
    if err: return err
    ok, msg = PM.start(p)
    _audit("project.start", f"{pid} {ok}")
    return jsonify({"ok": ok, "message": msg}), 200 if ok else 400

@api.post("/projects/<int:pid>/stop")
@login_required
def stop(pid):
    p, err = _own(pid)
    if err: return err
    ok, msg = PM.stop(p)
    _audit("project.stop", f"{pid} {ok}")
    return jsonify({"ok": ok, "message": msg})

@api.post("/projects/<int:pid>/restart")
@login_required
def restart(pid):
    p, err = _own(pid)
    if err: return err
    ok, msg = PM.restart(p)
    _audit("project.restart", f"{pid} {ok}")
    return jsonify({"ok": ok, "message": msg})

@api.patch("/projects/<int:pid>")
@login_required
def update_project(pid):
    p, err = _own(pid)
    if err: return err
    d = request.get_json() or {}
    if "startup" in d:
        rel = (d["startup"] or "").strip()
        if rel:
            target = FS.safe_join(sandbox.project_src(p), rel)
            if not target.is_file() or not rel.endswith(".py"):
                return jsonify({"error":"Startup must be an existing .py inside project"}), 400
        p.startup = rel or None
    if "args" in d: p.args = (d["args"] or "").strip()[:500] or None
    if "auto_restart" in d: p.auto_restart = bool(d["auto_restart"])
    if "restart_every_h" in d:
        try: p.restart_every_h = int(d["restart_every_h"])
        except: pass
    db.session.commit()
    return jsonify(_proj_json(p))

# ---------- uploads (ZIP or single .py) ----------
@api.post("/projects/<int:pid>/upload")
@login_required
def upload(pid):
    p, err = _own(pid)
    if err: return err
    f = request.files.get("file")
    if not f: return jsonify({"error":"No file"}), 400
    name = os.path.basename((f.filename or "").replace("\\","/"))
    if not name: return jsonify({"error":"Bad filename"}), 400
    src = sandbox.project_src(p); src.mkdir(parents=True, exist_ok=True)
    tmp = Config.TMP_DIR / f"up_{p.id}_{int(time.time()*1000)}"
    f.save(tmp)
    try:
        if name.lower().endswith(".zip"):
            prog = {}
            n = safe_extract(tmp, src, prog)
            # detect startup
            for c in ("app.py","main.py","bot.py","run.py","start.py"):
                if (src / c).is_file(): p.startup = c; break
            if not p.startup:
                pys = [x.name for x in src.iterdir() if x.suffix == ".py"]
                if len(pys) == 1: p.startup = pys[0]
            db.session.commit()
            return jsonify({"ok": True, "files": n, "startup": p.startup,
                            "requirements": (src/"requirements.txt").exists()})
        if name.lower().endswith(".py"):
            shutil.move(str(tmp), src / name)
            os.chmod(src / name, 0o644)
            if not p.startup: p.startup = name
            db.session.commit()
            return jsonify({"ok": True, "startup": p.startup})
        return jsonify({"error":"Only .zip or .py allowed"}), 400
    except ZipError as e:
        return jsonify({"error":f"Archive refused: {e}"}), 400
    finally:
        tmp.unlink(missing_ok=True)

# ---------- logs + SSE ----------
@api.get("/projects/<int:pid>/logs")
@login_required
def logs_tail(pid):
    p, err = _own(pid)
    if err: return err
    n = min(int(request.args.get("n", 200)), 5000)
    return jsonify({"status": p.status, "lines": LOGS.tail_lines(p, n),
                    "exit_code": p.exit_code})

@api.get("/projects/<int:pid>/logs/download")
@login_required
def logs_download(pid):
    p, err = _own(pid)
    if err: return err
    path = LOGS.path(p)
    if not path.exists(): return jsonify({"error":"No logs"}), 404
    return send_file(path, as_attachment=True, download_name=f"{p.name}_logs.txt")

@api.get("/projects/<int:pid>/logs/stream")
@login_required
def logs_stream(pid):
    p, err = _own(pid)
    if err: return err
    def gen():
        sent = 0
        while True:
            p2 = db.session.get(Project, pid)
            if not p2: break
            lines = LOGS.tail_lines(p2, 1000)
            if len(lines) > sent:
                chunk = "\n".join(lines[sent:])
                sent = len(lines)
                yield f"data: {json.dumps({'lines': chunk})}\n\n"
            else:
                yield "event: ping\ndata: {}\n\n"
            time.sleep(1.0)
            if p2.status != "running" and len(lines) == sent:
                yield f"event: end\ndata: {json.dumps({'status': p2.status})}\n\n"
                return
    return Response(stream_with_context(gen()), mimetype="text/event-stream",
                    headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

@api.post("/projects/<int:pid>/console/input")
@login_required
def console_input(pid):
    p, err = _own(pid)
    if err: return err
    text = (request.get_json() or {}).get("text") or ""
    if not text or len(text) > 1000: return jsonify({"error":"Bad input"}), 400
    ok, msg = PM.write_stdin(p, text)
    return jsonify({"ok": ok, "message": msg}), 200 if ok else 400

# ---------- packages ----------
@api.get("/projects/<int:pid>/packages")
@login_required
def pkg_list(pid):
    p, err = _own(pid)
    if err: return err
    rc, out = PKG.install(p, ["list", "--format=columns"])
    pkgs = []
    for line in out.splitlines()[2:]:
        parts = line.split()
        if len(parts) >= 2: pkgs.append({"name": parts[0], "version": parts[1]})
    return jsonify({"returncode": rc, "packages": pkgs, "raw": out[-2000:]})

@api.post("/projects/<int:pid>/packages/install")
@login_required
def pkg_install(pid):
    p, err = _own(pid)
    if err: return err
    d = request.get_json() or {}
    op = d.get("op", "install")
    try:
        if d.get("requirements"):
            req = FS.safe_join(sandbox.project_src(p), "requirements.txt")
            if not req.is_file(): return jsonify({"error":"requirements.txt not found"}), 400
            args = ["install","--progress-bar","off","-r","requirements.txt"]
        else:
            pkgs = PKG.parse(d.get("packages",""), op)
            if op == "install": args = ["install","--progress-bar","off",*pkgs]
            elif op == "upgrade": args = ["install","--upgrade","--progress-bar","off",*pkgs]
            elif op == "uninstall": args = ["uninstall","-y",*pkgs]
            else: return jsonify({"error":"Bad op"}), 400
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    rc, out = PKG.install(p, args)
    _audit("pkg."+op, f"{pid} rc={rc}")
    return jsonify({"ok": rc == 0, "returncode": rc, "output": out})

# ---------- files ----------
@api.get("/projects/<int:pid>/files")
@login_required
def fm_list(pid):
    p, err = _own(pid)
    if err: return err
    rel = request.args.get("path","")
    src = sandbox.project_src(p)
    try:
        path = FS.safe_join(src, rel)
    except ValueError: return jsonify({"error":"Bad path"}), 400
    if not path.is_dir(): return jsonify({"error":"Not a directory"}), 400
    return jsonify({"path": rel, "items": FS.list_dir(path, src)})

@api.get("/projects/<int:pid>/files/read")
@login_required
def fm_read(pid):
    p, err = _own(pid)
    if err: return err
    rel = request.args.get("path","")
    try: path = FS.safe_join(sandbox.project_src(p), rel)
    except ValueError: return jsonify({"error":"Bad path"}), 400
    if not path.is_file(): return jsonify({"error":"Not a file"}), 400
    if path.stat().st_size > 1_000_000: return jsonify({"error":"File too large (>1MB)"}), 400
    raw = path.read_bytes()
    if b"\x00" in raw[:2048]: return jsonify({"error":"Binary file"}), 400
    return jsonify({"path": rel, "content": raw.decode("utf-8","replace")})

@api.put("/projects/<int:pid>/files/write")
@login_required
def fm_write(pid):
    p, err = _own(pid)
    if err: return err
    d = request.get_json() or {}
    try: path = FS.safe_join(sandbox.project_src(p), d.get("path",""))
    except ValueError: return jsonify({"error":"Bad path"}), 400
    if not path.is_file(): return jsonify({"error":"Not a file"}), 400
    path.write_text(d.get("content",""), encoding="utf-8")
    return jsonify({"ok": True})

@api.post("/projects/<int:pid>/files/mkdir")
@login_required
def fm_mkdir(pid):
    p, err = _own(pid); 
    if err: return err
    d = request.get_json() or {}
    try: path = FS.safe_join(sandbox.project_src(p), d.get("path",""))
    except ValueError: return jsonify({"error":"Bad path"}), 400
    path.mkdir(parents=False, exist_ok=False)
    return jsonify({"ok": True})

@api.post("/projects/<int:pid>/files/upload")
@login_required
def fm_upload(pid):
    p, err = _own(pid)
    if err: return err
    rel = request.form.get("path","")
    f = request.files.get("file")
    if not f: return jsonify({"error":"No file"}), 400
    try: folder = FS.safe_join(sandbox.project_src(p), rel)
    except ValueError: return jsonify({"error":"Bad path"}), 400
    name = os.path.basename((f.filename or "upload").replace("\\","/"))
    if not name: return jsonify({"error":"Bad name"}), 400
    f.save(folder / name)
    return jsonify({"ok": True})

@api.delete("/projects/<int:pid>/files")
@login_required
def fm_delete(pid):
    p, err = _own(pid)
    if err: return err
    rel = request.args.get("path","")
    if not rel: return jsonify({"error":"Refusing to delete project root"}), 400
    try: path = FS.safe_join(sandbox.project_src(p), rel)
    except ValueError: return jsonify({"error":"Bad path"}), 400
    shutil.rmtree(path) if path.is_dir() else path.unlink()
    return jsonify({"ok": True})

@api.get("/projects/<int:pid>/files/download")
@login_required
def fm_download(pid):
    p, err = _own(pid)
    if err: return err
    rel = request.args.get("path","")
    try: path = FS.safe_join(sandbox.project_src(p), rel)
    except ValueError: return jsonify({"error":"Bad path"}), 400
    if not path.is_file(): return jsonify({"error":"Not a file"}), 400
    return send_file(path, as_attachment=True, download_name=path.name)

# ---------- env vars ----------
@api.get("/projects/<int:pid>/env")
@login_required
def env_list(pid):
    p, err = _own(pid)
    if err: return err
    import security
    return jsonify([{"key": r.key, "masked": True}
                    for r in EnvVar.query.filter_by(project_id=p.id).all()])

@api.post("/projects/<int:pid>/env")
@login_required
def env_set(pid):
    p, err = _own(pid)
    if err: return err
    import re, security
    from services.process_manager import PM as _  # avoid unused
    d = request.get_json() or {}
    k = (d.get("key") or "").strip()
    v = d.get("value") or ""
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$", k):
        return jsonify({"error":"Invalid key name"}), 400
    if k.upper() in {"PATH","HOME","PYTHONPATH","PYTHONHOME","VIRTUAL_ENV","LD_PRELOAD"} or \
       k.upper().startswith("LD_"):
        return jsonify({"error":"Reserved key name"}), 400
    existing = db.session.get(EnvVar, (p.id, k))
    if existing: existing.value_enc = security.enc(v)
    else: db.session.add(EnvVar(project_id=p.id, key=k, value_enc=security.enc(v)))
    db.session.commit()
    return jsonify({"ok": True})

@api.delete("/projects/<int:pid>/env/<key>")
@login_required
def env_del(pid, key):
    p, err = _own(pid)
    if err: return err
    e = db.session.get(EnvVar, (p.id, key))
    if e: db.session.delete(e); db.session.commit()
    return jsonify({"ok": True})

# ---------- backups ----------
@api.get("/projects/<int:pid>/backups")
@login_required
def backups_list(pid):
    p, err = _own(pid)
    if err: return err
    rows = Backup.query.filter_by(project_id=p.id).order_by(Backup.created_at.desc()).all()
    return jsonify([{"id": b.id, "created_at": b.created_at, "size": b.size,
                     "filename": b.filename} for b in rows])

@api.post("/projects/<int:pid>/backups")
@login_required
def backups_create(pid):
    p, err = _own(pid)
    if err: return err
    b = BK.create(p)
    if not b: return jsonify({"error":"Backup failed"}), 500
    return jsonify({"ok": True, "backup": {"id": b.id, "size": b.size}})

@api.get("/projects/<int:pid>/backups/<int:bid>/download")
@login_required
def backups_dl(pid, bid):
    p, err = _own(pid)
    if err: return err
    b = db.session.get(Backup, bid)
    if not b or b.project_id != p.id: return jsonify({"error":"Not found"}), 404
    return send_file(Config.BACKUPS_DIR / b.filename, as_attachment=True)

@api.post("/projects/<int:pid>/backups/<int:bid>/restore")
@login_required
def backups_restore(pid, bid):
    p, err = _own(pid)
    if err: return err
    b = db.session.get(Backup, bid)
    if not b or b.project_id != p.id: return jsonify({"error":"Not found"}), 404
    was_active = bool(p.desired) or p.status == "running"
    if p.status == "running": PM.stop(p)
    BK.create(p)
    BK.restore(p, b)
    if was_active: PM.start(p)
    _audit("project.restore", f"{pid} {bid}")
    return jsonify({"ok": True})