from .conftest import login

def test_register_and_login(client):
    r = client.post("/api/auth/register",
                    json={"email":"x@y.z","password":"abcdefgh"},
                    headers={"X-Requested-With":"XMLHttpRequest"})
    assert r.status_code == 200
    # not approved yet
    r = client.post("/api/auth/login",
                    json={"email":"x@y.z","password":"abcdefgh"},
                    headers={"X-Requested-With":"XMLHttpRequest"})
    assert r.status_code == 403

def test_admin_login(client):
    login(client)
    r = client.get("/api/auth/me")
    assert r.json["is_admin"] is True

def test_bad_password(client):
    r = client.post("/api/auth/login",
                    json={"email":"a@b.co","password":"wrong"},
                    headers={"X-Requested-With":"XMLHttpRequest"})
    assert r.status_code == 401