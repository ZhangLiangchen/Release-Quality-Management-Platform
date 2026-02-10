from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import (
    CaseLinkType,
    Issue,
    IssueCaseLink,
    IssuePriority,
    IssueSeverity,
    IssueStatus,
    TestCase,
    UserAccount,
    UserRole,
    VersionCaseStatus,
    get_db,
)
from ..errors import AppError
from ..permissions import ensure_issue_operator
from ..response import success_response
from ..schemas import (
    ImportValidateOut,
    IssueCloseRequest,
    IssueCreateRequest,
    IssueTransitionRequest,
    IssueUpdateRequest,
)
from ..services import (
    ISSUE_GROUP_STATUSES,
    as_csv_response,
    as_xlsx_response,
    find_case_by_key,
    find_user_by_user_id,
    find_version_by_key,
    get_or_create_default_snapshot,
    get_statuses_by_group,
    issue_to_dict,
    parse_import_rows,
    validate_required_columns,
    write_audit,
)

router = APIRouter(tags=["issues"])

OPEN_STATUSES = {
    IssueStatus.new,
    IssueStatus.assigned,
    IssueStatus.fixing,
    IssueStatus.to_verify,
    IssueStatus.verify_failed,
}


@router.get("/api/v1/issues")
def list_issues(
    request: Request,
    version_key: str,
    status_group: str = Query("all"),
    assignee: Optional[str] = None,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(get_current_user),
):
    version = find_version_by_key(db, version_key)
    statuses = get_statuses_by_group(status_group)

    query = db.query(Issue).filter(Issue.found_version_id == version.id, Issue.status.in_(statuses))
    if assignee:
        assignee_user = find_user_by_user_id(db, assignee)
        query = query.filter(Issue.assignee_id == assignee_user.id)

    issues = query.order_by(Issue.updated_at.desc()).all()
    data = [issue_to_dict(issue, db) for issue in issues]
    return success_response(request, data)


