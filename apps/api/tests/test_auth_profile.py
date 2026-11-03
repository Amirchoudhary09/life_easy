from __future__ import annotations

from tests.conftest import register


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.headers["x-request-id"]


async def test_request_id_is_echoed(client):
    resp = await client.get("/health", headers={"X-Request-ID": "abc123"})
    assert resp.headers["x-request-id"] == "abc123"


async def test_register_login_refresh_logout(client):
    resp = await client.post("/api/v1/auth/register", json={"email": "A@Example.com", "password": "correct horse battery"})
    assert resp.status_code == 201
    tokens = resp.json()
    assert tokens["token_type"] == "bearer"

    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == "a@example.com"  # normalised

    dup = await client.post("/api/v1/auth/register", json={"email": "a@example.com", "password": "correct horse battery"})
    assert dup.status_code == 409

    bad = await client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "wrong password!"})
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "unauthorized"

    ok = await client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "correct horse battery"})
    assert ok.status_code == 200

    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200
    reused = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert reused.status_code == 401, "refresh tokens rotate: the old one is dead"

    new_refresh = refreshed.json()["refresh_token"]
    out = await client.post("/api/v1/auth/logout", json={"refresh_token": new_refresh})
    assert out.status_code == 204
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh})).status_code == 401


async def test_short_password_rejected(client):
    resp = await client.post("/api/v1/auth/register", json={"email": "a@example.com", "password": "short"})
    assert resp.status_code == 422


async def test_protected_routes_require_token(client):
    assert (await client.get("/api/v1/me/profile")).status_code == 401
    assert (await client.get("/api/v1/me/profile", headers={"Authorization": "Bearer nope"})).status_code == 401


async def test_profile_update_and_isolation(client):
    a = await register(client, "a@example.com")
    b = await register(client, "b@example.com")
    resp = await client.patch(
        "/api/v1/me/profile",
        headers=a,
        json={
            "headline": "Backend developer",
            "skills": ["python", "fastapi"],
            "display_name": "Amir C",
            "preferences": {"titles": ["backend engineer"], "locations": ["Bengaluru"], "remote": "any"},
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["skills"] == ["python", "fastapi"]
    assert resp.json()["preferences"]["locations"] == ["Bengaluru"]
    assert (await client.get("/api/v1/auth/me", headers=a)).json()["display_name"] == "Amir C"
    other = await client.get("/api/v1/me/profile", headers=b)
    assert other.json()["headline"] is None, "users never see each other's data"


async def test_export_and_delete(client, inline_tasks):
    headers = await register(client)
    up = await client.post(
        "/api/v1/resumes", headers=headers, files={"file": ("cv.txt", b"Python developer, 3 years, FastAPI", "text/plain")}
    )
    assert up.status_code == 201
    export = await client.get("/api/v1/me/export", headers=headers)
    assert export.status_code == 200
    body = export.json()
    assert body["user"]["email"] == "amir@example.com"
    assert "password_hash" not in body["user"]
    assert len(body["resumes"]) == 1 and "embedding" not in body["resumes"][0]
    assert "audit_events" in body

    gone = await client.delete("/api/v1/me", headers=headers)
    assert gone.status_code == 202
    assert (await client.get("/api/v1/me/profile", headers=headers)).status_code == 401
    login = await client.post("/api/v1/auth/login", json={"email": "amir@example.com", "password": "correct horse battery"})
    assert login.status_code == 401
    # purged: the same email can register again
    again = await client.post("/api/v1/auth/register", json={"email": "amir@example.com", "password": "correct horse battery"})
    assert again.status_code == 201


async def test_rate_limit_on_login(client):
    for _ in range(20):
        await client.post("/api/v1/auth/login", json={"email": "x@example.com", "password": "whatever-pass"})
    resp = await client.post("/api/v1/auth/login", json={"email": "x@example.com", "password": "whatever-pass"})
    assert resp.status_code == 429
