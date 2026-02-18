from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import (
    CaseSuite,
    CaseSuiteVersion,
    IssueCaseLink,
    SuiteCaseRef,
    SuiteVersionStatus,
    TestCase,
    TestPlan,
    UserAccount,
    UserRole,
    get_db,
)
from ..errors import AppError
from ..response import success_response
from ..schemas import (
    SuiteCreateRequest,
    SuiteUpdateRequest,
    SuiteVersionCaseBatchRequest,
    SuiteVersionCreateRequest,
)
from ..services import (
    find_case_by_key,
    find_suite_by_key,
    find_suite_version_by_key,
    find_version_by_key,
    generate_suite_key,
    generate_suite_version_key,
    write_audit,
)

router = APIRouter(prefix="/api/v1/suites", tags=["suites"])


def _ensure_suite_editor(user: UserAccount) -> None:
    if user.role not in {UserRole.admin, UserRole.qa}:
        raise AppError("FORBIDDEN", "仅管理员或 QA 可维护用例集", status_code=403)


def _suite_versions_payload(db: Session, suite: CaseSuite) -> list[dict]:
    versions = (
        db.query(CaseSuiteVersion)
        .filter(CaseSuiteVersion.suite_id == suite.id)
        .order_by(CaseSuiteVersion.ver_no.desc())
        .all()
    )
    payload: list[dict] = []
    for item in versions:
        case_count = db.query(func.count(SuiteCaseRef.id)).filter(SuiteCaseRef.suite_version_id == item.id).scalar() or 0
        payload.append(
            {
                "suite_version_key": item.suite_version_key,
                "suite_key": suite.suite_key,
                "ver_no": item.ver_no,
                "status": item.status,
                "note": item.note,
                "case_count": int(case_count),
                "created_at": item.created_at,
                "published_at": item.published_at,
            }
        )
    return payload


@router.get("")
def list_suites(
    request: Request,
    version_key: str,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(get_current_user),
):
    version = find_version_by_key(db, version_key)
    suites = (
        db.query(CaseSuite)
        .filter(CaseSuite.version_id == version.id)
        .order_by(CaseSuite.updated_at.desc(), CaseSuite.id.desc())
        .all()
    )
    data = [
        {
            "suite_key": suite.suite_key,
            "version_key": version.version_key,
            "name": suite.name,
            "description": suite.description,
            "created_at": suite.created_at,
            "updated_at": suite.updated_at,
            "versions": _suite_versions_payload(db, suite),
        }
        for suite in suites
    ]
    return success_response(request, data)


