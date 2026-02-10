from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import (
    CaseStatus,
    CaseStatusHistory,
    TestCase,
    TestCaseStatus,
    UserAccount,
    UserRole,
    Version,
    VersionCaseStatus,
    get_db,
)
from ..errors import AppError
from ..response import success_response
from ..schemas import CaseDetailOut, CaseStatusUpdateRequest, ImportValidateOut
from ..services import (
    as_csv_response,
    as_xlsx_response,
    build_case_history_rows,
    build_case_module_rows,
    ensure_version_case_status_rows,
    find_case_by_key,
    find_version_by_key,
    get_or_create_default_snapshot,
    parse_import_rows,
    validate_required_columns,
    write_audit,
)

router = APIRouter(tags=["cases"])


@router.get("/api/v1/cases")
def list_cases(
    request: Request,
    version_key: str,
    group_by: str = "module",
    db: Session = Depends(get_db),
    _: UserAccount = Depends(get_current_user),
):
    if group_by != "module":
        raise AppError("VALIDATION_ERROR", "P0 仅支持 group_by=module", status_code=422)

    version = find_version_by_key(db, version_key)
    snapshot = get_or_create_default_snapshot(db, version)
    ensure_version_case_status_rows(db, version, snapshot, None)
    db.commit()

    data = build_case_module_rows(db, version)
    return success_response(request, data)


@router.get("/api/v1/cases/{case_key}")
def case_detail(
    case_key: str,
    request: Request,
    version_key: str,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(get_current_user),
):
    version = find_version_by_key(db, version_key)
    test_case = find_case_by_key(db, case_key)
    snapshot = get_or_create_default_snapshot(db, version)
    ensure_version_case_status_rows(db, version, snapshot, None)

    status_row = (
        db.query(VersionCaseStatus)
        .filter(
            VersionCaseStatus.version_id == version.id,
            VersionCaseStatus.snapshot_id == snapshot.id,
            VersionCaseStatus.case_id == test_case.id,
        )
        .first()
    )
    if not status_row:
        status_row = VersionCaseStatus(
            version_id=version.id,
            snapshot_id=snapshot.id,
            case_id=test_case.id,
            status=CaseStatus.not_run,
        )
        db.add(status_row)
        db.flush()

    detail = CaseDetailOut(
        case_key=test_case.case_key,
        title=test_case.title,
        module=test_case.module,
        steps=test_case.steps,
        expected=test_case.expected,
        tags=test_case.tags_json,
        latest_status=status_row.status,
    )

    history = build_case_history_rows(db, version.id, test_case.id)
    return success_response(
        request,
        {
            "case_info": detail.model_dump(),
            "history": history,
        },
    )


