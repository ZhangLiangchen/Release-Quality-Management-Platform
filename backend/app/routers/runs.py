from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import (
    CaseStatus,
    RunCase,
    RunCaseHistory,
    TestPlan,
    TestRun,
    UserAccount,
    UserRole,
    get_db,
)
from ..errors import AppError
from ..response import success_response
from ..schemas import RunCaseStatusUpdateRequest
from ..services import (
    calculate_run_metrics,
    find_run_by_key,
    find_run_case_by_key,
    find_version_by_key,
    refresh_run_status,
    write_audit,
)

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


def _serialize_run(db: Session, run: TestRun) -> dict:
    plan = run.plan
    version = plan.version
    metrics = calculate_run_metrics(db, run)
    return {
        "run_key": run.run_key,
        "plan_key": plan.plan_key,
        "version_key": version.version_key,
        "name": run.name,
        "build_no": run.build_no,
        "environment": run.environment,
        "status": run.status,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "pass_rate": metrics["pass_rate"],
        "executed_cases": metrics["executed_cases"],
        "total_cases": metrics["total_cases"],
    }


def _serialize_run_case(db: Session, run_case: RunCase) -> dict:
    updater = db.query(UserAccount).filter(UserAccount.id == run_case.last_updated_by).first() if run_case.last_updated_by else None
    return {
        "run_case_key": run_case.run_case_key,
        "case_key": run_case.case_key_snapshot,
        "title": run_case.title_snapshot,
        "module": run_case.module_snapshot,
        "steps": run_case.steps_snapshot,
        "expected": run_case.expected_snapshot,
        "status": run_case.current_status,
        "last_updated_at": run_case.last_updated_at,
        "last_updated_by": updater.user_id if updater else None,
    }


@router.get("")
def list_runs(
    request: Request,
    version_key: str,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(get_current_user),
):
    version = find_version_by_key(db, version_key)

    runs = (
        db.query(TestRun)
        .join(TestPlan, TestPlan.id == TestRun.plan_id)
        .filter(TestPlan.version_id == version.id)
        .order_by(TestRun.started_at.desc(), TestRun.id.desc())
        .all()
    )
    return success_response(request, [_serialize_run(db, run) for run in runs])


@router.get("/latest")
def get_latest_run(
    request: Request,
    version_key: str,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(get_current_user),
):
    version = find_version_by_key(db, version_key)
    run = (
        db.query(TestRun)
        .join(TestPlan, TestPlan.id == TestRun.plan_id)
        .filter(TestPlan.version_id == version.id)
        .order_by(TestRun.started_at.desc(), TestRun.id.desc())
        .first()
    )
    if not run:
        raise AppError("NOT_FOUND", f"版本下暂无 Run: {version_key}", status_code=404)
    return success_response(request, _serialize_run(db, run))


@router.get("/{run_key}")
def get_run_detail(
    run_key: str,
    request: Request,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(get_current_user),
):
    run = find_run_by_key(db, run_key)
    return success_response(request, _serialize_run(db, run))


@router.get("/{run_key}/cases")
def list_run_cases(
    run_key: str,
    request: Request,
    status: CaseStatus | None = Query(default=None),
    keyword: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: UserAccount = Depends(get_current_user),
):
    run = find_run_by_key(db, run_key)
    query = db.query(RunCase).filter(RunCase.run_id == run.id)
    if status is not None:
        query = query.filter(RunCase.current_status == status)
    rows = query.order_by(RunCase.case_key_snapshot.asc()).all()

    payload = []
    for run_case in rows:
        if keyword:
            needle = keyword.lower()
            if needle not in run_case.case_key_snapshot.lower() and needle not in run_case.title_snapshot.lower():
                continue
        payload.append(_serialize_run_case(db, run_case))

    return success_response(request, payload)


@router.put("/{run_key}/cases/{run_case_key}")
def update_run_case_status(
    run_key: str,
    run_case_key: str,
    payload: RunCaseStatusUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    if current_user.role not in {UserRole.admin, UserRole.qa}:
        raise AppError("FORBIDDEN", "仅管理员或 QA 可更新执行状态", status_code=403)

    run = find_run_by_key(db, run_key)
    run_case = find_run_case_by_key(db, run, run_case_key)

    run_case.current_status = payload.status
    run_case.last_updated_by = current_user.id
    run_case.last_updated_at = datetime.utcnow()

    db.add(
        RunCaseHistory(
            run_case_id=run_case.id,
            status=payload.status,
            remark=payload.remark,
            operator_id=current_user.id,
            attachments_json=[item.model_dump() for item in payload.attachments],
        )
    )

    refresh_run_status(db, run)

    write_audit(
        db,
        current_user.id,
        action="run.case.status.update",
        object_type="run_case",
        object_id=run_case.run_case_key,
        diff={"status": payload.status.value},
    )

    db.commit()

    return success_response(
        request,
        {
            "run_key": run.run_key,
            "run_case_key": run_case.run_case_key,
            "status": run_case.current_status,
            "run_status": run.status,
        },
    )


@router.get("/{run_key}/cases/{run_case_key}/history")
def get_run_case_history(
    run_key: str,
    run_case_key: str,
    request: Request,
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    _: UserAccount = Depends(get_current_user),
):
    run = find_run_by_key(db, run_key)
    run_case = find_run_case_by_key(db, run, run_case_key)
    rows = (
        db.query(RunCaseHistory)
        .filter(RunCaseHistory.run_case_id == run_case.id)
        .order_by(RunCaseHistory.operated_at.desc(), RunCaseHistory.id.desc())
        .limit(limit)
        .all()
    )

    user_ids = [item.operator_id for item in rows if item.operator_id]
    user_map = {
        row.id: row.user_id
        for row in db.query(UserAccount).filter(UserAccount.id.in_(user_ids)).all()
    }

    data = [
        {
            "id": item.id,
            "status": item.status,
            "remark": item.remark,
            "operator": user_map.get(item.operator_id, "system") if item.operator_id else "system",
            "operated_at": item.operated_at,
            "attachments": item.attachments_json,
        }
        for item in rows
    ]
    return success_response(request, data)
