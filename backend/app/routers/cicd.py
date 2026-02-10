from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import UserAccount, UserRole, get_db
from ..errors import AppError
from ..response import success_response
from ..services import write_audit

router = APIRouter(prefix="/api/v1/cicd", tags=["cicd"])

StageStatus = Literal["pending", "running", "success", "failed"]
RunStatus = Literal["pending", "running", "success", "failed"]


class TriggerRunRequest(BaseModel):
    branch: str = Field(min_length=1)
    commit_id: Optional[str] = None
    note: Optional[str] = None
    triggered_by: str = Field(min_length=1)


class UpdateStageRequest(BaseModel):
    status: StageStatus
    note: Optional[str] = None


_LOCK = RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _create_pipeline() -> dict:
    now = _now_iso()
    return {
        "pipeline_key": "hyperchain-binary",
        "pipeline_name": "Hyperchain 二进制 CICD",
        "project_name": "Hyperchain",
        "binary_name": "hyperchain",
        "build_machine": {
            "name": "内网构建机",
            "ip": "172.22.67.76",
            "note": "占位：后续补充真实登录凭据和构建环境",
        },
        "deploy_target": {
            "name": "制品分发机",
            "ip": "10.10.33.56",
            "note": "占位：后续补充部署目录与鉴权方式",
        },
        "build_script_path": "/opt/hyperchain/scripts/build_hyperchain.sh",
        "artifact_path": "/opt/hyperchain/output/hyperchain",
        "deploy_path": "/data/hyperchain/bin",
        "stages_template": [
            {
                "stage_key": "prepare",
                "name": "准备构建环境",
                "description": "连接构建机并准备源码、依赖和环境变量。",
                "command": "ssh 172.22.67.76 \"prepare_env.sh\"",
            },
            {
                "stage_key": "build",
                "name": "编译 Hyperchain 二进制",
                "description": "在构建机执行编译脚本，生成可发布二进制。",
                "command": "ssh 172.22.67.76 \"/opt/hyperchain/scripts/build_hyperchain.sh\"",
            },
            {
                "stage_key": "package",
                "name": "归档制品",
                "description": "收集并校验编译结果，形成发布制品。",
                "command": "ssh 172.22.67.76 \"sha256sum /opt/hyperchain/output/hyperchain\"",
            },
            {
                "stage_key": "scp",
                "name": "SCP 分发二进制",
                "description": "将二进制通过 scp 发送到目标机器指定目录。",
                "command": "scp /opt/hyperchain/output/hyperchain user@10.10.33.56:/data/hyperchain/bin/",
            },
        ],
        "updated_at": now,
    }


def _make_run(
    run_id: str,
    pipeline: dict,
    branch: str,
    commit_id: Optional[str],
    note: Optional[str],
    triggered_by: str,
) -> dict:
    now = _now_iso()
    stages = []
    for index, stage in enumerate(pipeline["stages_template"]):
        stages.append(
            {
                "stage_key": stage["stage_key"],
                "name": stage["name"],
                "description": stage["description"],
                "command": stage["command"],
                "status": "running" if index == 0 else "pending",
                "updated_at": now if index == 0 else None,
                "note": "占位：等待后续接入真实回调" if index == 0 else None,
            }
        )

    return {
        "run_id": run_id,
        "pipeline_key": pipeline["pipeline_key"],
        "pipeline_name": pipeline["pipeline_name"],
        "branch": branch,
        "commit_id": commit_id,
        "note": note,
        "status": "running",
        "triggered_by": triggered_by,
        "started_at": now,
        "finished_at": None,
        "stages": stages,
        "logs": [f"[trigger] {triggered_by} 触发流水线, branch={branch}"],
    }


_PIPELINES: dict[str, dict] = {"hyperchain-binary": _create_pipeline()}
_RUNS: dict[str, list[dict]] = {
    "hyperchain-binary": [
        {
            "run_id": "RUN-0001",
            "pipeline_key": "hyperchain-binary",
            "pipeline_name": "Hyperchain 二进制 CICD",
            "branch": "release/v1.0.0",
            "commit_id": "placeholder-commit",
            "note": "初始化占位流水线",
            "status": "running",
            "triggered_by": "qa",
            "started_at": _now_iso(),
            "finished_at": None,
            "stages": [
                {
                    "stage_key": "prepare",
                    "name": "准备构建环境",
                    "description": "连接构建机并准备源码、依赖和环境变量。",
                    "command": "ssh 172.22.67.76 \"prepare_env.sh\"",
                    "status": "success",
                    "updated_at": _now_iso(),
                    "note": "占位：环境准备完成",
                },
                {
                    "stage_key": "build",
                    "name": "编译 Hyperchain 二进制",
                    "description": "在构建机执行编译脚本，生成可发布二进制。",
                    "command": "ssh 172.22.67.76 \"/opt/hyperchain/scripts/build_hyperchain.sh\"",
                    "status": "running",
                    "updated_at": _now_iso(),
                    "note": "占位：正在构建",
                },
                {
                    "stage_key": "package",
                    "name": "归档制品",
                    "description": "收集并校验编译结果，形成发布制品。",
                    "command": "ssh 172.22.67.76 \"sha256sum /opt/hyperchain/output/hyperchain\"",
                    "status": "pending",
                    "updated_at": None,
                    "note": None,
                },
                {
                    "stage_key": "scp",
                    "name": "SCP 分发二进制",
                    "description": "将二进制通过 scp 发送到目标机器指定目录。",
                    "command": "scp /opt/hyperchain/output/hyperchain user@10.10.33.56:/data/hyperchain/bin/",
                    "status": "pending",
                    "updated_at": None,
                    "note": None,
                },
            ],
            "logs": [
                "[prepare] 占位: 构建环境已准备",
                "[build] 占位: build_hyperchain.sh 正在执行",
            ],
        }
    ]
}


