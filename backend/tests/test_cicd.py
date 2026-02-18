from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.routers import cicd


class _FakeSshClient:
    def close(self) -> None:
        return


@pytest.fixture()
def cicd_state_guard():
    pipelines = deepcopy(cicd._PIPELINES)
    runs = deepcopy(cicd._RUNS)
    yield
    cicd._PIPELINES.clear()
    cicd._PIPELINES.update(deepcopy(pipelines))
    cicd._RUNS.clear()
    cicd._RUNS.update(deepcopy(runs))


def _put_test_run(run_id: str, branch: str) -> dict:
    pipeline = cicd._create_pipeline()
    run = cicd._make_run(
        run_id=run_id,
        pipeline=pipeline,
        repo_url="git@gitlab.example.com:hyperchain/go-hyperchain.git",
        branch=branch,
        commit_id=None,
        note=None,
        triggered_by="qa",
    )
    stages = {item["stage_key"]: item for item in run["stages"]}
    stages["prepare"]["status"] = "success"
    stages["build"]["status"] = "success"
    stages["package"]["status"] = "running"
    stages["scp"]["status"] = "pending"
    cicd._RUNS["hyperchain-binary"] = [run]
    return run


def _find_stage(run: dict, stage_key: str) -> dict:
    return next(item for item in run["stages"] if item["stage_key"] == stage_key)


def test_get_hyperchain_pipeline(client: TestClient, auth_headers):
    headers = auth_headers("qa")
    response = client.get("/api/v1/cicd/pipelines/hyperchain-binary", headers=headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["pipeline_key"] == "hyperchain-binary"
    assert data["build_machine"]["ip"] == "172.22.67.76"
    assert data["deploy_target"]["ip"] == "10.10.131.192"


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
        json={
            "repo_url": "git@gitlab.example.com:hyperchain/go-hyperchain.git",
            "branch": "release/hyperchain-v1",
            "commit_id": "abc123",
            "triggered_by": "qa",
        },
        headers=headers,
    )
    assert trigger_resp.status_code == 200
    run = trigger_resp.json()["data"]
    run_id = run["run_id"]
    assert run["repo_url"] == "git@gitlab.example.com:hyperchain/go-hyperchain.git"
    assert "git clone -b" in run["stages"][0]["command"]

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


def test_get_cicd_run_logs_chunk(client: TestClient, auth_headers):
    headers = auth_headers("qa")
    trigger_resp = client.post(
        "/api/v1/cicd/pipelines/hyperchain-binary/runs",
        json={
            "repo_url": "git@gitlab.example.com:hyperchain/go-hyperchain.git",
            "branch": "develop-bm-zkj-perf",
            "triggered_by": "qa",
        },
        headers=headers,
    )
    assert trigger_resp.status_code == 200
    run = trigger_resp.json()["data"]
    run_id = run["run_id"]

    logs_resp = client.get(f"/api/v1/cicd/runs/{run_id}/logs?cursor=0&limit=20", headers=headers)
    assert logs_resp.status_code == 200
    data = logs_resp.json()["data"]
    assert data["run_id"] == run_id
    assert isinstance(data["lines"], list)
    assert data["next_cursor"] >= len(data["lines"])


def test_target_config_fallback_to_frigate(monkeypatch):
    monkeypatch.setattr(cicd._SETTINGS, "cicd_target_ssh_host", "")
    monkeypatch.setattr(cicd._SETTINGS, "cicd_target_ssh_user", "")
    monkeypatch.setattr(cicd._SETTINGS, "cicd_target_ssh_password", "")
    monkeypatch.setattr(cicd._SETTINGS, "frigate_dynamic_ssh_host", "10.10.131.192")
    monkeypatch.setattr(cicd._SETTINGS, "frigate_dynamic_ssh_user", "hyperchain")
    monkeypatch.setattr(cicd._SETTINGS, "frigate_dynamic_ssh_password", "secret")

    assert cicd._resolve_cicd_target_ssh_host() == "10.10.131.192"
    assert cicd._resolve_cicd_target_ssh_user() == "hyperchain"
    assert cicd._resolve_cicd_target_ssh_password() == "secret"


