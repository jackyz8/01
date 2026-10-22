import io, zipfile, time
from .conftest import login

def _mk(client, name):
    login(client)
    pid = client.post("/api/projects", json={"name":name},
                      headers={"X-Requested-With":"XMLHttpRequest"}).json["id"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf,"w") as z:
        z.writestr("app.py", "import time,sys\nprint('hello',flush=True)\n"
                             "for l in sys.stdin: print('got',l.strip(),flush=True)\n")
    buf.seek(0)
    client.post(f"/api/projects/{pid}/upload",
                data={"file":(buf,"p.zip")},
                content_type="multipart/form-data",
                headers={"X-Requested-With":"XMLHttpRequest"})
    return pid

def test_start_stop(client):
    pid = _mk(client, "life1")
    r = client.post(f"/api/projects/{pid}/start", headers={"X-Requested-With":"XMLHttpRequest"})
    assert r.status_code == 200 and r.json["ok"]
    time.sleep(2)
    r = client.post(f"/api/projects/{pid}/stop", headers={"X-Requested-With":"XMLHttpRequest"})
    assert r.json["ok"]

def test_isolation(client):
    pid = _mk(client, "iso1")
    client.post("/api/auth/logout", headers={"X-Requested-With":"XMLHttpRequest"})
    # create second user (admin approves via API)
    client.post("/api/auth/register", json={"email":"u2@x.co","password":"abcdefgh"},
                headers={"X-Requested-With":"XMLHttpRequest"})
    from database import db, User
    with client.application.app_context():
        u2 = User.query.filter_by(email="u2@x.co").first()
        u2.is_approved = True; db.session.commit()
    login(client, "u2@x.co", "abcdefgh")
    r = client.get(f"/api/projects/{pid}", headers={"X-Requested-With":"XMLHttpRequest"})
    assert r.status_code == 403