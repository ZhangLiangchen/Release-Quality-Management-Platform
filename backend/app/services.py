from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from io import BytesIO, StringIO
from typing import Iterable, Optional

import csv
import openpyxl
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from .database import (
    AuditLog,
    CaseLinkType,
    CaseSetSnapshot,
    CaseStatus,
    CaseStatusHistory,
    Issue,
    IssueCaseLink,
    IssueStatus,
    TestCase,
    UserAccount,
    Version,
    VersionCaseStatus,
)
from .errors import AppError

ISSUE_GROUP_STATUSES: dict[str, set[IssueStatus]] = {
    "all": {
        IssueStatus.new,
        IssueStatus.assigned,
        IssueStatus.fixing,
        IssueStatus.to_verify,
        IssueStatus.verify_failed,
        IssueStatus.closed,
        IssueStatus.rejected,
        IssueStatus.duplicate,
        IssueStatus.invalid,
        IssueStatus.deferred,
    },
    "open": {IssueStatus.new, IssueStatus.assigned, IssueStatus.fixing, IssueStatus.verify_failed},
    "pending": {IssueStatus.to_verify},
    "closed": {IssueStatus.closed},
    "invalid": {IssueStatus.invalid, IssueStatus.rejected, IssueStatus.duplicate, IssueStatus.deferred},
}


def get_statuses_by_group(group: str) -> set[IssueStatus]:
    if group not in ISSUE_GROUP_STATUSES:
        raise AppError("VALIDATION_ERROR", f"未知状态组: {group}", status_code=422)
    return ISSUE_GROUP_STATUSES[group]


def find_version_by_key(db: Session, version_key: str) -> Version:
    version = db.query(Version).filter(Version.version_key == version_key).first()
    if not version:
        raise AppError("NOT_FOUND", f"版本不存在: {version_key}", status_code=404)
    return version


def find_user_by_user_id(db: Session, user_id: str) -> UserAccount:
    user = db.query(UserAccount).filter(UserAccount.user_id == user_id).first()
    if not user:
        raise AppError("NOT_FOUND", f"用户不存在: {user_id}", status_code=404)
    return user


def find_case_by_key(db: Session, case_key: str) -> TestCase:
    case = db.query(TestCase).filter(TestCase.case_key == case_key).first()
    if not case:
        raise AppError("NOT_FOUND", f"用例不存在: {case_key}", status_code=404)
    return case


def get_or_create_default_snapshot(
    db: Session,
    version: Version,
    actor_id: Optional[int] = None,
) -> CaseSetSnapshot:
    existing = db.query(CaseSetSnapshot).filter(CaseSetSnapshot.version_id == version.id).first()
    if existing:
        return existing

    snapshot_count = db.query(func.count(CaseSetSnapshot.id)).scalar() or 0
    snapshot = CaseSetSnapshot(
        snapshot_id=f"SNAP-{snapshot_count + 1:03d}",
        version_id=version.id,
        case_set_id=None,
        snapshot_json={"scope": "all_active_cases", "reason": "auto-generated"},
        created_by=actor_id,
    )
    db.add(snapshot)
    db.flush()
    return snapshot


def ensure_version_case_status_rows(
    db: Session,
    version: Version,
    snapshot: CaseSetSnapshot,
    actor_id: Optional[int],
) -> None:
    cases = db.query(TestCase).filter(TestCase.status == "active").all()
    for test_case in cases:
        exists = (
            db.query(VersionCaseStatus)
            .filter(
                VersionCaseStatus.version_id == version.id,
                VersionCaseStatus.snapshot_id == snapshot.id,
                VersionCaseStatus.case_id == test_case.id,
            )
            .first()
        )
        if exists:
            continue

        db.add(
            VersionCaseStatus(
                version_id=version.id,
                snapshot_id=snapshot.id,
                case_id=test_case.id,
                status=CaseStatus.not_run,
                updated_by=actor_id,
            )
        )


