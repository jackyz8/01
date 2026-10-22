import io, zipfile
from .conftest import login
from database import Project, db

def _create_proj(client, name="t1"):
    login(client)
    r = client.post("/api/projects", json={"name":name},
                    headers={"X-Requested-With":"XMLHttpRequest"})
    return r.json["id"]

def test_path_traversal_rejected(client):
    pid = _create_proj(client)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf,"w") as z: z.writestr("../../etc/passwd","x")
    buf.seek(0)
    r = client.post(f"/api/projects/{pid}/upload",
                    data={"file":(buf,"evil.zip")},
                    content_type="multipart/form-data",
                    headers={"X-Requested-With":"XMLHttpRequest"})
    assert r.status_code == 400

def test_safe_zip_ok(client):
    pid = _create_proj(client)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf,"w") as z:
        z.writestr("app.py","print('hi')\n")
    buf.seek(0)
    r = client.post(f"/api/projects/{pid}/upload",
                    data={"file":(buf,"ok.zip")},
                    content_type="multipart/form-data",
                    headers={"X-Requested-With":"XMLHttpRequest"})
    assert r.status_code == 200 and r.json["startup"] == "app.py"