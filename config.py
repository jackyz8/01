import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INSTANCE = BASE_DIR / "instance"
INSTANCE.mkdir(exist_ok=True)

def _int(k, d): 
    try: return int(os.environ.get(k, d))
    except ValueError: return d
def _bool(k, d=False):
    return str(os.environ.get(k, d)).lower() in ("1","true","yes","on")

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "")
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8
    MAX_CONTENT_LENGTH = _int("MAX_ZIP_MB", 100) * 1024 * 1024

    DATA_DIR = Path(os.environ.get("DATA_DIR", INSTANCE / "data")).resolve()
    PROJECTS_DIR = DATA_DIR / "projects"
    VENVS_DIR = DATA_DIR / "venvs"
    LOGS_DIR = DATA_DIR / "logs"
    RUNTIME_DIR = DATA_DIR / "runtime"
    BACKUPS_DIR = DATA_DIR / "backups"
    TMP_DIR = DATA_DIR / "tmp"
    DB_URL = os.environ.get("DATABASE_URL", f"sqlite:///{INSTANCE/'glory.db'}")

    SANDBOX_MODE = os.environ.get("SANDBOX_MODE", "docker").lower()
    DOCKER_BIN = os.environ.get("DOCKER_BIN", "docker")
    DOCKER_IMAGE = os.environ.get("DOCKER_IMAGE", "python:3.11-slim")
    DOCKER_NETWORK = os.environ.get("DOCKER_NETWORK", "bridge")
    ALLOW_UNSANDBOXED_USERS = _bool("ALLOW_UNSANDBOXED_USERS", False)

    PROJECT_MEM_MB = _int("PROJECT_MEM_MB", 512)
    PROJECT_CPUS = float(os.environ.get("PROJECT_CPUS", "1.0"))
    PROJECT_PIDS = _int("PROJECT_PIDS", 256)
    MAX_PROJECTS_PER_USER = _int("MAX_PROJECTS_PER_USER", 5)
    MAX_ZIP_MB = _int("MAX_ZIP_MB", 100)
    MAX_UNZIPPED_MB = _int("MAX_UNZIPPED_MB", 500)
    MAX_FILE_MB = _int("MAX_FILE_MB", 50)
    MAX_ZIP_FILES = _int("MAX_ZIP_FILES", 5000)
    AUTO_RESTART_MAX = _int("AUTO_RESTART_MAX", 10)
    RESUME_ON_START = _bool("RESUME_ON_START", True)
    PIP_TIMEOUT = _int("PIP_TIMEOUT", 900)
    MONITOR_INTERVAL = float(os.environ.get("MONITOR_INTERVAL", "5"))

    ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "")
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").strip().lower()

    @classmethod
    def ensure_dirs(cls):
        for d in (cls.DATA_DIR, cls.PROJECTS_DIR, cls.VENVS_DIR,
                  cls.LOGS_DIR, cls.RUNTIME_DIR, cls.BACKUPS_DIR, cls.TMP_DIR):
            d.mkdir(parents=True, exist_ok=True)