from __future__ import annotations

from datetime import datetime, timezone
import time

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import AutomationRun, AutomationRunStatus


def _get_hypersonic_first_keys(client: TestClient, headers: dict[str, str]) -> tuple[str, str]:
    response = client.get("/api/v1/automation/frameworks/hypersonic", headers=headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["configurations"]) > 0
    assert len(data["test_suites"]) > 0
    return data["configurations"][0]["config_key"], data["test_suites"][0]["suite_key"]


def _wait_run_terminal_status(client: TestClient, headers: dict[str, str], run_id: str, timeout_sec: float = 8.0) -> str:
    deadline = time.monotonic() + timeout_sec
    cursor = 0
    status = "pending"
    while time.monotonic() < deadline:
        response = client.get(
            f"/api/v1/automation/runs/{run_id}/logs",
            params={"cursor": cursor, "limit": 200},
            headers=headers,
        )
        assert response.status_code == 200
        payload = response.json()["data"]
        status = payload["status"]
        cursor = payload["next_cursor"]
        if status in {"success", "failed", "canceled"}:
            return status
        time.sleep(0.1)
    raise AssertionError(f"任务 {run_id} 在 {timeout_sec}s 内未进入终态，当前状态: {status}")


def test_get_frigate_dynamic_framework(client: TestClient, auth_headers):
    headers = auth_headers("qa")
    response = client.get("/api/v1/automation/frameworks/frigateDynamic", headers=headers)
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["entry_name"] == "性能测试自动化"
    assert data["framework_type"] == "performance"
    assert data["build_machine"]["ip"] == "10.10.131.192"
    assert data["streamlit_url"] == "http://10.10.131.192:8501"
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
    assert len(run["logs"]) > 0


def test_hypersonic_trigger_and_logs_chunk(client: TestClient, auth_headers):
    headers = auth_headers("qa")
    config_key, suite_key = _get_hypersonic_first_keys(client, headers)

    trigger_resp = client.post(
        "/api/v1/automation/frameworks/hypersonic/runs",
        json={
            "configuration_key": config_key,
            "test_suite_key": suite_key,
            "operation_mode": "functional_test",
            "triggered_by": "qa",
        },
        headers=headers,
    )
    assert trigger_resp.status_code == 200
    run = trigger_resp.json()["data"]
    assert run["framework_key"] == "hypersonic"
    assert run["operation_mode"] == "functional_test"
    assert run["status"] in {"pending", "running", "success"}

    logs_resp = client.get(
        f"/api/v1/automation/runs/{run['run_id']}/logs",
        params={"cursor": 0, "limit": 2},
        headers=headers,
    )
    assert logs_resp.status_code == 200
    chunk = logs_resp.json()["data"]
    assert chunk["run_id"] == run["run_id"]
    assert isinstance(chunk["lines"], list)
    assert len(chunk["lines"]) <= 2
    assert isinstance(chunk["next_cursor"], int)
    assert isinstance(chunk["has_more"], bool)

    final_status = _wait_run_terminal_status(client, headers, run["run_id"])
    assert final_status == "success"


def test_cancel_pending_hypersonic_run(client: TestClient, auth_headers, db_session: Session):
    headers = auth_headers("qa")
    run_id = f"AUTO-CANCEL-{int(time.time() * 1000)}"

    run = AutomationRun(
        run_id=run_id,
        framework_key="hypersonic",
        entry_name="功能测试自动化",
        configuration_key="func-default",
        test_suite_key="demo",
        operation_mode="functional_test",
        status=AutomationRunStatus.pending,
        triggered_by="qa",
        started_at=datetime.now(timezone.utc),
        finished_at=None,
        cancel_requested=False,
        meta_json={"source": "test"},
    )
    db_session.add(run)
    db_session.commit()

    response = client.post(f"/api/v1/automation/runs/{run_id}:cancel", headers=headers)
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["run_id"] == run_id
    assert payload["status"] == "canceled"
    assert payload["finished_at"] is not None
    assert any("任务已取消" in line for line in payload["logs"])


def test_viewer_cannot_update_or_trigger_automation(client: TestClient, auth_headers):
    viewer_headers = auth_headers("viewer")
    qa_headers = auth_headers("qa")
    _, suite_key = _get_hypersonic_first_keys(client, qa_headers)

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
            "test_suite_key": suite_key,
            "operation_mode": "functional_test",
            "triggered_by": "viewer",
        },
        headers=viewer_headers,
    )
    assert trigger_resp.status_code == 403


def test_invalid_operation_mode_is_rejected(client: TestClient, auth_headers):
    headers = auth_headers("qa")
    config_key, suite_key = _get_hypersonic_first_keys(client, headers)
    response = client.post(
        "/api/v1/automation/frameworks/hypersonic/runs",
        json={
            "configuration_key": config_key,
            "test_suite_key": suite_key,
            "operation_mode": "deploy_and_test",
            "triggered_by": "qa",
        },
        headers=headers,
    )
    assert response.status_code == 422
