import threading, time, logging
from config import Config
from database import db, Project
from services.process_manager import PM
from services.logs import LOGS

log = logging.getLogger("supervisor")
_started = False

def start(app):
    global _started
    if _started: return
    _started = True
    threading.Thread(target=_loop, args=(app,), daemon=True, name="supervisor").start()

def _loop(app):
    with app.app_context():
        if Config.RESUME_ON_START:
            time.sleep(3)
            for p in Project.query.filter_by(desired=True).all():
                if p.status == "running" and PM.is_alive(p): continue
                ok, info = PM.start(p, manual=False)
                log.info("resume %s: %s", p.id, info)
        while True:
            time.sleep(Config.MONITOR_INTERVAL)
            try: _tick(app)
            except Exception: log.exception("supervisor tick")

def _tick(app):
    with app.app_context():
        for p in Project.query.filter_by(status="running").all():
            if PM.is_alive(p): LOGS.rotate(p); continue
            PM.finalize(p.id)
        while PM.pending:
            pid = PM.pending.pop(0)
            p = db.session.get(Project, pid)
            if not p: continue
            n = p.restart_count or 0
            if p.auto_restart and n < Config.AUTO_RESTART_MAX:
                delay = min(60, 3 * 2 ** n)
                p.restart_count = n + 1; db.session.commit()
                def _do(pid=pid, delay=delay):
                    time.sleep(delay)
                    with app.app_context():
                        pp = db.session.get(Project, pid)
                        if pp and pp.desired and pp.status != "running":
                            PM.start(pp, manual=False)
                threading.Thread(target=_do, daemon=True).start()
        for p in Project.query.filter_by(status="running").all():
            if p.restart_every_h and p.started_at and \
               time.time() - p.started_at > p.restart_every_h * 3600:
                PM.restart(p)