def write_audit(
    db: Session,
    actor_id: Optional[int],
    action: str,
    object_type: str,
    object_id: str,
    diff: dict,
) -> None:
    db.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            diff_json=diff,
        )
    )


def calculate_dashboard(db: Session, version: Version) -> dict:
    snapshot = get_or_create_default_snapshot(db, version)

    rows = (
        db.query(VersionCaseStatus, TestCase)
        .join(TestCase, TestCase.id == VersionCaseStatus.case_id)
        .filter(
            VersionCaseStatus.version_id == version.id,
            VersionCaseStatus.snapshot_id == snapshot.id,
            TestCase.status == "active",
        )
        .all()
    )

    total_cases = len(rows)
    executed_statuses = {CaseStatus.passed, CaseStatus.failed, CaseStatus.blocked, CaseStatus.skipped}
    executed_cases = len([1 for row, _ in rows if row.status in executed_statuses])
    passed_cases = len([1 for row, _ in rows if row.status == CaseStatus.passed])
    skipped_cases = len([1 for row, _ in rows if row.status == CaseStatus.skipped])
    execution_rate = 0.0 if total_cases == 0 else executed_cases / total_cases

    effective_denominator = executed_cases - skipped_cases
    pass_rate = None if effective_denominator <= 0 else passed_cases / effective_denominator

    issues = db.query(Issue).filter(Issue.found_version_id == version.id).all()
    total_issues = len(issues)
    resolved_statuses = ISSUE_GROUP_STATUSES["closed"] | ISSUE_GROUP_STATUSES["invalid"]
    resolved_issues = len([1 for issue in issues if issue.status in resolved_statuses])
    pending_issue_count = len([1 for issue in issues if issue.status in ISSUE_GROUP_STATUSES["pending"]])
    resolution_rate = 0.0 if total_issues == 0 else resolved_issues / total_issues

    return {
        "total_cases": total_cases,
        "executed_cases": executed_cases,
        "passed_cases": passed_cases,
        "skipped_cases": skipped_cases,
        "execution_rate": execution_rate,
        "pass_rate": pass_rate,
        "total_issues": total_issues,
        "resolved_issues": resolved_issues,
        "resolution_rate": resolution_rate,
        "pending_issue_count": pending_issue_count,
    }


def serialize_issue_links(links: Iterable[IssueCaseLink], db: Session) -> list[dict]:
    case_map = {
        row.id: row.case_key
        for row in db.query(TestCase).filter(TestCase.id.in_([link.case_id for link in links])).all()
    }
    return [
        {
            "case_key": case_map.get(link.case_id, ""),
            "link_type": link.link_type,
            "note": link.note,
        }
        for link in links
    ]


def issue_to_dict(issue: Issue, db: Session) -> dict:
    version_ids = [issue.found_version_id, issue.fix_version_id, issue.verify_version_id]
    version_map = {
        row.id: row.version_key
        for row in db.query(Version).filter(Version.id.in_([version_id for version_id in version_ids if version_id])).all()
    }

    user_ids = [issue.assignee_id, issue.reporter_id]
    user_map = {
        row.id: row.user_id
        for row in db.query(UserAccount).filter(UserAccount.id.in_([user_id for user_id in user_ids if user_id])).all()
    }

    return {
        "issue_key": issue.issue_key,
        "title": issue.title,
        "description": issue.description,
        "status": issue.status,
        "priority": issue.priority,
        "severity": issue.severity,
        "assignee": user_map.get(issue.assignee_id),
        "reporter": user_map.get(issue.reporter_id, ""),
        "found_version_key": version_map.get(issue.found_version_id, ""),
        "fix_version_key": version_map.get(issue.fix_version_id) if issue.fix_version_id else None,
        "verify_version_key": version_map.get(issue.verify_version_id) if issue.verify_version_id else None,
        "created_at": issue.created_at,
        "updated_at": issue.updated_at,
        "links": serialize_issue_links(issue.links, db),
    }


