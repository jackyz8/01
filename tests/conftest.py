import os, tempfile, pytest
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="glory-test-")
os.environ["SECRET_KEY"] = "test-secret-key-not-for-prod"
os.environ["DATABASE_URL"] = f"sqlite:///{os.environ['DATA_DIR']}/test.db"
os.environ["SANDBOX_MODE"] = "process"
os.environ["ALLOW_UNSANDBOXED_USERS"] = "true"
os.environ["ADMIN_EMAIL"] = ""

from app import app as _app
from database import db, User

@pytest.fixture()
def app():
    _app.config.update(TESTING=True)
    with _app.app_context():
        db.drop_all(); db.create_all()
        u = User(email="a@b.co", is_approved=True, is_admin=True)
        u.set_password("password123"); db.session.add(u); db.session.commit()
    yield _app

@pytest.fixture()
def client(app):
    return app.test_client()

def login(client, email="a@b.co", pw="password123"):
    r = client.post("/api/auth/login", json={"email":email,"password":pw},
                    headers={"X-Requested-With":"XMLHttpRequest"})
    assert r.status_code == 200, r.data