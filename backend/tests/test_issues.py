from __future__ import annotations

from fastapi.testclient import TestClient


def test_issue_close_requires_regression_passed(client: TestClient, auth_headers):
    headers = auth_headers("qa")

    # TC-002 在 v1.1.0 初始为 not_run，应被关闭校验拒绝
    close_resp = client.post(
        "/api/v1/issues/ISS-001:close",
        json={
            "fix_version_key": "v1.0.0",
            "verify_version_key": "v1.1.0",
            "regression_case_keys": ["TC-002"],
        },
        headers=headers,
    )
    assert close_resp.status_code == 422

    # 将验证版本中的回归用例置为 passed
    update_resp = client.put(
        "/api/v1/versions/v1.1.0/cases/TC-002/status",
        json={"status": "passed", "note": "回归通过", "attachments": []},
        headers=headers,
    )
    assert update_resp.status_code == 200

    close_resp_2 = client.post(
        "/api/v1/issues/ISS-001:close",
        json={
            "fix_version_key": "v1.0.0",
            "verify_version_key": "v1.1.0",
            "regression_case_keys": ["TC-002"],
        },
        headers=headers,
    )
    assert close_resp_2.status_code == 200
    assert close_resp_2.json()["data"]["status"] == "closed"


def test_issue_close_with_run_key(client: TestClient, auth_headers):
    headers = auth_headers("qa")

    latest_run_resp = client.get("/api/v1/runs/latest", params={"version_key": "v1.0.0"}, headers=headers)
    assert latest_run_resp.status_code == 200
    run_key = latest_run_resp.json()["data"]["run_key"]

    close_resp = client.post(
        "/api/v1/issues/ISS-001:close",
        json={
            "fix_version_key": "v1.0.0",
            "run_key": run_key,
            "regression_case_keys": ["TC-001"],
        },
        headers=headers,
    )
    assert close_resp.status_code == 200
    assert close_resp.json()["data"]["status"] == "closed"
