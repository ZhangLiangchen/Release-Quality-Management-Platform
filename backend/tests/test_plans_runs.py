from __future__ import annotations

from fastapi.testclient import TestClient


def test_list_suites_returns_created_suite(client: TestClient, auth_headers):
    headers = auth_headers("qa")

    create_suite_resp = client.post(
        "/api/v1/suites",
        json={
            "version_key": "v1.0.0",
            "name": "列表检查用例集",
            "description": "list-suite-test",
        },
        headers=headers,
    )
    assert create_suite_resp.status_code == 200
    suite_key = create_suite_resp.json()["data"]["suite_key"]

    resp = client.get("/api/v1/suites", params={"version_key": "v1.0.0"}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert any(item["suite_key"] == suite_key for item in data)


def test_create_plan_and_run_and_update_status(client: TestClient, auth_headers):
    headers = auth_headers("qa")

    create_suite_resp = client.post(
        "/api/v1/suites",
        json={
            "version_key": "v1.0.0",
            "name": "回归套件-自动化",
            "description": "测试创建流程",
        },
        headers=headers,
    )
    assert create_suite_resp.status_code == 200
    suite = create_suite_resp.json()["data"]
    suite_key = suite["suite_key"]
    suite_version_key = suite["versions"][0]["suite_version_key"]

    add_cases_resp = client.post(
        f"/api/v1/suites/{suite_key}/versions/{suite_version_key}/cases:add",
        json={"case_keys": ["TC-001", "TC-002"]},
        headers=headers,
    )
    assert add_cases_resp.status_code == 200

    publish_resp = client.post(f"/api/v1/suites/{suite_key}/versions/{suite_version_key}/publish", headers=headers)
    assert publish_resp.status_code == 200

    create_plan_resp = client.post(
        "/api/v1/plans",
        json={
            "version_key": "v1.0.0",
            "suite_version_key": suite_version_key,
            "name": "自动化回归计划",
            "description": "测试计划",
        },
        headers=headers,
    )
    assert create_plan_resp.status_code == 200
    plan_key = create_plan_resp.json()["data"]["plan_key"]

    create_run_resp = client.post(
        f"/api/v1/plans/{plan_key}/runs",
        json={"name": "回归-Run1", "build_no": "b001", "environment": "staging"},
        headers=headers,
    )
    assert create_run_resp.status_code == 200
    run_key = create_run_resp.json()["data"]["run_key"]

    run_cases_resp = client.get(f"/api/v1/runs/{run_key}/cases", headers=headers)
    assert run_cases_resp.status_code == 200
    run_cases = run_cases_resp.json()["data"]
    assert len(run_cases) > 0

    first_run_case = run_cases[0]
    update_resp = client.put(
        f"/api/v1/runs/{run_key}/cases/{first_run_case['run_case_key']}",
        json={"status": "passed", "remark": "执行通过", "attachments": []},
        headers=headers,
    )
    assert update_resp.status_code == 200

    history_resp = client.get(f"/api/v1/runs/{run_key}/cases/{first_run_case['run_case_key']}/history", headers=headers)
    assert history_resp.status_code == 200
    history = history_resp.json()["data"]
    assert len(history) >= 1
    assert history[0]["status"] == "passed"