def as_csv_response(filename: str, headers: list[str], rows: list[dict]) -> StreamingResponse:
    text_stream = StringIO()
    writer = csv.DictWriter(text_stream, fieldnames=headers)
    writer.writeheader()
    for row in rows:
        normalized = {key: row.get(key, "") for key in headers}
        writer.writerow(normalized)
    stream = BytesIO(text_stream.getvalue().encode("utf-8"))
    stream.seek(0)

    return StreamingResponse(
        stream,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def as_xlsx_response(filename: str, headers: list[str], rows: list[dict]) -> StreamingResponse:
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.append(headers)
    for row in rows:
        worksheet.append([row.get(key, "") for key in headers])

    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)

    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def parse_import_rows(filename: str, file_bytes: bytes) -> list[dict[str, str]]:
    lower = filename.lower()

    if lower.endswith(".csv"):
        text = file_bytes.decode("utf-8")
        reader = csv.DictReader(text.splitlines())
        return [
            {str(key).strip(): str(value).strip() for key, value in row.items() if key is not None}
            for row in reader
        ]

    if lower.endswith(".xlsx"):
        workbook = openpyxl.load_workbook(BytesIO(file_bytes))
        sheet = workbook.active
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return []
        headers = [str(value).strip() for value in rows[0]]
        result: list[dict[str, str]] = []
        for data_row in rows[1:]:
            mapped = {
                headers[idx]: str(value).strip() if value is not None else ""
                for idx, value in enumerate(data_row)
                if idx < len(headers)
            }
            if any(mapped.values()):
                result.append(mapped)
        return result

    raise AppError("VALIDATION_ERROR", "仅支持 CSV/XLSX 导入", status_code=422)


def validate_required_columns(rows: list[dict[str, str]], required_columns: list[str]) -> list[str]:
    errors: list[str] = []
    for idx, row in enumerate(rows):
        for key in required_columns:
            if not row.get(key):
                errors.append(f"第 {idx + 2} 行缺少 {key}")
    return errors


def build_case_module_rows(db: Session, version: Version) -> list[dict]:
    snapshot = get_or_create_default_snapshot(db, version)
    statuses = (
        db.query(VersionCaseStatus, TestCase, UserAccount)
        .join(TestCase, TestCase.id == VersionCaseStatus.case_id)
        .outerjoin(UserAccount, UserAccount.id == VersionCaseStatus.updated_by)
        .filter(
            VersionCaseStatus.version_id == version.id,
            VersionCaseStatus.snapshot_id == snapshot.id,
            TestCase.status == "active",
        )
        .all()
    )

    grouped: dict[str, list[dict]] = defaultdict(list)
    for status, test_case, updater in statuses:
        grouped[test_case.module].append(
            {
                "case_key": test_case.case_key,
                "title": test_case.title,
                "module": test_case.module,
                "latest_status": status.status,
                "latest_updated_at": status.updated_at,
                "latest_updated_by": updater.user_id if updater else None,
            }
        )

    return [
        {
            "module": module,
            "cases": sorted(items, key=lambda row: row["case_key"]),
        }
        for module, items in sorted(grouped.items(), key=lambda item: item[0])
    ]


def build_case_history_rows(db: Session, version_id: int, case_id: int, limit: int = 10) -> list[dict]:
    rows = (
        db.query(CaseStatusHistory, UserAccount)
        .outerjoin(UserAccount, UserAccount.id == CaseStatusHistory.executor_id)
        .filter(CaseStatusHistory.version_id == version_id, CaseStatusHistory.case_id == case_id)
        .order_by(CaseStatusHistory.executed_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": history.id,
            "executed_at": history.executed_at,
            "executor": user.user_id if user else "system",
            "status": history.status,
            "note": history.note,
            "attachments": history.attachments_json,
        }
        for history, user in rows
    ]


def make_snapshot_payload(version_key: str, case_keys: list[str], reason: str) -> dict:
    return {
        "version_key": version_key,
        "case_keys": case_keys,
        "reason": reason,
        "generated_at": datetime.utcnow().isoformat(),
    }