def _find_run(run_id: str) -> tuple[str, dict]:
    for pipeline_key, pipeline_runs in _RUNS.items():
        for run in pipeline_runs:
            if run["run_id"] == run_id:
                return pipeline_key, run
    raise AppError("NOT_FOUND", f"流水线运行记录不存在: {run_id}", status_code=404)


@router.get("/pipelines/{pipeline_key}")
def get_pipeline(
    pipeline_key: str,
    request: Request,
    _: UserAccount = Depends(get_current_user),
):
    with _LOCK:
        pipeline = _PIPELINES.get(pipeline_key)
        if not pipeline:
            raise AppError("NOT_FOUND", f"流水线不存在: {pipeline_key}", status_code=404)
        return success_response(request, deepcopy(pipeline))


@router.get("/pipelines/{pipeline_key}/runs")
def list_runs(
    pipeline_key: str,
    request: Request,
    _: UserAccount = Depends(get_current_user),
):
    with _LOCK:
        if pipeline_key not in _PIPELINES:
            raise AppError("NOT_FOUND", f"流水线不存在: {pipeline_key}", status_code=404)
        return success_response(request, deepcopy(_RUNS.get(pipeline_key, [])))


@router.post("/pipelines/{pipeline_key}/runs")
def trigger_run(
    pipeline_key: str,
    payload: TriggerRunRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    if current_user.role == UserRole.viewer:
        raise AppError("FORBIDDEN", "Viewer 无权限触发 CICD", status_code=403)

    with _LOCK:
        pipeline = _PIPELINES.get(pipeline_key)
        if not pipeline:
            raise AppError("NOT_FOUND", f"流水线不存在: {pipeline_key}", status_code=404)

        run_count = sum(len(item) for item in _RUNS.values())
        run_id = f"RUN-{run_count + 1:04d}"
        run = _make_run(run_id, pipeline, payload.branch, payload.commit_id, payload.note, payload.triggered_by)
        _RUNS.setdefault(pipeline_key, []).insert(0, run)

    write_audit(
        db,
        current_user.id,
        action="cicd.run.trigger",
        object_type="cicd_run",
        object_id=run_id,
        diff={"pipeline": pipeline_key, "branch": payload.branch},
    )
    db.commit()

    return success_response(request, deepcopy(run))


@router.post("/runs/{run_id}/stages/{stage_key}:update")
def update_stage(
    run_id: str,
    stage_key: str,
    payload: UpdateStageRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    if current_user.role == UserRole.viewer:
        raise AppError("FORBIDDEN", "Viewer 无权限更新 CICD 阶段", status_code=403)

    with _LOCK:
        _, run = _find_run(run_id)
        stage_index = next((idx for idx, item in enumerate(run["stages"]) if item["stage_key"] == stage_key), -1)
        if stage_index < 0:
            raise AppError("NOT_FOUND", f"阶段不存在: {stage_key}", status_code=404)

        now = _now_iso()
        stage = run["stages"][stage_index]
        stage["status"] = payload.status
        stage["updated_at"] = now
        stage["note"] = payload.note
        run["logs"].insert(0, f"[{stage_key}] {payload.status}{' - ' + payload.note if payload.note else ''}")

        if payload.status == "failed":
            run["status"] = "failed"
            run["finished_at"] = now
        elif payload.status == "success":
            next_stage = run["stages"][stage_index + 1] if stage_index + 1 < len(run["stages"]) else None
            if next_stage and next_stage["status"] == "pending":
                next_stage["status"] = "running"
                next_stage["updated_at"] = now
                next_stage["note"] = "占位：等待手动推进或回调"

            all_success = all(item["status"] == "success" for item in run["stages"])
            run["status"] = "success" if all_success else "running"
            run["finished_at"] = now if all_success else None
        else:
            run["status"] = "running"
            run["finished_at"] = None

    write_audit(
        db,
        current_user.id,
        action="cicd.stage.update",
        object_type="cicd_run",
        object_id=run_id,
        diff={"stage_key": stage_key, "status": payload.status},
    )
    db.commit()

    return success_response(request, deepcopy(run))
