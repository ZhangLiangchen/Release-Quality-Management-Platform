from __future__ import annotations

from fastapi.testclient import TestClient


def _create_published_plan(client: TestClient, headers: dict[str, str], *, name: str, case_keys: list[str]) -> str:
    suite_resp = client.post(
        "/api/v1/suites",
        json={
            "version_key": "v1.0.0",
            "name": f"{name}-suite",
            "description": "delete-plan-test",
            "case_keys": case_keys,
        },
        headers=headers,
    )
    assert suite_resp.status_code == 200
    suite = suite_resp.json()["data"]
    suite_key = suite["suite_key"]
    suite_version_key = suite["versions"][0]["suite_version_key"]

    publish_resp = client.post(f"/api/v1/suites/{suite_key}/versions/{suite_version_key}/publish", headers=headers)
    assert publish_resp.status_code == 200

    plan_resp = client.post(
        "/api/v1/plans",
        json={
            "version_key": "v1.0.0",
            "suite_version_key": suite_version_key,
            "name": name,
            "description": "delete-plan-test",
        },
        headers=headers,
    )
    assert plan_resp.status_code == 200
    return plan_resp.json()["data"]["plan_key"]


def test_delete_plan_success_when_no_issue_binding(client: TestClient, auth_headers):
    headers = auth_headers("qa")
    plan_key = _create_published_plan(client, headers, name="删除计划-无绑定", case_keys=["TC-001"])

    resp = client.delete(f"/api/v1/plans/{plan_key}", headers=headers)
    assert resp.status_code == 200

    list_resp = client.get("/api/v1/plans", params={"version_key": "v1.0.0"}, headers=headers)
    assert list_resp.status_code == 200
    keys = {item["plan_key"] for item in list_resp.json()["data"]}
    assert plan_key not in keys


def test_delete_plan_blocked_when_issue_binding_exists(client: TestClient, auth_headers):
    headers = auth_headers("qa")
    plan_key = _create_published_plan(client, headers, name="删除计划-有绑定", case_keys=["TC-002"])

    resp = client.delete(f"/api/v1/plans/{plan_key}", headers=headers)
    assert resp.status_code == 422
    error = resp.json()["error"]
    assert error["message"] == "该测试计划有问题单绑定，不可删除"

    bindings = error["details"]["bindings"]
    assert any(item["issue_key"] == "ISS-001" and item["case_key"] == "TC-002" for item in bindings)
