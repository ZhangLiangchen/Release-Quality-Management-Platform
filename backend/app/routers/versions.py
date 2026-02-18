from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import (
    CaseStatusHistory,
    Issue,
    ProjectConfig,
    TestCase,
    UserAccount,
    UserRole,
    Version,
    get_db,
)
from ..errors import AppError
from ..response import success_response
from ..schemas import VersionCreateRequest, VersionOut
from ..services import (
    ensure_version_case_status_rows,
    find_version_by_key,
    get_or_create_default_snapshot,
    make_snapshot_payload,
    write_audit,
)

router = APIRouter(prefix="/api/v1/versions", tags=["versions"])


@router.get("")
def list_versions(request: Request, db: Session = Depends(get_db), _: UserAccount = Depends(get_current_user)):
    versions = db.query(Version).order_by(Version.created_at.asc()).all()
    data = [
        VersionOut(
            version_key=version.version_key,
            name=version.name,
            is_current=version.is_current,
            created_at=version.created_at,
        ).model_dump()
        for version in versions
    ]
    return success_response(request, data)


@router.post("")
def create_version(
    payload: VersionCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    if current_user.role not in {UserRole.admin, UserRole.qa}:
        raise AppError("FORBIDDEN", "仅管理员或 QA 可新增版本", status_code=403)

    version_key = payload.version_key.strip()
    if not version_key:
        raise AppError("VALIDATION_ERROR", "version_key 不能为空", status_code=422)
    if db.query(Version).filter(Version.version_key == version_key).first():
        raise AppError("VALIDATION_ERROR", "版本号已存在", status_code=422)

    version = Version(version_key=version_key, name=version_key, is_current=False)
    db.add(version)
    db.flush()

    snapshot = get_or_create_default_snapshot(db, version, current_user.id)
    case_keys = [row.case_key for row in db.query(TestCase.case_key).filter(TestCase.status == "active").all()]
    ensure_version_case_status_rows(db, version, snapshot, current_user.id)
    snapshot.snapshot_json = make_snapshot_payload(version.version_key, case_keys, "create version")

    write_audit(
        db,
        current_user.id,
        action="version.create",
        object_type="version",
        object_id=version.version_key,
        diff={"version_key": version.version_key, "snapshot_id": snapshot.snapshot_id},
    )

    db.commit()
    db.refresh(version)

    data = VersionOut(
        version_key=version.version_key,
        name=version.name,
        is_current=version.is_current,
        created_at=version.created_at,
    )
    return success_response(request, data.model_dump())


@router.post("/{version_key}:set-current")
def set_current_version(
    version_key: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    if current_user.role not in {UserRole.admin, UserRole.qa}:
        raise AppError("FORBIDDEN", "仅管理员或 QA 可设置系统当前版本", status_code=403)

    version = find_version_by_key(db, version_key)
    db.query(Version).update({Version.is_current: False})
    version.is_current = True

    config = db.query(ProjectConfig).first()
    if not config:
        config = ProjectConfig(project_name="测试管理系统", current_version_id=version.id)
        db.add(config)
    else:
        config.current_version_id = version.id

    write_audit(
        db,
        current_user.id,
        action="version.set_current",
        object_type="version",
        object_id=version.version_key,
        diff={"is_current": True},
    )
    db.commit()
    return success_response(request, {"version_key": version.version_key, "is_current": True})


@router.delete("/{version_key}")
def delete_version(
    version_key: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    if current_user.role not in {UserRole.admin, UserRole.qa}:
        raise AppError("FORBIDDEN", "仅管理员或 QA 可删除版本", status_code=403)

    version = find_version_by_key(db, version_key)
    if version.is_current:
        raise AppError("VALIDATION_ERROR", "当前版本不可删除", status_code=422)

    has_case_history = (
        db.query(CaseStatusHistory)
        .filter(CaseStatusHistory.version_id == version.id)
        .first()
        is not None
    )
    has_issue_data = (
        db.query(Issue)
        .filter(
            (Issue.found_version_id == version.id)
            | (Issue.fix_version_id == version.id)
            | (Issue.verify_version_id == version.id)
        )
        .first()
        is not None
    )
    if has_case_history or has_issue_data:
        raise AppError("VALIDATION_ERROR", "版本下存在执行或问题单数据，禁止删除", status_code=422)

    db.delete(version)
    write_audit(
        db,
        current_user.id,
        action="version.delete",
        object_type="version",
        object_id=version_key,
        diff={},
    )
    db.commit()
    return success_response(request, {"version_key": version_key, "deleted": True})
