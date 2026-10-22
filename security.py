import os
from cryptography.fernet import Fernet, InvalidToken
from config import Config

_fernet = None

def _load():
    global _fernet
    if _fernet is not None: return _fernet
    key = Config.ENCRYPTION_KEY
    keyfile = Config.DATA_DIR / "secret.key"
    if not key:
        if keyfile.exists():
            key = keyfile.read_text().strip()
        else:
            key = Fernet.generate_key().decode()
            fd = os.open(keyfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f: f.write(key)
    _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet

def enc(s: str) -> str:
    return _load().encrypt(s.encode()).decode()

def dec(s: str) -> str:
    try: return _load().decrypt(s.encode()).decode()
    except (InvalidToken, Exception): return ""