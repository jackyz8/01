# GLORY HOST

Web-based Python project hosting panel — Flask + SQLite + Docker sandbox + vanilla-JS dashboard.

## Requirements
- Linux (Docker for sandboxed execution is strongly recommended)
- Python 3.11+
- Docker Engine (for `SANDBOX_MODE=docker`)

## Quickstart (dev)
```bash
git clone <repo> glory-host && cd glory-host
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# generate secrets
python -c "import secrets;print('SECRET_KEY='+secrets.token_hex(32))" >> .env
python -c "from cryptography.fernet import Fernet;print('ENCRYPTION_KEY='+Fernet.generate_key().decode())" >> .env
python -c "from app import app; \
           from database import db,User; \
           c=app.app_context(); c.push(); \
           u=User.query.filter_by(email='admin@example.com').first(); \
           u.set_password('ChangeMeNow!'); db.session.commit(); print('admin password set')"
python run_dev.py    # http://127.0.0.1:8000