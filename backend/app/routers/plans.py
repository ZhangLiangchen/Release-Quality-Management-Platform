from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import (
    Issue,
    IssueCaseLink,
    PlanStatus,
    RunCase,
    RunCaseHistory,
    SuiteCaseRef,
    SuiteVersionStatus,
    TestCase,
    TestPlan,
    TestRun,
    UserAccount,
    UserRole,
    get_db,
)
from ..errors import AppError
from ..response import success_response
from ..schemas import PlanCreateRequest, RunCreateRequest
from ..services import (
    calculate_run_metrics,
    create_run_from_suite_version,
    find_plan_by_key,
    find_suite_version_by_key,
    find_version_by_key,
    generate_plan_key,
    write_audit,
)

router = APIRouter(prefix="/api/v1/plans", tags=["plans"])


def _ensure_plan_editor(user: UserAccount) -> None:
    if user.role not in {UserRole.admin, UserRole.qa}:
        raise AppError("FORBIDDEN", "仅管理员或 QA 可维护测试计划", status_code=403)


def _run_payload(db: Session, run: TestRun, plan: TestPlan, version_key: str) -> dict:
    metrics = calculate_run_metrics(db, run)
    return {
        "run_key": run.run_key,
        "plan_key": plan.plan_key,
        "version_key": version_key,
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


def _plan_issue_bindings(db: Session, plan: TestPlan) -> list[dict]:
    rows = (
        db.query(Issue.issue_key, TestCase.case_key)
        .join(IssueCaseLink, IssueCaseLink.issue_id == Issue.id)
        .join(TestCase, TestCase.id == IssueCaseLink.case_id)
        .join(SuiteCaseRef, SuiteCaseRef.case_id == TestCase.id)
        .filter(SuiteCaseRef.suite_version_id == plan.suite_version_id)
        .distinct()
        .order_by(Issue.issue_key.asc(), TestCase.case_key.asc())
        .all()
    )
    return [{"issue_key": row.issue_key, "case_key": row.case_key} for row in rows]


@router.get("")
def list_plans(
    request: Request,
    version_key: str,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(get_current_user),
):
    version = find_version_by_key(db, version_key)
    plans = (
        db.query(TestPlan)
        .filter(TestPlan.version_id == version.id)
        .order_by(TestPlan.updated_at.desc(), TestPlan.id.desc())
        .all()
    )

    payload: list[dict] = []
    for plan in plans:
        latest_run = (
            db.query(TestRun)
            .filter(TestRun.plan_id == plan.id)
            .order_by(TestRun.started_at.desc(), TestRun.id.desc())
            .first()
        )
        run_count = db.query(func.count(TestRun.id)).filter(TestRun.plan_id == plan.id).scalar() or 0
        latest_pass_rate = calculate_run_metrics(db, latest_run)["pass_rate"] if latest_run else None
        payload.append(
            {
                "plan_key": plan.plan_key,
                "version_key": version.version_key,
                "suite_version_key": plan.suite_version.suite_version_key,
                "name": plan.name,
                "description": plan.description,
                "status": plan.status,
                "created_at": plan.created_at,
                "updated_at": plan.updated_at,
                "run_count": int(run_count),
                "pass_rate": latest_pass_rate,
            }
        )

    return success_response(request, payload)


@router.post("")
def create_plan(
    payload: PlanCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    _ensure_plan_editor(current_user)

    version = find_version_by_key(db, payload.version_key)
    suite_version = find_suite_version_by_key(db, payload.suite_version_key)
    suite = suite_version.suite
    if suite.version_id != version.id:
        raise AppError("VALIDATION_ERROR", "用例集版本与测试版本不匹配", status_code=422)
    if suite_version.status != SuiteVersionStatus.published:
        raise AppError("VALIDATION_ERROR", "只能使用已发布用例集版本创建计划", status_code=422)

    plan_name = payload.name.strip()
    if not plan_name:
        raise AppError("VALIDATION_ERROR", "计划名称不能为空", status_code=422)

    duplicate = (
        db.query(TestPlan)
        .filter(TestPlan.version_id == version.id, TestPlan.name == plan_name)
        .first()
    )
    if duplicate:
        raise AppError("VALIDATION_ERROR", f"计划已存在: {plan_name}", status_code=422)

    plan = TestPlan(
        plan_key=generate_plan_key(db),
        version_id=version.id,
        suite_version_id=suite_version.id,
        name=plan_name,
        description=payload.description,
        status=PlanStatus.in_progress,
        created_by=current_user.id,
    )
    db.add(plan)
    db.flush()

    write_audit(
        db,
        current_user.id,
        action="plan.create",
        object_type="test_plan",
        object_id=plan.plan_key,
        diff={"version_key": version.version_key, "suite_version_key": suite_version.suite_version_key},
    )

    db.commit()
    db.refresh(plan)

    return success_response(
        request,
        {
            "plan_key": plan.plan_key,
            "version_key": version.version_key,
            "suite_version_key": suite_version.suite_version_key,
            "name": plan.name,
            "description": plan.description,
            "status": plan.status,
            "created_at": plan.created_at,
            "updated_at": plan.updated_at,
            "run_count": 0,
            "pass_rate": None,
        },
    )


@router.delete("/{plan_key}")
def delete_plan(
    plan_key: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    _ensure_plan_editor(current_user)

    plan = find_plan_by_key(db, plan_key)
    bindings = _plan_issue_bindings(db, plan)
    if bindings:
        raise AppError(
            "VALIDATION_ERROR",
            "该测试计划有问题单绑定，不可删除",
            status_code=422,
            details={"bindings": bindings},
        )

    run_ids = [row.id for row in db.query(TestRun.id).filter(TestRun.plan_id == plan.id).all()]
    if run_ids:
        run_case_ids = [row.id for row in db.query(RunCase.id).filter(RunCase.run_id.in_(run_ids)).all()]
        if run_case_ids:
            (
                db.query(RunCaseHistory)
                .filter(RunCaseHistory.run_case_id.in_(run_case_ids))
                .delete(synchronize_session=False)
            )
        db.query(RunCase).filter(RunCase.run_id.in_(run_ids)).delete(synchronize_session=False)
        db.query(TestRun).filter(TestRun.id.in_(run_ids)).delete(synchronize_session=False)

    write_audit(
        db,
        current_user.id,
        action="plan.delete",
        object_type="test_plan",
        object_id=plan.plan_key,
        diff={"run_count": len(run_ids)},
    )

    db.delete(plan)
    db.commit()
    return success_response(request, {"plan_key": plan_key, "deleted": True})


@router.get("/{plan_key}")
def get_plan_detail(
    plan_key: str,
    request: Request,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(get_current_user),
):
    plan = find_plan_by_key(db, plan_key)
    version = plan.version
    suite_version = plan.suite_version

    runs = (
        db.query(TestRun)
        .filter(TestRun.plan_id == plan.id)
        .order_by(TestRun.started_at.desc(), TestRun.id.desc())
        .all()
    )

    return success_response(
        request,
        {
            "plan": {
                "plan_key": plan.plan_key,
                "version_key": version.version_key,
                "suite_version_key": suite_version.suite_version_key,
                "name": plan.name,
                "description": plan.description,
                "status": plan.status,
                "created_at": plan.created_at,
                "updated_at": plan.updated_at,
            },
            "runs": [_run_payload(db, run, plan, version.version_key) for run in runs],
        },
    )


@router.post("/{plan_key}/runs")
def create_plan_run(
    plan_key: str,
    payload: RunCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    _ensure_plan_editor(current_user)

    plan = find_plan_by_key(db, plan_key)
    run_name = payload.name.strip()
    if not run_name:
        raise AppError("VALIDATION_ERROR", "执行轮次名称不能为空", status_code=422)
    case_keys = set(payload.case_keys or []) if payload.case_keys else None
    run = create_run_from_suite_version(
        db,
        plan=plan,
        name=run_name,
        actor_id=current_user.id,
        build_no=payload.build_no,
        environment=payload.environment,
        case_keys=case_keys,
    )

    plan.status = PlanStatus.in_progress

    write_audit(
        db,
        current_user.id,
        action="plan.run.create",
        object_type="test_run",
        object_id=run.run_key,
        diff={"plan_key": plan.plan_key, "case_subset": len(case_keys) if case_keys else None},
    )

    db.commit()

    return success_response(request, _run_payload(db, run, plan, plan.version.version_key))
