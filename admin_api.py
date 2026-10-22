from flask import Blueprint, request, jsonify
from auth import admin_required, current_user
from database import db, User, Project, AuditLog
from services import monitoring
from services.process_manager import PM
from services.files import dir_size
from config import Config

adm = Blueprint("admin_api", __name__, url_prefix="/api/admin")

@adm.get("/users")
@admin_required
def users():
    return jsonify([{"id": u.id, "email": u.email, "is_admin": u.is_admin,
                     "is_approved": u.is_approved, "is_banned": u.is_banned,
                     "max_projects": u.max_projects,
                     "created_at": u.created_at} for u in User.query.all()])

@adm.patch("/users/<int:uid>")
@admin_required
def users_update(uid):
    u = db.session.get(User, uid)
    if not u: return jsonify({"error":"not found"}), 404
    d = request.get_json() or {}
    for k in ("is_approved","is_banned","is_admin"):
        if k in d: setattr(u, k, bool(d[k]))
    if "max_projects" in d:
        v = d["max_projects"]
        u.max_projects = int(v) if v not in (None, "", "null") else None
    db.session.commit()
    return jsonify({"ok": True})

@adm.get("/projects")
@admin_required
def projects():
    return jsonify([{"id": p.id, "owner_id": p.owner_id, "name": p.name,
                     "status": p.status} for p in Project.query.all()])

@adm.post("/projects/<int:pid>/kill")
@admin_required
def kill(pid):
    p = db.session.get(Project, pid)
    if not p: return jsonify({"error":"not found"}), 404
    ok, msg = PM.stop(p, force=True)
    return jsonify({"ok": ok, "message": msg})

@adm.get("/system")
@admin_required
def system():
    du = dir_size(Config.PROJECTS_DIR)
    return jsonify({"host": monitoring.host_stats(),
                    "storage": {"projects_bytes": du,
                                "projects_dir": str(Config.PROJECTS_DIR)}})

@adm.get("/audit")
@admin_required
def audit():
    rows = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(200).all()
    return jsonify([{"id": a.id, "user_id": a.user_id, "action": a.action,
                     "detail": a.detail, "ip": a.ip, "created_at": a.created_at} for a in rows])