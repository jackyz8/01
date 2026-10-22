import re, time, threading, secrets as pysecrets
from collections import defaultdict
from flask import Blueprint, request, session, jsonify, redirect, url_for, render_template, g
from database import db, User
from security import enc  # noqa

auth_bp = Blueprint("auth", __name__)
_login_attempts = defaultdict(list)
_lk = threading.Lock()
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def _rate_ok(ip):
    now = time.time()
    with _lk:
        _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < 300]
        return len(_login_attempts[ip]) < 10

def _rate_fail(ip):
    with _lk: _login_attempts[ip].append(time.time())

def current_user():
    if "uid" not in session: return None
    return db.session.get(User, session["uid"])

def login_required(fn):
    from functools import wraps
    @wraps(fn)
    def w(*a, **k):
        if not current_user():
            if request.path.startswith("/api/"):
                return jsonify({"error":"auth required"}), 401
            return redirect(url_for("auth.login_page"))
        return fn(*a, **k)
    return w

def admin_required(fn):
    from functools import wraps
    @wraps(fn)
    def w(*a, **k):
        u = current_user()
        if not u or not u.is_admin:
            return jsonify({"error":"forbidden"}), 403
        return fn(*a, **k)
    return w

@auth_bp.route("/login", methods=["GET"])
def login_page(): return render_template("login.html")

@auth_bp.route("/register", methods=["GET"])
def register_page(): return render_template("register.html")

@auth_bp.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    pw = data.get("password") or ""
    if not EMAIL_RE.match(email): return jsonify({"error":"Invalid email"}), 400
    if len(pw) < 8: return jsonify({"error":"Password min 8 chars"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error":"Email already registered"}), 409
    u = User(email=email, is_approved=False)
    u.set_password(pw)
    db.session.add(u); db.session.commit()
    return jsonify({"ok": True, "pending_approval": True})

@auth_bp.route("/api/auth/login", methods=["POST"])
def login():
    ip = request.remote_addr or "?"
    if not _rate_ok(ip): return jsonify({"error":"Too many attempts, wait 5 min"}), 429
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    pw = data.get("password") or ""
    u = User.query.filter_by(email=email).first()
    if not u or not u.check_password(pw):
        _rate_fail(ip); return jsonify({"error":"Invalid credentials"}), 401
    if u.is_banned: return jsonify({"error":"Account banned"}), 403
    if not u.is_approved and not u.is_admin:
        return jsonify({"error":"Account pending admin approval"}), 403
    session.clear()
    session.permanent = True
    session["uid"] = u.id
    u.last_login = db.func.now()
    db.session.commit()
    return jsonify({"ok": True, "user": {"id": u.id, "email": u.email, "is_admin": u.is_admin}})

@auth_bp.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear(); return jsonify({"ok": True})

@auth_bp.route("/api/auth/me")
@login_required
def me():
    u = current_user()
    return jsonify({"id": u.id, "email": u.email, "is_admin": u.is_admin,
                    "max_projects": u.max_projects})