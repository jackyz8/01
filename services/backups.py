import shutil, time, zipfile
from pathlib import Path
from config import Config
from database import db, Backup
from services import sandbox
from services.archive import safe_extract

def create(p):
    src = sandbox.project_src(p)
    if not src.exists(): return None
    name = f"{p.owner_id}_{p.id}_{int(time.time())}.zip"
    dest = Config.BACKUPS_DIR / name
    base = str(dest.with_suffix(""))
    shutil.make_archive(base, "zip", str(src))
    b = Backup(project_id=p.id, filename=name, size=dest.stat().st_size)
    db.session.add(b); db.session.commit()
    _trim(p)
    return b

def _trim(p, keep=5):
    rows = Backup.query.filter_by(project_id=p.id).order_by(Backup.created_at.desc()).all()
    for old in rows[keep:]:
        (Config.BACKUPS_DIR / old.filename).unlink(missing_ok=True)
        db.session.delete(old)
    db.session.commit()

def restore(p, b):
    path = Config.BACKUPS_DIR / b.filename
    if not path.exists(): raise FileNotFoundError
    src = sandbox.project_src(p)
    tmp = Config.TMP_DIR / f"restore_{p.id}_{int(time.time())}"
    try:
        safe_extract(path, tmp, strip_top=False)
        shutil.rmtree(src, ignore_errors=True)
        Path(tmp).rename(src)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)