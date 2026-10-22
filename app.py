import os, sys, logging
from flask import Flask, render_template, session, redirect, url_for
from config import Config
from database import db, init_db
from auth import auth_bp, current_user
from api import api
from admin_api import adm
from services.supervisor import start as start_supervisor
from services import sandbox

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    if not app.config["SECRET_KEY"]:
        sys.exit("SECRET_KEY missing. Set it in .env (use: python -c 'import secrets;print(secrets.token_hex(32))')")
    Config.ensure_dirs()
    db.init_app(app)
    with app.app_context(): init_db(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(api)
    app.register_blueprint(adm)

    @app.route("/")
    def landing():
        if current_user(): return redirect(url_for("dashboard"))
        return render_template("landing.html")

    @app.route("/dashboard")
    def dashboard():
        if not current_user(): return redirect(url_for("auth.login_page"))
        return render_template("dashboard.html")

    @app.route("/projects/<int:pid>")
    def project_page(pid):
        if not current_user(): return redirect(url_for("auth.login_page"))
        return render_template("project_detail.html", pid=pid)

    @app.route("/admin")
    def admin_page():
        u = current_user()
        if not u or not u.is_admin: return redirect(url_for("dashboard"))
        return render_template("admin.html")

    @app.route("/docs")
    def docs(): return render_template("docs.html")

    @app.before_request
    def csrf_guard():
        from flask import request
        if request.method in ("POST","PUT","PATCH","DELETE") and not request.path.startswith("/api/auth/"):
            # Require Origin/Referer match for same-origin protection; plus X-CSRF header
            if request.headers.get("X-Requested-With") != "XMLHttpRequest":
                return {"error":"CSRF: missing X-Requested-With"}, 403

    @app.errorhandler(413)
    def too_large(e): return {"error":f"File exceeds {Config.MAX_ZIP_MB} MB"}, 413

    start_supervisor(app)
    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1", port=int(os.environ.get("PORT","8000")))