def test_execute_package_success_and_chain_scp(monkeypatch, cicd_state_guard):
    run = _put_test_run(run_id="RUN-TEST-SUCCESS", branch="develop-bm-zkj-perf")

    monkeypatch.setattr(cicd._SETTINGS, "cicd_target_ssh_password", "secret")
    monkeypatch.setattr(cicd, "_connect_cicd_ssh", lambda: _FakeSshClient())
    monkeypatch.setattr(cicd, "_connect_cicd_target_ssh", lambda: _FakeSshClient())

    def _fake_run_stage_command(_client, _run_id, _stage_key, command, auto_password=None):
        if command.endswith("git rev-parse HEAD"):
            return 0, ["e387dca4e567a8d0242696187ba4e63e2b08bc4f"]
        if "--short=8 HEAD" in command:
            return 0, ["e387dca4"]
        if "./hyperchain --codeVersion" in command:
            return 0, ["develop-bm-zkj-perf-20260211-e387dca4"]
        if "md5sum ./hyperchain" in command:
            return 0, ["2d3f4a5b6c7d8e9f0011223344556677  ./hyperchain"]
        if command.startswith("mkdir -p "):
            return 0, []
        if "scp -o StrictHostKeyChecking=no" in command:
            assert auto_password == "secret"
            return 0, ["copied"]
        if command.startswith("md5sum /home/hyperchain/dev_workspace/frigate-dynamic/bin_assets/new-hyperchain/hyperchain"):
            return 0, ["2d3f4a5b6c7d8e9f0011223344556677  hyperchain"]
        if command.startswith("rm -f "):
            return 0, []
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(cicd, "_run_stage_command", _fake_run_stage_command)
    cicd._execute_package_verify(run["run_id"], run["branch"])

    assert run["status"] == "success"
    assert _find_stage(run, "package")["status"] == "success"
    assert _find_stage(run, "scp")["status"] == "success"
    assert any("source_md5=" in item for item in run["logs"])
    assert any("target_md5=" in item for item in run["logs"])


def test_execute_package_fail_on_code_version_sha_mismatch(monkeypatch, cicd_state_guard):
    run = _put_test_run(run_id="RUN-TEST-PACKAGE-FAIL", branch="develop-bm-zkj-perf")

    monkeypatch.setattr(cicd, "_connect_cicd_ssh", lambda: _FakeSshClient())
    called = {"scp": False}

    def _fake_run_stage_command(_client, _run_id, _stage_key, command, auto_password=None):
        if command.endswith("git rev-parse HEAD"):
            return 0, ["e387dca4e567a8d0242696187ba4e63e2b08bc4f"]
        if "--short=8 HEAD" in command:
            return 0, ["e387dca4"]
        if "./hyperchain --codeVersion" in command:
            return 0, ["develop-bm-zkj-perf-20260211-deadbeef"]
        if "md5sum ./hyperchain" in command:
            return 0, ["2d3f4a5b6c7d8e9f0011223344556677  ./hyperchain"]
        raise AssertionError(f"unexpected command: {command}")

    def _fake_scp(*args, **kwargs):
        called["scp"] = True

    monkeypatch.setattr(cicd, "_run_stage_command", _fake_run_stage_command)
    monkeypatch.setattr(cicd, "_execute_scp_distribute", _fake_scp)

    cicd._execute_package_verify(run["run_id"], run["branch"])

    assert called["scp"] is False
    assert run["status"] == "failed"
    assert _find_stage(run, "package")["status"] == "failed"
    assert _find_stage(run, "scp")["status"] == "pending"


def test_execute_scp_fail_on_md5_mismatch(monkeypatch, cicd_state_guard):
    run = _put_test_run(run_id="RUN-TEST-SCP-FAIL", branch="develop-bm-zkj-perf")
    _find_stage(run, "package")["status"] = "success"
    _find_stage(run, "scp")["status"] = "running"

    monkeypatch.setattr(cicd._SETTINGS, "cicd_target_ssh_password", "secret")
    monkeypatch.setattr(cicd, "_connect_cicd_ssh", lambda: _FakeSshClient())
    monkeypatch.setattr(cicd, "_connect_cicd_target_ssh", lambda: _FakeSshClient())
    removed = {"called": False}

    def _fake_run_stage_command(_client, _run_id, _stage_key, command, auto_password=None):
        if command.startswith("mkdir -p "):
            return 0, []
        if "scp -o StrictHostKeyChecking=no" in command:
            return 0, ["copied"]
        if command.startswith("md5sum /home/hyperchain/dev_workspace/frigate-dynamic/bin_assets/new-hyperchain/hyperchain"):
            return 0, ["aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa  hyperchain"]
        if command.startswith("rm -f "):
            removed["called"] = True
            return 0, []
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(cicd, "_run_stage_command", _fake_run_stage_command)
    cicd._execute_scp_distribute(run["run_id"], run["branch"], source_md5="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")

    assert removed["called"] is True
    assert run["status"] == "failed"
    assert _find_stage(run, "scp")["status"] == "failed"
