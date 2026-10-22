import time, secrets
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_approved = db.Column(db.Boolean, default=False, nullable=False)
    is_banned = db.Column(db.Boolean, default=False, nullable=False)
    max_projects = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    projects = db.relationship("Project", backref="owner", lazy="dynamic")

    def set_password(self, pw): self.password_hash = generate_password_hash(pw)
    def check_password(self, pw): return check_password_hash(self.password_hash, pw)

class Project(db.Model):
    __tablename__ = "projects"
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    startup = db.Column(db.String(255))
    args = db.Column(db.String(500))
    image = db.Column(db.String(120))
    status = db.Column(db.String(16), default="new", nullable=False)
    desired = db.Column(db.Boolean, default=False)
    pid = db.Column(db.Integer)
    pid_ctime = db.Column(db.Float)
    container = db.Column(db.String(64))
    started_at = db.Column(db.Float)
    ended_at = db.Column(db.Float)
    exit_code = db.Column(db.Integer)
    auto_restart = db.Column(db.Boolean, default=True)
    restart_count = db.Column(db.Integer, default=0)
    crash_count = db.Column(db.Integer, default=0)
    restart_every_h = db.Column(db.Integer, default=0)
    sandbox = db.Column(db.String(16), default="docker")
    created_at = db.Column(db.Float, default=time.time)
    __table_args__ = (db.UniqueConstraint("owner_id", "name", name="uq_owner_name"),)

class EnvVar(db.Model):
    __tablename__ = "env_vars"
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), primary_key=True)
    key = db.Column(db.String(64), primary_key=True)
    value_enc = db.Column(db.Text, nullable=False)

class Backup(db.Model):
    __tablename__ = "backups"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), index=True)
    filename = db.Column(db.String(255), nullable=False)
    size = db.Column(db.Integer)
    created_at = db.Column(db.Float, default=time.time)

class AuditLog(db.Model):
    __tablename__ = "audit_log"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    action = db.Column(db.String(64))
    detail = db.Column(db.Text)
    ip = db.Column(db.String(64))
    created_at = db.Column(db.Float, default=time.time)

def init_db(app):
    with app.app_context():
        db.create_all()
        admin_email = app.config.get("ADMIN_EMAIL", "").strip().lower()
        if admin_email and not User.query.filter_by(email=admin_email).first():
            # admin is created but password must be set via CLI (never via env)
            u = User(email=admin_email, is_admin=True, is_approved=True)
            u.set_password(secrets.token_urlsafe(32))  # forces CLI reset
            db.session.add(u)
            db.session.commit()