@router.post("")
def create_suite(
    payload: SuiteCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    _ensure_suite_editor(current_user)

    version = find_version_by_key(db, payload.version_key)
    name = payload.name.strip()
    if not name:
        raise AppError("VALIDATION_ERROR", "用例集名称不能为空", status_code=422)

    duplicate = (
        db.query(CaseSuite)
        .filter(CaseSuite.version_id == version.id, CaseSuite.name == name)
        .first()
    )
    if duplicate:
        raise AppError("VALIDATION_ERROR", f"用例集已存在: {name}", status_code=422)

    suite = CaseSuite(
        suite_key=generate_suite_key(db),
        version_id=version.id,
        name=name,
        description=payload.description,
        created_by=current_user.id,
    )
    db.add(suite)
    db.flush()

    suite_version = CaseSuiteVersion(
        suite_version_key=generate_suite_version_key(db),
        suite_id=suite.id,
        ver_no=1,
        status=SuiteVersionStatus.draft,
        note="初始草稿版本",
        created_by=current_user.id,
    )
    db.add(suite_version)
    db.flush()

    if payload.case_keys:
        ordered_unique_keys = list(dict.fromkeys(payload.case_keys))
        cases = [find_case_by_key(db, case_key) for case_key in ordered_unique_keys]
    else:
        cases = []

    for index, test_case in enumerate(cases, start=1):
        db.add(
            SuiteCaseRef(
                suite_version_id=suite_version.id,
                case_id=test_case.id,
                order_no=index,
                module_path_snapshot=test_case.module,
            )
        )

    write_audit(
        db,
        current_user.id,
        action="suite.create",
        object_type="case_suite",
        object_id=suite.suite_key,
        diff={"version_key": version.version_key, "name": suite.name, "initial_cases": len(cases)},
    )

    db.commit()

    return success_response(
        request,
        {
            "suite_key": suite.suite_key,
            "version_key": version.version_key,
            "name": suite.name,
            "description": suite.description,
            "created_at": suite.created_at,
            "updated_at": suite.updated_at,
            "versions": _suite_versions_payload(db, suite),
        },
    )


@router.put("/{suite_key}")
def update_suite(
    suite_key: str,
    payload: SuiteUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    _ensure_suite_editor(current_user)

    suite = find_suite_by_key(db, suite_key)
    name = payload.name.strip()
    if not name:
        raise AppError("VALIDATION_ERROR", "用例集名称不能为空", status_code=422)

    duplicate = (
        db.query(CaseSuite)
        .filter(
            CaseSuite.version_id == suite.version_id,
            CaseSuite.name == name,
            CaseSuite.id != suite.id,
        )
        .first()
    )
    if duplicate:
        raise AppError("VALIDATION_ERROR", f"同版本下用例集名称重复: {name}", status_code=422)

    before = {"name": suite.name, "description": suite.description}
    suite.name = name
    suite.description = payload.description
    suite.updated_at = datetime.utcnow()

    write_audit(
        db,
        current_user.id,
        action="suite.update",
        object_type="case_suite",
        object_id=suite.suite_key,
        diff={"before": before, "after": {"name": suite.name, "description": suite.description}},
    )

    db.commit()
    return success_response(
        request,
        {
            "suite_key": suite.suite_key,
            "version_key": suite.version.version_key,
            "name": suite.name,
            "description": suite.description,
            "created_at": suite.created_at,
            "updated_at": suite.updated_at,
            "versions": _suite_versions_payload(db, suite),
        },
    )


@router.delete("/{suite_key}")
def delete_suite(
    suite_key: str,
    suite_version_key: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    _ensure_suite_editor(current_user)

    suite = find_suite_by_key(db, suite_key)

    suite_version = find_suite_version_by_key(db, suite_version_key)
    if suite_version.suite_id != suite.id:
        raise AppError("VALIDATION_ERROR", "用例集版本不属于目标用例集", status_code=422)

    blocked_case_rows = (
        db.query(TestCase.case_key)
        .join(SuiteCaseRef, SuiteCaseRef.case_id == TestCase.id)
        .join(IssueCaseLink, IssueCaseLink.case_id == TestCase.id)
        .filter(SuiteCaseRef.suite_version_id == suite_version.id)
        .distinct()
        .order_by(TestCase.case_key.asc())
        .all()
    )
    if blocked_case_rows:
        blocked_case_keys = [row.case_key for row in blocked_case_rows]
        raise AppError(
            "VALIDATION_ERROR",
            f"当前版本存在问题单绑定用例，禁止删除用例集: {', '.join(blocked_case_keys[:10])}",
            status_code=422,
            details={"blocked_case_keys": blocked_case_keys},
        )

    has_plan = (
        db.query(TestPlan.id)
        .join(CaseSuiteVersion, CaseSuiteVersion.id == TestPlan.suite_version_id)
        .filter(CaseSuiteVersion.suite_id == suite.id)
        .first()
        is not None
    )
    if has_plan:
        raise AppError("VALIDATION_ERROR", "用例集已被测试计划引用，禁止删除", status_code=422)

    suite_version_ids = [row.id for row in db.query(CaseSuiteVersion.id).filter(CaseSuiteVersion.suite_id == suite.id).all()]
    if suite_version_ids:
        (
            db.query(SuiteCaseRef)
            .filter(SuiteCaseRef.suite_version_id.in_(suite_version_ids))
            .delete(synchronize_session=False)
        )
        (
            db.query(CaseSuiteVersion)
            .filter(CaseSuiteVersion.id.in_(suite_version_ids))
            .delete(synchronize_session=False)
        )

    write_audit(
        db,
        current_user.id,
        action="suite.delete",
        object_type="case_suite",
        object_id=suite.suite_key,
        diff={"suite_version_key": suite_version_key},
    )

    db.delete(suite)
    db.commit()
    return success_response(request, {"suite_key": suite_key, "deleted": True})


@router.get("/{suite_key}/versions/{suite_version_key}")
def get_suite_version_detail(
    suite_key: str,
    suite_version_key: str,
    request: Request,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(get_current_user),
):
    suite = find_suite_by_key(db, suite_key)
    suite_version = find_suite_version_by_key(db, suite_version_key)
    if suite_version.suite_id != suite.id:
        raise AppError("VALIDATION_ERROR", "用例集版本不属于目标用例集", status_code=422)

    rows = (
        db.query(SuiteCaseRef, TestCase)
        .join(TestCase, TestCase.id == SuiteCaseRef.case_id)
        .filter(SuiteCaseRef.suite_version_id == suite_version.id)
        .order_by(SuiteCaseRef.order_no.asc(), TestCase.case_key.asc())
        .all()
    )
    case_ids = [test_case.id for _, test_case in rows]
    issue_linked_case_ids = set()
    if case_ids:
        issue_linked_case_ids = {
            row.case_id
            for row in (
                db.query(IssueCaseLink.case_id)
                .filter(IssueCaseLink.case_id.in_(case_ids))
                .distinct()
                .all()
            )
        }
    cases = [
        {
            "case_key": test_case.case_key,
            "title": test_case.title,
            "module": ref.module_path_snapshot or test_case.module,
            "status": test_case.status,
            "issue_linked": test_case.id in issue_linked_case_ids,
        }
        for ref, test_case in rows
    ]

    return success_response(
        request,
        {
            "suite_key": suite.suite_key,
            "name": suite.name,
            "description": suite.description,
            "suite_version": {
                "suite_version_key": suite_version.suite_version_key,
                "ver_no": suite_version.ver_no,
                "status": suite_version.status,
                "note": suite_version.note,
                "case_count": len(cases),
                "created_at": suite_version.created_at,
                "published_at": suite_version.published_at,
            },
            "cases": cases,
        },
    )


@router.post("/{suite_key}/versions")
def create_suite_version(
    suite_key: str,
    payload: SuiteVersionCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    _ensure_suite_editor(current_user)

    suite = find_suite_by_key(db, suite_key)
    latest = (
        db.query(CaseSuiteVersion)
        .filter(CaseSuiteVersion.suite_id == suite.id)
        .order_by(CaseSuiteVersion.ver_no.desc())
        .first()
    )
    if not latest:
        raise AppError("VALIDATION_ERROR", "当前用例集缺少基础版本", status_code=422)

    next_ver_no = latest.ver_no + 1
    suite_version = CaseSuiteVersion(
        suite_version_key=generate_suite_version_key(db),
        suite_id=suite.id,
        ver_no=next_ver_no,
        status=SuiteVersionStatus.draft,
        note=payload.note,
        created_by=current_user.id,
    )
    db.add(suite_version)
    db.flush()

    rows = (
        db.query(SuiteCaseRef)
        .filter(SuiteCaseRef.suite_version_id == latest.id)
        .order_by(SuiteCaseRef.order_no.asc(), SuiteCaseRef.id.asc())
        .all()
    )
    for row in rows:
        db.add(
            SuiteCaseRef(
                suite_version_id=suite_version.id,
                case_id=row.case_id,
                order_no=row.order_no,
                module_path_snapshot=row.module_path_snapshot,
            )
        )

    write_audit(
        db,
        current_user.id,
        action="suite.version.derive",
        object_type="case_suite_version",
        object_id=suite_version.suite_version_key,
        diff={"suite_key": suite.suite_key, "base_version": latest.suite_version_key, "ver_no": next_ver_no},
    )

    db.commit()

    return success_response(
        request,
        {
            "suite_version_key": suite_version.suite_version_key,
            "suite_key": suite.suite_key,
            "ver_no": suite_version.ver_no,
            "status": suite_version.status,
            "note": suite_version.note,
            "case_count": db.query(func.count(SuiteCaseRef.id)).filter(SuiteCaseRef.suite_version_id == suite_version.id).scalar() or 0,
            "created_at": suite_version.created_at,
            "published_at": suite_version.published_at,
        },
    )


@router.post("/{suite_key}/versions/{suite_version_key}/cases:add")
def add_suite_cases(
    suite_key: str,
    suite_version_key: str,
    payload: SuiteVersionCaseBatchRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    _ensure_suite_editor(current_user)
    suite = find_suite_by_key(db, suite_key)
    suite_version = find_suite_version_by_key(db, suite_version_key)
    if suite_version.suite_id != suite.id:
        raise AppError("VALIDATION_ERROR", "用例集版本不属于目标用例集", status_code=422)
    if suite_version.status != SuiteVersionStatus.draft:
        raise AppError("VALIDATION_ERROR", "仅草稿版本可编辑用例", status_code=422)

    existing_case_ids = {
        row.case_id for row in db.query(SuiteCaseRef.case_id).filter(SuiteCaseRef.suite_version_id == suite_version.id).all()
    }
    order_no = db.query(func.count(SuiteCaseRef.id)).filter(SuiteCaseRef.suite_version_id == suite_version.id).scalar() or 0
    inserted = 0
    for case_key in dict.fromkeys(payload.case_keys):
        test_case = find_case_by_key(db, case_key)
        if test_case.id in existing_case_ids:
            continue
        order_no += 1
        db.add(
            SuiteCaseRef(
                suite_version_id=suite_version.id,
                case_id=test_case.id,
                order_no=order_no,
                module_path_snapshot=test_case.module,
            )
        )
        inserted += 1

    suite.updated_at = datetime.utcnow()

    write_audit(
        db,
        current_user.id,
        action="suite.version.cases.add",
        object_type="case_suite_version",
        object_id=suite_version.suite_version_key,
        diff={"added": inserted, "requested": len(payload.case_keys)},
    )

    db.commit()
    return success_response(request, {"suite_version_key": suite_version.suite_version_key, "added": inserted})


@router.post("/{suite_key}/versions/{suite_version_key}/cases:remove")
def remove_suite_cases(
    suite_key: str,
    suite_version_key: str,
    payload: SuiteVersionCaseBatchRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    _ensure_suite_editor(current_user)
    suite = find_suite_by_key(db, suite_key)
    suite_version = find_suite_version_by_key(db, suite_version_key)
    if suite_version.suite_id != suite.id:
        raise AppError("VALIDATION_ERROR", "用例集版本不属于目标用例集", status_code=422)
    if suite_version.status != SuiteVersionStatus.draft:
        raise AppError("VALIDATION_ERROR", "仅草稿版本可编辑用例", status_code=422)

    requested_cases = [find_case_by_key(db, case_key) for case_key in dict.fromkeys(payload.case_keys)]
    requested_case_ids = {item.id for item in requested_cases}
    requested_case_key_by_id = {item.id: item.case_key for item in requested_cases}

    suite_case_ids = {
        row.case_id
        for row in db.query(SuiteCaseRef.case_id).filter(SuiteCaseRef.suite_version_id == suite_version.id).all()
    }
    target_case_ids = list(requested_case_ids.intersection(suite_case_ids))

    blocked_case_ids = {
        row.case_id
        for row in (
            db.query(IssueCaseLink.case_id)
            .filter(IssueCaseLink.case_id.in_(target_case_ids))
            .distinct()
            .all()
        )
    }
    if blocked_case_ids:
        blocked_case_keys = sorted(
            requested_case_key_by_id.get(case_id, str(case_id)) for case_id in blocked_case_ids
        )
        raise AppError(
            "VALIDATION_ERROR",
            f"以下用例已绑定问题单，禁止移除: {', '.join(blocked_case_keys)}",
            status_code=422,
            details={"blocked_case_keys": blocked_case_keys},
        )

    deleted = (
        db.query(SuiteCaseRef)
        .filter(SuiteCaseRef.suite_version_id == suite_version.id, SuiteCaseRef.case_id.in_(target_case_ids))
        .delete(synchronize_session=False)
    )

    suite.updated_at = datetime.utcnow()

    write_audit(
        db,
        current_user.id,
        action="suite.version.cases.remove",
        object_type="case_suite_version",
        object_id=suite_version.suite_version_key,
        diff={"removed": int(deleted or 0), "requested": len(payload.case_keys)},
    )

    db.commit()
    return success_response(request, {"suite_version_key": suite_version.suite_version_key, "removed": int(deleted or 0)})


@router.post("/{suite_key}/versions/{suite_version_key}/publish")
def publish_suite_version(
    suite_key: str,
    suite_version_key: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    _ensure_suite_editor(current_user)
    suite = find_suite_by_key(db, suite_key)
    suite_version = find_suite_version_by_key(db, suite_version_key)
    if suite_version.suite_id != suite.id:
        raise AppError("VALIDATION_ERROR", "用例集版本不属于目标用例集", status_code=422)

    suite_version.status = SuiteVersionStatus.published
    suite_version.published_by = current_user.id
    suite_version.published_at = datetime.utcnow()
    suite.updated_at = datetime.utcnow()

    write_audit(
        db,
        current_user.id,
        action="suite.version.publish",
        object_type="case_suite_version",
        object_id=suite_version.suite_version_key,
        diff={"status": "published"},
    )

    db.commit()

    return success_response(
        request,
        {
            "suite_version_key": suite_version.suite_version_key,
            "suite_key": suite.suite_key,
            "ver_no": suite_version.ver_no,
            "status": suite_version.status,
            "note": suite_version.note,
            "case_count": db.query(func.count(SuiteCaseRef.id)).filter(SuiteCaseRef.suite_version_id == suite_version.id).scalar() or 0,
            "created_at": suite_version.created_at,
            "published_at": suite_version.published_at,
        },
    )
