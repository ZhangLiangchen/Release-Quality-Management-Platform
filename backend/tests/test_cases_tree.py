from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, TestCase, TestCaseStatus, Version, VersionCaseStatus
from app.seed import seed_database
from app.services import cleanup_placeholder_cases


def _build_isolated_session_factory(db_path: Path):
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    local_session = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    session = local_session()
    try:
        seed_database(session)
    finally:
        session.close()
    return engine, local_session


def test_get_case_tree_returns_hierarchy_and_backfills_legacy(client: TestClient, auth_headers, db_session: Session):
    headers = auth_headers("qa")
    resp = client.get("/api/v1/case-tree", params={"version_key": "v1.0.0"}, headers=headers)
    assert resp.status_code == 200

    data = resp.json()["data"]
    assert data["version_key"] == "v1.0.0"
    assert isinstance(data["tree"], list)
    assert len(data["tree"]) > 0

    seed_case = db_session.query(TestCase).filter(TestCase.case_key == "TC-001").first()
    assert seed_case is not None
    assert seed_case.tree_node_id is not None


def test_create_case_tree_node_success_duplicate_and_forbidden(client: TestClient, auth_headers):
    headers = auth_headers("qa")
    payload = {
        "version_key": "v1.0.0",
        "name": "手工目录",
        "node_type": "directory",
    }

    create_resp = client.post("/api/v1/case-tree/nodes", json=payload, headers=headers)
    assert create_resp.status_code == 200
    node_id = create_resp.json()["data"]["node_id"]
    assert node_id

    duplicate_resp = client.post("/api/v1/case-tree/nodes", json=payload, headers=headers)
    assert duplicate_resp.status_code == 422
    assert duplicate_resp.json()["error"]["code"] == "VALIDATION_ERROR"

    viewer_headers = auth_headers("viewer")
    forbid_resp = client.post("/api/v1/case-tree/nodes", json=payload, headers=viewer_headers)
    assert forbid_resp.status_code == 403
    assert forbid_resp.json()["error"]["code"] == "FORBIDDEN"


def test_create_case_and_keep_version_status_matrix(client: TestClient, auth_headers, db_session: Session):
    headers = auth_headers("qa")

    dir_resp = client.post(
        "/api/v1/case-tree/nodes",
        json={"version_key": "v1.0.0", "name": "文本用例", "node_type": "directory"},
        headers=headers,
    )
    assert dir_resp.status_code == 200
    dir_node_id = dir_resp.json()["data"]["node_id"]

    file_resp = client.post(
        "/api/v1/case-tree/nodes",
        json={
            "version_key": "v1.0.0",
            "parent_node_id": dir_node_id,
            "name": "manual_suite",
            "node_type": "file",
        },
        headers=headers,
    )
    assert file_resp.status_code == 200
    file_node_id = file_resp.json()["data"]["node_id"]

    create_case_resp = client.post(
        "/api/v1/cases",
        json={
            "version_key": "v1.0.0",
            "parent_node_id": file_node_id,
            "case_key": "HS-MANUAL-001",
            "title": "手工新增用例",
            "steps": "执行步骤",
            "expected": "预期通过",
            "tags": ["manual"],
        },
        headers=headers,
    )
    assert create_case_resp.status_code == 200

    duplicate_resp = client.post(
        "/api/v1/cases",
        json={
            "version_key": "v1.0.0",
            "parent_node_id": file_node_id,
            "case_key": "HS-MANUAL-001",
            "title": "重复用例",
            "steps": "步骤",
            "expected": "预期",
            "tags": [],
        },
        headers=headers,
    )
    assert duplicate_resp.status_code == 422
    assert duplicate_resp.json()["error"]["code"] == "VALIDATION_ERROR"

    created_case = db_session.query(TestCase).filter(TestCase.case_key == "HS-MANUAL-001").first()
    assert created_case is not None

    versions = db_session.query(Version).all()
    for version in versions:
        rows = (
            db_session.query(VersionCaseStatus)
            .filter(VersionCaseStatus.version_id == version.id, VersionCaseStatus.case_id == created_case.id)
            .all()
        )
        assert len(rows) == 1


def test_update_and_delete_case(client: TestClient, auth_headers, db_session: Session):
    headers = auth_headers("qa")

    tree_resp = client.get("/api/v1/case-tree", params={"version_key": "v1.0.0"}, headers=headers)
    assert tree_resp.status_code == 200
    tree = tree_resp.json()["data"]["tree"]
    first_node = tree[0]
    parent_node_id = first_node["node_id"]
    if first_node["node_type"] == "directory" and first_node["children"]:
        parent_node_id = first_node["children"][0]["node_id"]

    update_resp = client.put(
        "/api/v1/cases/TC-001",
        json={
            "parent_node_id": parent_node_id,
            "title": "用户登录成功-更新",
            "steps": "更新步骤",
            "expected": "更新预期",
            "tags": ["p0", "smoke"],
        },
        headers=headers,
    )
    assert update_resp.status_code == 200

    updated = db_session.query(TestCase).filter(TestCase.case_key == "TC-001").first()
    assert updated is not None
    assert updated.title == "用户登录成功-更新"
    assert updated.steps == "更新步骤"
    assert updated.expected == "更新预期"
    assert updated.status == TestCaseStatus.active

    delete_resp = client.delete("/api/v1/cases/TC-001", headers=headers)
    assert delete_resp.status_code == 200

    deleted = db_session.query(TestCase).filter(TestCase.case_key == "TC-001").first()
    assert deleted is not None
    assert deleted.status == TestCaseStatus.deprecated


def test_cleanup_placeholder_cases_only_removes_seed_placeholders(tmp_path: Path):
    db_path = tmp_path / "cleanup.db"
    engine, local_session = _build_isolated_session_factory(db_path)
    try:
        session = local_session()
        try:
            before = session.query(TestCase).count()
            stats = cleanup_placeholder_cases(session)
            session.commit()
            after = session.query(TestCase).count()
            assert stats["deleted_cases"] > 0
            assert after < before
            remaining_keys = {item.case_key for item in session.query(TestCase).all()}
            assert "TC-001" not in remaining_keys
            assert "TC-002" not in remaining_keys
        finally:
            session.close()
    finally:
        engine.dispose()


def test_bootstrap_case_library_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from scripts import bootstrap_case_library

    db_path = tmp_path / "bootstrap.db"
    engine, local_session = _build_isolated_session_factory(db_path)
    case_json = tmp_path / "cases.json"
    case_json.write_text(
        json.dumps(
            [
                {
                    "case_key": "HS-BOOT-001",
                    "title": "bootstrap 用例",
                    "module": "bootstrap/demo",
                    "steps": "步骤",
                    "expected": "预期",
                    "tags": ["bootstrap"],
                    "tree_segments": ["bootstrap", "demo", "suite_file"],
                    "source": "bootstrap/demo/test_demo.py::test_bootstrap",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(bootstrap_case_library, "SessionLocal", local_session)

    try:
        bootstrap_case_library.upsert_cases(case_json)
        bootstrap_case_library.upsert_cases(case_json)

        verify_session = local_session()
        try:
            rows = verify_session.query(TestCase).filter(TestCase.case_key == "HS-BOOT-001").all()
            assert len(rows) == 1
        finally:
            verify_session.close()
    finally:
        engine.dispose()
