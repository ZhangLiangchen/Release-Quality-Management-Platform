from __future__ import annotations

from fastapi.testclient import TestClient


def test_get_frigate_dynamic_framework(client: TestClient, auth_headers):
    headers = auth_headers("qa")
    response = client.get("/api/v1/automation/frameworks/frigateDynamic", headers=headers)
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["entry_name"] == "性能测试自动化"
    assert data["framework_type"] == "performance"
    assert data["build_machine"]["ip"] == "172.22.67.76"
    assert len(data["configurations"]) > 0
    assert len(data["test_suites"]) > 0


def test_update_configuration_and_trigger_run(client: TestClient, auth_headers):
    headers = auth_headers("qa")

    update_resp = client.put(
        "/api/v1/automation/frameworks/frigateDynamic/configurations/perf-default",
        json={"content": "job_name: updated_perf_job", "updated_by": "qa"},
        headers=headers,
    )
    assert update_resp.status_code == 200
    updated_framework = update_resp.json()["data"]
    updated_config = next(item for item in updated_framework["configurations"] if item["config_key"] == "perf-default")
    assert updated_config["content"] == "job_name: updated_perf_job"

    trigger_resp = client.post(
        "/api/v1/automation/frameworks/frigateDynamic/runs",
        json={
            "configuration_key": "perf-default",
            "test_suite_key": "suite-perf-smoke",
            "operation_mode": "deploy_and_test",
            "note": "integration-test",
            "triggered_by": "qa",
        },
        headers=headers,
    )
    assert trigger_resp.status_code == 200
    run = trigger_resp.json()["data"]
    assert run["framework_key"] == "frigateDynamic"
    assert run["operation_mode"] == "deploy_and_test"
    assert run["status"] in {"running", "success"}


def test_viewer_cannot_update_or_trigger_automation(client: TestClient, auth_headers):
    viewer_headers = auth_headers("viewer")

    update_resp = client.put(
        "/api/v1/automation/frameworks/hypersonic/configurations/func-default",
        json={"content": "suite_mode: smoke", "updated_by": "viewer"},
        headers=viewer_headers,
    )
    assert update_resp.status_code == 403

    trigger_resp = client.post(
        "/api/v1/automation/frameworks/hypersonic/runs",
        json={
            "configuration_key": "func-default",
            "test_suite_key": "suite-func-core",
            "operation_mode": "functional_test",
            "triggered_by": "viewer",
        },
        headers=viewer_headers,
    )
    assert trigger_resp.status_code == 403


def test_invalid_operation_mode_is_rejected(client: TestClient, auth_headers):
    headers = auth_headers("qa")
    response = client.post(
        "/api/v1/automation/frameworks/hypersonic/runs",
        json={
            "configuration_key": "func-default",
            "test_suite_key": "suite-func-core",
            "operation_mode": "deploy_and_test",
            "triggered_by": "qa",
        },
        headers=headers,
    )
    assert response.status_code == 422
