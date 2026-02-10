from __future__ import annotations

from fastapi.testclient import TestClient


def test_get_hyperchain_pipeline(client: TestClient, auth_headers):
    headers = auth_headers("qa")
    response = client.get("/api/v1/cicd/pipelines/hyperchain-binary", headers=headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["pipeline_key"] == "hyperchain-binary"
    assert data["build_machine"]["ip"] == "172.22.67.76"
    assert data["deploy_target"]["ip"] == "10.10.33.56"


def test_viewer_cannot_trigger_cicd(client: TestClient, auth_headers):
    headers = auth_headers("viewer")
    response = client.post(
        "/api/v1/cicd/pipelines/hyperchain-binary/runs",
        json={"branch": "release/test", "triggered_by": "viewer"},
        headers=headers,
    )
    assert response.status_code == 403


def test_trigger_and_update_cicd_stage(client: TestClient, auth_headers):
    headers = auth_headers("qa")

    trigger_resp = client.post(
        "/api/v1/cicd/pipelines/hyperchain-binary/runs",
        json={"branch": "release/hyperchain-v1", "commit_id": "abc123", "triggered_by": "qa"},
        headers=headers,
    )
    assert trigger_resp.status_code == 200
    run = trigger_resp.json()["data"]
    run_id = run["run_id"]

    # 推进所有阶段到 success，最终 run 应变成 success
    for stage_key in ["prepare", "build", "package", "scp"]:
        update_resp = client.post(
            f"/api/v1/cicd/runs/{run_id}/stages/{stage_key}:update",
            json={"status": "success", "note": "test-pass"},
            headers=headers,
        )
        assert update_resp.status_code == 200

    list_resp = client.get("/api/v1/cicd/pipelines/hyperchain-binary/runs", headers=headers)
    assert list_resp.status_code == 200
    runs = list_resp.json()["data"]
    target = next(item for item in runs if item["run_id"] == run_id)
    assert target["status"] == "success"
