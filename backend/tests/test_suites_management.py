from __future__ import annotations

from fastapi.testclient import TestClient


def _create_suite(
    client: TestClient,
    headers: dict[str, str],
    *,
    name: str,
    case_keys: list[str] | None = None,
) -> tuple[str, str]:
    payload: dict[str, object] = {
        "version_key": "v1.0.0",
        "name": name,
        "description": "suite-management-test",
    }
    if case_keys is not None:
        payload["case_keys"] = case_keys

    resp = client.post("/api/v1/suites", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    return data["suite_key"], data["versions"][0]["suite_version_key"]


def test_create_suite_defaults_to_empty_cases(client: TestClient, auth_headers):
    headers = auth_headers("qa")
    suite_key, suite_version_key = _create_suite(client, headers, name="管理测试-空用例集")

    detail = client.get(f"/api/v1/suites/{suite_key}/versions/{suite_version_key}", headers=headers)
    assert detail.status_code == 200
    data = detail.json()["data"]
    assert data["suite_version"]["case_count"] == 0
    assert data["cases"] == []


def test_update_suite_success_and_duplicate_name_rejected(client: TestClient, auth_headers):
    headers = auth_headers("qa")
    suite_a_key, _ = _create_suite(client, headers, name="管理测试-更新-A")
    suite_b_key, _ = _create_suite(client, headers, name="管理测试-更新-B")

    duplicate_resp = client.put(
        f"/api/v1/suites/{suite_b_key}",
        json={"name": "管理测试-更新-A", "description": "dup"},
        headers=headers,
    )
    assert duplicate_resp.status_code == 422

    update_resp = client.put(
        f"/api/v1/suites/{suite_b_key}",
        json={"name": "管理测试-更新-B2", "description": "updated"},
        headers=headers,
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["data"]["name"] == "管理测试-更新-B2"

    list_resp = client.get("/api/v1/suites", params={"version_key": "v1.0.0"}, headers=headers)
    assert list_resp.status_code == 200
    suite_names = {item["suite_key"]: item["name"] for item in list_resp.json()["data"]}
    assert suite_names[suite_a_key] == "管理测试-更新-A"
    assert suite_names[suite_b_key] == "管理测试-更新-B2"


def test_seed_has_no_default_suite(client: TestClient, auth_headers):
    headers = auth_headers("qa")

    list_resp = client.get("/api/v1/suites", params={"version_key": "v1.0.0"}, headers=headers)
    assert list_resp.status_code == 200
    assert all(item["name"] != "默认用例集" for item in list_resp.json()["data"])


def test_delete_suite_blocked_when_selected_version_has_issue_linked_cases(client: TestClient, auth_headers):
    headers = auth_headers("qa")
    suite_key, suite_version_key = _create_suite(client, headers, name="管理测试-删除-问题单拦截", case_keys=["TC-002"])

    delete_resp = client.delete(
        f"/api/v1/suites/{suite_key}",
        params={"suite_version_key": suite_version_key},
        headers=headers,
    )
    assert delete_resp.status_code == 422
    assert "blocked_case_keys" in delete_resp.json()["error"]["details"]


def test_delete_suite_blocked_when_referenced_by_plan(client: TestClient, auth_headers):
    headers = auth_headers("qa")
    suite_key, suite_version_key = _create_suite(client, headers, name="管理测试-删除-计划引用", case_keys=["TC-001"])

    publish_resp = client.post(f"/api/v1/suites/{suite_key}/versions/{suite_version_key}/publish", headers=headers)
    assert publish_resp.status_code == 200

    create_plan_resp = client.post(
        "/api/v1/plans",
        json={
            "version_key": "v1.0.0",
            "suite_version_key": suite_version_key,
            "name": "管理测试-计划引用",
            "description": "plan ref",
        },
        headers=headers,
    )
    assert create_plan_resp.status_code == 200

    delete_resp = client.delete(
        f"/api/v1/suites/{suite_key}",
        params={"suite_version_key": suite_version_key},
        headers=headers,
    )
    assert delete_resp.status_code == 422


def test_delete_suite_success_without_issue_or_plan(client: TestClient, auth_headers):
    headers = auth_headers("qa")
    suite_key, suite_version_key = _create_suite(client, headers, name="管理测试-删除-成功", case_keys=["TC-001"])

    delete_resp = client.delete(
        f"/api/v1/suites/{suite_key}",
        params={"suite_version_key": suite_version_key},
        headers=headers,
    )
    assert delete_resp.status_code == 200

    list_resp = client.get("/api/v1/suites", params={"version_key": "v1.0.0"}, headers=headers)
    assert list_resp.status_code == 200
    suite_keys = {item["suite_key"] for item in list_resp.json()["data"]}
    assert suite_key not in suite_keys


def test_remove_suite_cases_checks_issue_binding_and_published_status(client: TestClient, auth_headers):
    headers = auth_headers("qa")
    suite_key, suite_version_key = _create_suite(
        client,
        headers,
        name="管理测试-移除用例",
        case_keys=["TC-001", "TC-002"],
    )

    remove_unlinked_resp = client.post(
        f"/api/v1/suites/{suite_key}/versions/{suite_version_key}/cases:remove",
        json={"case_keys": ["TC-001"]},
        headers=headers,
    )
    assert remove_unlinked_resp.status_code == 200

    remove_linked_resp = client.post(
        f"/api/v1/suites/{suite_key}/versions/{suite_version_key}/cases:remove",
        json={"case_keys": ["TC-002"]},
        headers=headers,
    )
    assert remove_linked_resp.status_code == 422
    assert "blocked_case_keys" in remove_linked_resp.json()["error"]["details"]

    publish_resp = client.post(f"/api/v1/suites/{suite_key}/versions/{suite_version_key}/publish", headers=headers)
    assert publish_resp.status_code == 200

    remove_after_publish_resp = client.post(
        f"/api/v1/suites/{suite_key}/versions/{suite_version_key}/cases:remove",
        json={"case_keys": ["TC-002"]},
        headers=headers,
    )
    assert remove_after_publish_resp.status_code == 422
    assert "仅草稿版本可编辑用例" in remove_after_publish_resp.json()["error"]["message"]