@router.post("/api/v1/issues")
def create_issue(
    payload: IssueCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    if current_user.role == UserRole.viewer:
        raise AppError("FORBIDDEN", "无权限创建问题单", status_code=403)

    found_version = find_version_by_key(db, payload.found_version_key)
    reporter = find_user_by_user_id(db, payload.reporter)
    assignee = find_user_by_user_id(db, payload.assignee) if payload.assignee else None

    if not payload.links:
        raise AppError("VALIDATION_ERROR", "至少关联一个复现用例", status_code=422)
    if not any(link.link_type == CaseLinkType.repro for link in payload.links):
        raise AppError("VALIDATION_ERROR", "至少关联一条 repro 用例", status_code=422)

    count = db.query(func.count(Issue.id)).scalar() or 0
    issue = Issue(
        issue_id=f"I-{count + 1:03d}",
        issue_key=f"ISS-{count + 1:03d}",
        title=payload.title,
        description=payload.description,
        status=IssueStatus.new,
        priority=payload.priority,
        severity=payload.severity,
        assignee_id=assignee.id if assignee else None,
        reporter_id=reporter.id,
        found_version_id=found_version.id,
    )
    db.add(issue)
    db.flush()

    for link in payload.links:
        linked_case = find_case_by_key(db, link.case_key)
        db.add(
            IssueCaseLink(
                issue_id=issue.id,
                case_id=linked_case.id,
                link_type=link.link_type,
                note=link.note,
            )
        )

    write_audit(
        db,
        current_user.id,
        action="issue.create",
        object_type="issue",
        object_id=issue.issue_key,
        diff={"status": issue.status.value},
    )

    db.commit()
    db.refresh(issue)
    data = issue_to_dict(issue, db)
    return success_response(request, data)


@router.put("/api/v1/issues/{issue_key}")
def update_issue(
    issue_key: str,
    payload: IssueUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    if current_user.role == UserRole.viewer:
        raise AppError("FORBIDDEN", "无权限修改问题单", status_code=403)

    issue = db.query(Issue).filter(Issue.issue_key == issue_key).first()
    if not issue:
        raise AppError("NOT_FOUND", "问题单不存在", status_code=404)

    ensure_issue_operator(current_user, issue.assignee_id)
    before = {
        "title": issue.title,
        "description": issue.description,
        "priority": issue.priority.value,
        "assignee_id": issue.assignee_id,
    }

    if payload.title is not None:
        issue.title = payload.title
    if payload.description is not None:
        issue.description = payload.description
    if payload.priority is not None:
        issue.priority = payload.priority
    if payload.assignee is not None:
        assignee = find_user_by_user_id(db, payload.assignee)
        issue.assignee_id = assignee.id

    write_audit(
        db,
        current_user.id,
        action="issue.update",
        object_type="issue",
        object_id=issue.issue_key,
        diff={"before": before, "after": {"title": issue.title, "priority": issue.priority.value}},
    )

    db.commit()
    db.refresh(issue)
    return success_response(request, issue_to_dict(issue, db))


@router.post("/api/v1/issues/{issue_key}:transition")
def transition_issue(
    issue_key: str,
    payload: IssueTransitionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    if current_user.role == UserRole.viewer:
        raise AppError("FORBIDDEN", "无权限流转问题单", status_code=403)

    issue = db.query(Issue).filter(Issue.issue_key == issue_key).first()
    if not issue:
        raise AppError("NOT_FOUND", "问题单不存在", status_code=404)

    ensure_issue_operator(current_user, issue.assignee_id)

    issue.status = payload.target_status
    write_audit(
        db,
        current_user.id,
        action="issue.transition",
        object_type="issue",
        object_id=issue.issue_key,
        diff={"target_status": payload.target_status.value},
    )
    db.commit()
    db.refresh(issue)
    return success_response(request, issue_to_dict(issue, db))


@router.post("/api/v1/issues/{issue_key}:close")
def close_issue(
    issue_key: str,
    payload: IssueCloseRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    if current_user.role == UserRole.viewer:
        raise AppError("FORBIDDEN", "无权限关闭问题单", status_code=403)

    issue = db.query(Issue).filter(Issue.issue_key == issue_key).first()
    if not issue:
        raise AppError("NOT_FOUND", "问题单不存在", status_code=404)

    ensure_issue_operator(current_user, issue.assignee_id)

    if not payload.regression_case_keys:
        raise AppError("VALIDATION_ERROR", "关闭前必须关联回归用例", status_code=422)

    fix_version = find_version_by_key(db, payload.fix_version_key)
    verify_version = find_version_by_key(db, payload.verify_version_key)
    verify_snapshot = get_or_create_default_snapshot(db, verify_version)

    missing_cases: list[str] = []
    for case_key in payload.regression_case_keys:
        test_case = find_case_by_key(db, case_key)

        link_exists = (
            db.query(IssueCaseLink)
            .filter(
                IssueCaseLink.issue_id == issue.id,
                IssueCaseLink.case_id == test_case.id,
                IssueCaseLink.link_type == CaseLinkType.regression,
            )
            .first()
        )
        if not link_exists:
            db.add(
                IssueCaseLink(
                    issue_id=issue.id,
                    case_id=test_case.id,
                    link_type=CaseLinkType.regression,
                )
            )

        status_row = (
            db.query(VersionCaseStatus)
            .filter(
                VersionCaseStatus.version_id == verify_version.id,
                VersionCaseStatus.snapshot_id == verify_snapshot.id,
                VersionCaseStatus.case_id == test_case.id,
            )
            .first()
        )
        if not status_row or status_row.status != "passed":
            missing_cases.append(case_key)

    if missing_cases:
        raise AppError(
            "VALIDATION_ERROR",
            "回归用例在验证版本下未全部通过",
            status_code=422,
            details={"unpassed_cases": missing_cases},
        )

    issue.fix_version_id = fix_version.id
    issue.verify_version_id = verify_version.id
    issue.status = IssueStatus.closed

    write_audit(
        db,
        current_user.id,
        action="issue.close",
        object_type="issue",
        object_id=issue.issue_key,
        diff={"fix_version": payload.fix_version_key, "verify_version": payload.verify_version_key},
    )

    db.commit()
    db.refresh(issue)
    return success_response(request, issue_to_dict(issue, db))


@router.post("/api/v1/issues:import")
async def import_issues(
    request: Request,
    file: UploadFile = File(...),
    mode: str = Query("upsert"),
    validate_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    if current_user.role not in {UserRole.admin, UserRole.qa}:
        raise AppError("FORBIDDEN", "仅管理员或 QA 可导入问题单", status_code=403)

    if mode not in {"upsert", "add_only"}:
        raise AppError("VALIDATION_ERROR", "mode 仅支持 upsert/add_only", status_code=422)

    file_bytes = await file.read()
    rows = parse_import_rows(file.filename or "", file_bytes)
    errors = validate_required_columns(rows, ["issue_key", "title", "found_version_key"])

    imported = 0
    for idx, row in enumerate(rows):
        if any(not row.get(column) for column in ["issue_key", "title", "found_version_key"]):
            continue

        status_value = IssueStatus(row.get("status", "new")) if row.get("status", "new") in IssueStatus._value2member_map_ else IssueStatus.new
        if status_value not in OPEN_STATUSES:
            errors.append(f"第 {idx + 2} 行 status 仅允许开放态")
            continue

        found_version = find_version_by_key(db, row["found_version_key"])
        existing = db.query(Issue).filter(Issue.issue_key == row["issue_key"]).first()
        priority = (
            IssuePriority(row.get("priority", "medium"))
            if row.get("priority", "medium") in IssuePriority._value2member_map_
            else IssuePriority.medium
        )
        severity = (
            IssueSeverity(row.get("severity", "major"))
            if row.get("severity", "major") in IssueSeverity._value2member_map_
            else IssueSeverity.major
        )

        if existing:
            if mode == "add_only":
                continue
            existing.title = row["title"]
            existing.description = row.get("description", "")
            existing.status = status_value
            existing.priority = priority
            existing.severity = severity
            existing.found_version_id = found_version.id
            imported += 1
            continue

        issue_count = db.query(func.count(Issue.id)).scalar() or 0
        issue = Issue(
            issue_id=f"I-{issue_count + idx + 1:03d}",
            issue_key=row["issue_key"],
            title=row["title"],
            description=row.get("description", ""),
            status=status_value,
            priority=priority,
            severity=severity,
            reporter_id=current_user.id,
            found_version_id=found_version.id,
        )
        db.add(issue)
        imported += 1

    if validate_only:
        data = ImportValidateOut(total_rows=len(rows), valid_rows=max(len(rows) - len(errors), 0), errors=errors)
        return success_response(request, data.model_dump())

    write_audit(
        db,
        current_user.id,
        action="issue.import",
        object_type="issue",
        object_id="bulk",
        diff={"mode": mode, "total": len(rows), "imported": imported, "errors": len(errors)},
    )

    db.commit()
    data = ImportValidateOut(total_rows=len(rows), valid_rows=imported, errors=errors)
    return success_response(request, data.model_dump())


@router.get("/api/v1/issues:export")
def export_issues(
    version_key: str,
    format: str = Query("xlsx"),
    db: Session = Depends(get_db),
    _: UserAccount = Depends(get_current_user),
):
    if format not in {"csv", "xlsx"}:
        raise AppError("VALIDATION_ERROR", "format 仅支持 csv/xlsx", status_code=422)

    version = find_version_by_key(db, version_key)
    issues = db.query(Issue).filter(Issue.found_version_id == version.id).order_by(Issue.updated_at.desc()).all()

    payload = []
    for issue in issues:
        issue_dict = issue_to_dict(issue, db)
        payload.append(
            {
                "issue_key": issue_dict["issue_key"],
                "title": issue_dict["title"],
                "status": issue_dict["status"].value,
                "priority": issue_dict["priority"].value,
                "severity": issue_dict["severity"].value,
                "assignee": issue_dict["assignee"] or "",
                "reporter": issue_dict["reporter"],
                "found_version_key": issue_dict["found_version_key"],
                "updated_at": issue_dict["updated_at"].isoformat(),
            }
        )

    headers = [
        "issue_key",
        "title",
        "status",
        "priority",
        "severity",
        "assignee",
        "reporter",
        "found_version_key",
        "updated_at",
    ]

    filename = f"issues-{version.version_key}.{format}"
    if format == "csv":
        return as_csv_response(filename, headers, payload)
    return as_xlsx_response(filename, headers, payload)
