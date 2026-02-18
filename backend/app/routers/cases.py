from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import (
    CaseStatus,
    CaseStatusHistory,
    CaseTreeNode,
    CaseTreeNodeType,
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
from ..schemas import (
    CaseCreateRequest,
    CaseDetailOut,
    CaseStatusUpdateRequest,
    CaseTreeNodeCreateRequest,
    CaseUpdateRequest,
    ImportValidateOut,
)
from ..services import (
    as_csv_response,
    as_xlsx_response,
    build_case_history_rows,
    build_case_module_rows,
    build_case_tree_rows,
    ensure_case_tree_nodes_for_legacy_cases,
    ensure_version_case_status_rows,
    find_case_by_key,
    find_case_tree_node_by_node_id,
    find_or_create_case_tree_node,
    find_version_by_key,
    get_or_create_default_snapshot,
    parse_import_rows,
    split_case_module_path,
    validate_required_columns,
    write_audit,
)

router = APIRouter(tags=["cases"])


def _next_case_id(db: Session) -> str:
    count = db.query(func.count(TestCase.id)).scalar() or 0
    seq = int(count) + 1
    while True:
        case_id = f"HSC-{seq:07d}"
        exists = db.query(TestCase).filter(TestCase.case_id == case_id).first()
        if not exists:
            return case_id
        seq += 1


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


@router.get("/api/v1/case-tree")
def list_case_tree(
    request: Request,
    version_key: str,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(get_current_user),
):
    version = find_version_by_key(db, version_key)
    tree = build_case_tree_rows(db, version)
    db.commit()
    return success_response(
        request,
        {
            "version_key": version_key,
            "tree": tree,
        },
    )


@router.post("/api/v1/case-tree/nodes")
def create_case_tree_node(
    payload: CaseTreeNodeCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    if current_user.role not in {UserRole.admin, UserRole.qa}:
        raise AppError("FORBIDDEN", "仅管理员或 QA 可新增目录", status_code=403)

    find_version_by_key(db, payload.version_key)
    parent = find_case_tree_node_by_node_id(db, payload.parent_node_id) if payload.parent_node_id else None
    normalized_name = payload.name.strip()
    if not normalized_name:
        raise AppError("VALIDATION_ERROR", "目录名不能为空", status_code=422)

    if parent and parent.node_type != CaseTreeNodeType.directory:
        raise AppError("VALIDATION_ERROR", "仅目录节点可新增子目录", status_code=422)

    full_path = normalized_name if not parent else f"{parent.full_path}/{normalized_name}"
    exists = db.query(CaseTreeNode).filter(CaseTreeNode.full_path == full_path).first()
    if exists:
        raise AppError("VALIDATION_ERROR", "同级目录重名", status_code=422)

    node = find_or_create_case_tree_node(
        db,
        name=normalized_name,
        node_type=payload.node_type,
        parent=parent,
    )

    write_audit(
        db,
        current_user.id,
        action="case.tree.node.create",
        object_type="case_tree_node",
        object_id=node.node_id,
        diff={
            "parent_node_id": parent.node_id if parent else None,
            "name": node.name,
            "node_type": node.node_type.value,
            "full_path": node.full_path,
        },
    )

    db.commit()
    return success_response(
        request,
        {
            "node_id": node.node_id,
            "name": node.name,
            "node_type": node.node_type,
            "parent_node_id": parent.node_id if parent else None,
            "full_path": node.full_path,
        },
    )


@router.post("/api/v1/cases")
def create_case(
    payload: CaseCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    if current_user.role not in {UserRole.admin, UserRole.qa}:
        raise AppError("FORBIDDEN", "仅管理员或 QA 可新增用例", status_code=403)

    find_version_by_key(db, payload.version_key)
    parent = find_case_tree_node_by_node_id(db, payload.parent_node_id)
    if parent.node_type not in {CaseTreeNodeType.directory, CaseTreeNodeType.file}:
        raise AppError("VALIDATION_ERROR", "父节点类型不支持挂载用例", status_code=422)

    case_key = payload.case_key.strip()
    if not case_key:
        raise AppError("VALIDATION_ERROR", "用例编号不能为空", status_code=422)

    existing = db.query(TestCase).filter(TestCase.case_key == case_key).first()
    if existing:
        raise AppError("VALIDATION_ERROR", f"用例编号已存在: {case_key}", status_code=422)

    path_parts = split_case_module_path(parent.full_path)
    module = path_parts[0] if len(path_parts) == 1 else "/".join(path_parts[:2])

    test_case = TestCase(
        case_id=_next_case_id(db),
        case_key=case_key,
        tree_node_id=parent.id,
        module=module,
        title=payload.title.strip(),
        steps=payload.steps.strip(),
        expected=payload.expected.strip(),
        tags_json=[item.strip() for item in payload.tags if item.strip()],
        status=TestCaseStatus.active,
    )
    db.add(test_case)
    db.flush()
    ensure_case_tree_nodes_for_legacy_cases(db)

    versions = db.query(Version).all()
    for row in versions:
        snapshot = get_or_create_default_snapshot(db, row, current_user.id)
        ensure_version_case_status_rows(db, row, snapshot, current_user.id)

    write_audit(
        db,
        current_user.id,
        action="case.create",
        object_type="test_case",
        object_id=test_case.case_key,
        diff={
            "tree_node_id": parent.node_id,
            "module": test_case.module,
            "title": test_case.title,
        },
    )

    db.commit()
    return success_response(
        request,
        {
            "case_key": case_key,
            "title": test_case.title,
            "module": test_case.module,
            "tree_node_id": parent.node_id,
        },
    )


@router.put("/api/v1/cases/{case_key}")
def update_case(
    case_key: str,
    payload: CaseUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    if current_user.role not in {UserRole.admin, UserRole.qa}:
        raise AppError("FORBIDDEN", "仅管理员或 QA 可更新用例", status_code=403)

    test_case = find_case_by_key(db, case_key)
    if test_case.status != TestCaseStatus.active:
        raise AppError("VALIDATION_ERROR", "已废弃用例不可编辑", status_code=422)

    parent = None
    if payload.parent_node_id:
        parent = find_case_tree_node_by_node_id(db, payload.parent_node_id)
        if parent.node_type not in {CaseTreeNodeType.directory, CaseTreeNodeType.file}:
            raise AppError("VALIDATION_ERROR", "父节点类型不支持挂载用例", status_code=422)

    before = {
        "tree_node_id": test_case.tree_node_id,
        "module": test_case.module,
        "title": test_case.title,
        "steps": test_case.steps,
        "expected": test_case.expected,
        "tags": test_case.tags_json,
    }

    if parent:
        path_parts = split_case_module_path(parent.full_path)
        module = path_parts[0] if len(path_parts) == 1 else "/".join(path_parts[:2])
        test_case.tree_node_id = parent.id
        test_case.module = module

    test_case.title = payload.title.strip()
    test_case.steps = payload.steps.strip()
    test_case.expected = payload.expected.strip()
    test_case.tags_json = [item.strip() for item in payload.tags if item.strip()]

    write_audit(
        db,
        current_user.id,
        action="case.update",
        object_type="test_case",
        object_id=test_case.case_key,
        diff={
            "before": before,
            "after": {
                "tree_node_id": test_case.tree_node_id,
                "module": test_case.module,
                "title": test_case.title,
                "steps": test_case.steps,
                "expected": test_case.expected,
                "tags": test_case.tags_json,
            },
        },
    )

    db.commit()
    return success_response(
        request,
        {
            "case_key": test_case.case_key,
            "title": test_case.title,
            "module": test_case.module,
            "tree_node_id": parent.node_id if parent else None,
        },
    )


@router.delete("/api/v1/cases/{case_key}")
def delete_case(
    case_key: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    if current_user.role not in {UserRole.admin, UserRole.qa}:
        raise AppError("FORBIDDEN", "仅管理员或 QA 可删除用例", status_code=403)

    test_case = find_case_by_key(db, case_key)
    if test_case.status == TestCaseStatus.deprecated:
        return success_response(request, {"case_key": case_key, "deleted": True, "already_deprecated": True})

    test_case.status = TestCaseStatus.deprecated

    write_audit(
        db,
        current_user.id,
        action="case.delete",
        object_type="test_case",
        object_id=test_case.case_key,
        diff={"status": "deprecated"},
    )

    db.commit()
    return success_response(request, {"case_key": case_key, "deleted": True})


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