@router.put("/api/v1/versions/{version_key}/cases/{case_key}/status")
def update_case_status(
    version_key: str,
    case_key: str,
    payload: CaseStatusUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    if current_user.role not in {UserRole.admin, UserRole.qa}:
        raise AppError("FORBIDDEN", "仅管理员或 QA 可更新用例状态", status_code=403)

    version = find_version_by_key(db, version_key)
    test_case = find_case_by_key(db, case_key)
    snapshot = get_or_create_default_snapshot(db, version, current_user.id)
    ensure_version_case_status_rows(db, version, snapshot, current_user.id)

    status_row = (
        db.query(VersionCaseStatus)
        .filter(
            VersionCaseStatus.version_id == version.id,
            VersionCaseStatus.snapshot_id == snapshot.id,
            VersionCaseStatus.case_id == test_case.id,
        )
        .first()
    )
    if not status_row:
        status_row = VersionCaseStatus(
            version_id=version.id,
            snapshot_id=snapshot.id,
            case_id=test_case.id,
            status=CaseStatus.not_run,
        )
        db.add(status_row)

    before_status = status_row.status
    status_row.status = payload.status
    status_row.note = payload.note
    status_row.updated_by = current_user.id

    db.add(
        CaseStatusHistory(
            version_id=version.id,
            case_id=test_case.id,
            status=payload.status,
            executor_id=current_user.id,
            note=payload.note,
            attachments_json=[attachment.model_dump() for attachment in payload.attachments],
        )
    )

    write_audit(
        db,
        current_user.id,
        action="case.status.update",
        object_type="version_case_status",
        object_id=f"{version_key}:{case_key}",
        diff={"before": before_status.value, "after": payload.status.value},
    )

    db.commit()
    return success_response(request, {"version_key": version_key, "case_key": case_key, "status": payload.status})


@router.get("/api/v1/versions/{version_key}/cases/{case_key}/history")
def case_history(
    version_key: str,
    case_key: str,
    request: Request,
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    _: UserAccount = Depends(get_current_user),
):
    version = find_version_by_key(db, version_key)
    test_case = find_case_by_key(db, case_key)
    data = build_case_history_rows(db, version.id, test_case.id, limit=limit)
    return success_response(request, data)


@router.post("/api/v1/cases:import")
async def import_cases(
    request: Request,
    file: UploadFile = File(...),
    mode: str = Query("upsert"),
    validate_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    if current_user.role not in {UserRole.admin, UserRole.qa}:
        raise AppError("FORBIDDEN", "仅管理员或 QA 可导入用例", status_code=403)

    if mode not in {"upsert", "add_only"}:
        raise AppError("VALIDATION_ERROR", "mode 仅支持 upsert/add_only", status_code=422)

    file_bytes = await file.read()
    rows = parse_import_rows(file.filename or "", file_bytes)
    errors = validate_required_columns(rows, ["case_key", "title", "module", "steps", "expected"])

    if validate_only:
        data = ImportValidateOut(total_rows=len(rows), valid_rows=max(len(rows) - len(errors), 0), errors=errors)
        return success_response(request, data.model_dump())

    imported_count = 0
    for idx, row in enumerate(rows):
        if any(not row.get(column) for column in ["case_key", "title", "module", "steps", "expected"]):
            continue

        existing = db.query(TestCase).filter(TestCase.case_key == row["case_key"]).first()
        if existing:
            if mode == "add_only":
                continue
            existing.title = row["title"]
            existing.module = row["module"]
            existing.steps = row["steps"]
            existing.expected = row["expected"]
            existing.tags_json = [tag.strip() for tag in row.get("tags", "").split(",") if tag.strip()]
            existing.status = TestCaseStatus.active
            imported_count += 1
            continue

        count = db.query(func.count(TestCase.id)).scalar() or 0
        db.add(
            TestCase(
                case_id=f"C-{count + idx + 1:03d}",
                case_key=row["case_key"],
                title=row["title"],
                module=row["module"],
                steps=row["steps"],
                expected=row["expected"],
                tags_json=[tag.strip() for tag in row.get("tags", "").split(",") if tag.strip()],
                status=TestCaseStatus.active,
            )
        )
        imported_count += 1

    db.flush()

    versions = db.query(Version).all()
    for version in versions:
        snapshot = get_or_create_default_snapshot(db, version, current_user.id)
        ensure_version_case_status_rows(db, version, snapshot, current_user.id)

    write_audit(
        db,
        current_user.id,
        action="case.import",
        object_type="test_case",
        object_id="bulk",
        diff={"mode": mode, "total": len(rows), "imported": imported_count, "errors": len(errors)},
    )

    db.commit()
    data = ImportValidateOut(total_rows=len(rows), valid_rows=imported_count, errors=errors)
    return success_response(request, data.model_dump())


@router.get("/api/v1/cases:export")
def export_cases(
    version_key: str,
    format: str = Query("xlsx"),
    db: Session = Depends(get_db),
    _: UserAccount = Depends(get_current_user),
):
    if format not in {"csv", "xlsx"}:
        raise AppError("VALIDATION_ERROR", "format 仅支持 csv/xlsx", status_code=422)

    version = find_version_by_key(db, version_key)
    snapshot = get_or_create_default_snapshot(db, version)
    ensure_version_case_status_rows(db, version, snapshot, None)

    rows = (
        db.query(VersionCaseStatus, TestCase)
        .join(TestCase, TestCase.id == VersionCaseStatus.case_id)
        .filter(
            VersionCaseStatus.version_id == version.id,
            VersionCaseStatus.snapshot_id == snapshot.id,
            TestCase.status == TestCaseStatus.active,
        )
        .order_by(TestCase.case_key.asc())
        .all()
    )

    payload = [
        {
            "case_key": test_case.case_key,
            "title": test_case.title,
            "module": test_case.module,
            "status": status.status.value,
            "steps": test_case.steps,
            "expected": test_case.expected,
        }
        for status, test_case in rows
    ]

    headers = ["case_key", "title", "module", "status", "steps", "expected"]
    filename = f"cases-{version.version_key}.{format}"
    if format == "csv":
        return as_csv_response(filename, headers, payload)
    return as_xlsx_response(filename, headers, payload)
