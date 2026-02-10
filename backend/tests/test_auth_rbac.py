from __future__ import annotations

from fastapi.testclient import TestClient


def test_login_and_me(client: TestClient):
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "password123"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["data"]["access_token"]

    me_resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["data"]["username"] == "admin"


def test_viewer_cannot_create_version(client: TestClient, auth_headers):
    headers = auth_headers("viewer")
    response = client.post("/api/v1/versions", json={"version_key": "v9.9.9"}, headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
