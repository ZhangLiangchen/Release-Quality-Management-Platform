from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import CaseSetSnapshot, CaseStatusHistory, TestCase as TestCaseModel, Version, VersionCaseStatus


def test_create_version_generates_snapshot_and_default_status(client: TestClient, auth_headers, db_session: Session):
    headers = auth_headers("qa")
    resp = client.post("/api/v1/versions", json={"version_key": "v2.0.0"}, headers=headers)
    assert resp.status_code == 200

    version = db_session.query(Version).filter(Version.version_key == "v2.0.0").first()
    assert version is not None

    snapshot = db_session.query(CaseSetSnapshot).filter(CaseSetSnapshot.version_id == version.id).first()
    assert snapshot is not None

    case_count = db_session.query(TestCaseModel).count()
    status_count = (
        db_session.query(VersionCaseStatus)
        .filter(
            VersionCaseStatus.version_id == version.id,
            VersionCaseStatus.snapshot_id == snapshot.id,
        )
        .count()
    )
    assert status_count == case_count


def test_update_case_status_writes_history(client: TestClient, auth_headers, db_session: Session):
    headers = auth_headers("qa")
    resp = client.put(
        "/api/v1/versions/v1.0.0/cases/TC-001/status",
        json={"status": "failed", "note": "回归失败", "attachments": []},
        headers=headers,
    )
    assert resp.status_code == 200

    history = (
        db_session.query(CaseStatusHistory)
        .join(TestCaseModel, TestCaseModel.id == CaseStatusHistory.case_id)
        .filter(CaseStatusHistory.version_id == 1, TestCaseModel.case_key == "TC-001")
        .order_by(CaseStatusHistory.id.desc())
        .first()
    )
    assert history is not None
    assert history.status.value == "failed"
