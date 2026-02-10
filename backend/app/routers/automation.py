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

router = APIRouter(prefix="/api/v1/automation", tags=["automation"])

FrameworkType = Literal["performance", "functional"]
OperationMode = Literal[
    "deploy_pressure_machine",
    "deploy_hyperchain",
    "deploy_and_test",
    "test_only",
    "functional_test",
]


class UpdateContentRequest(BaseModel):
    content: str
    updated_by: str = Field(min_length=1)


class TriggerAutomationRunRequest(BaseModel):
    configuration_key: str = Field(min_length=1)
    test_suite_key: str = Field(min_length=1)
    operation_mode: OperationMode
    note: Optional[str] = None
    triggered_by: str = Field(min_length=1)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_frameworks() -> dict[str, dict]:
    now = _now_iso()
    return {
        "frigateDynamic": {
            "framework_key": "frigateDynamic",
            "entry_name": "性能测试自动化",
            "display_name": "frigateDynamic",
            "framework_type": "performance",
            "description": (
                "frigateDynamic 负责自动部署压力机上的 frigate 与被测 "
                "hyperchain 二进制，并通过 SSH 触发一次性压测作业。"
            ),
            "streamlit_url": "http://172.22.67.76:8501",
            "build_machine": {
                "name": "构建/调度机",
                "ip": "172.22.67.76",
                "note": "占位：后续补充 SSH 账号、脚本路径与网络策略",
            },
            "deploy_target": {
                "name": "被测集群入口",
                "ip": "10.10.33.56",
                "note": "占位：后续补充二进制下发目录、配置目录",
            },
            "configurations": [
                {
                    "config_key": "perf-default",
                    "name": "默认性能配置",
                    "description": "占位配置，用于演示在线编辑与保存",
                    "content": "\n".join(
                        [
                            "job_name: frigate_dynamic_perf",
                            "pressure_host: 172.22.67.76",
                            "target_cluster_host: 10.10.33.56",
                            "frigate_package_path: /data/frigate/frigate.tar.gz",
                            "hyperchain_binary_path: /data/hyperchain/bin/hyperchain",
                            "ssh_user: placeholder_user",
                            "ssh_port: 22",
                        ]
                    ),
                    "updated_at": now,
                    "updated_by": "qa",
                },
                {
                    "config_key": "perf-long-run",
                    "name": "长稳压测配置",
                    "description": "用于长时压测的占位参数集",
                    "content": "\n".join(
                        [
                            "job_name: frigate_dynamic_long_run",
                            "duration_min: 180",
                            "rps: 1200",
                            "pressure_host: 172.22.67.76",
                            "target_cluster_host: 10.10.33.56",
                        ]
                    ),
                    "updated_at": now,
                    "updated_by": "admin",
                },
            ],
            "test_suites": [
                {
                    "suite_key": "suite-perf-smoke",
                    "name": "性能冒烟套件",
                    "description": "快速验证部署与基本负载打通",
                    "content": "\n".join(
                        [
                            "suite: perf_smoke",
                            "scenario: basic_transfer",
                            "users: 50",
                            "duration_min: 10",
                        ]
                    ),
                    "updated_at": now,
                    "updated_by": "qa",
                },
                {
                    "suite_key": "suite-perf-throughput",
                    "name": "吞吐压测套件",
                    "description": "压测吞吐与稳定性",
                    "content": "\n".join(
                        [
                            "suite: perf_throughput",
                            "scenario: tx_stress",
                            "users: 500",
                            "duration_min: 60",
                        ]
                    ),
                    "updated_at": now,
                    "updated_by": "admin",
                },
            ],
            "operation_modes": [
                {
                    "mode": "deploy_pressure_machine",
                    "label": "单独部署测试机",
                    "description": "仅在压力机部署或更新 frigate，不触发压测。",
                },
                {
                    "mode": "deploy_hyperchain",
                    "label": "单独部署 Hyperchain",
                    "description": "仅向被测集群下发 hyperchain 二进制及配置。",
                },
                {
                    "mode": "deploy_and_test",
                    "label": "一键部署及压测",
                    "description": "串行执行部署压力机、部署被测集群并触发压测。",
                },
                {
                    "mode": "test_only",
                    "label": "仅执行压测",
                    "description": "跳过部署步骤，直接通过 SSH 触发 frigate 压测。",
                },
            ],
            "updated_at": now,
        },
        "hypersonic": {
            "framework_key": "hypersonic",
            "entry_name": "功能测试自动化",
            "display_name": "hypersonic",
            "framework_type": "functional",
            "description": "hypersonic 用于执行功能回归自动化测试，支持配置与测试套在线维护和触发运行。",
            "build_machine": {
                "name": "功能测试执行机",
                "ip": "172.22.67.76",
                "note": "占位：后续补充执行入口脚本与运行环境",
            },
            "deploy_target": {
                "name": "被测服务入口",
                "ip": "10.10.33.56",
                "note": "占位：后续补充服务地址、鉴权与环境变量",
            },
            "configurations": [
                {
                    "config_key": "func-default",
                    "name": "默认功能配置",
                    "description": "基础回归配置",
                    "content": "\n".join(
                        [
                            "suite_mode: full_regression",
                            "target_env: testnet",
                            "api_base_url: http://10.10.33.56:8080",
                            "report_dir: /data/hypersonic/report",
                        ]
                    ),
                    "updated_at": now,
                    "updated_by": "qa",
                },
                {
                    "config_key": "func-fast",
                    "name": "快速回归配置",
                    "description": "用于 CI 快速验证",
                    "content": "\n".join(
                        [
                            "suite_mode: smoke",
                            "target_env: testnet",
                            "parallelism: 4",
                        ]
                    ),
                    "updated_at": now,
                    "updated_by": "admin",
                },
            ],
            "test_suites": [
                {
                    "suite_key": "suite-func-core",
                    "name": "核心交易回归",
                    "description": "覆盖核心交易与账户流程",
                    "content": "\n".join(
                        [
                            "suite: core_tx",
                            "cases:",
                            "- account/create",
                            "- transfer/basic",
                            "- transfer/rollback",
                        ]
                    ),
                    "updated_at": now,
                    "updated_by": "qa",
                },
                {
                    "suite_key": "suite-func-contract",
                    "name": "合约功能回归",
                    "description": "覆盖合约部署、调用、升级流程",
                    "content": "\n".join(
                        [
                            "suite: contract_regression",
                            "cases:",
                            "- contract/deploy",
                            "- contract/invoke",
                            "- contract/upgrade",
                        ]
                    ),
                    "updated_at": now,
                    "updated_by": "admin",
                },
            ],
            "operation_modes": [
                {
                    "mode": "functional_test",
                    "label": "执行功能测试",
                    "description": "按所选配置与测试套执行功能自动化测试。",
                }
            ],
            "updated_at": now,
        },
    }


def _build_initial_runs() -> dict[str, list[dict]]:
    now = _now_iso()
    return {
        "frigateDynamic": [
            {
                "run_id": "AUTO-0001",
                "framework_key": "frigateDynamic",
                "entry_name": "性能测试自动化",
                "configuration_key": "perf-default",
                "test_suite_key": "suite-perf-smoke",
                "operation_mode": "deploy_and_test",
                "status": "running",
                "note": "占位：夜间冒烟压测",
                "triggered_by": "qa",
                "started_at": now,
                "finished_at": None,
                "logs": [
                    "[deploy_pressure_machine] 占位：已连接压力机 172.22.67.76",
                    "[deploy_hyperchain] 占位：已下发二进制到 10.10.33.56",
                    "[test_only] 占位：已通过 SSH 启动 frigate 压测",
                ],
            }
        ],
        "hypersonic": [
            {
                "run_id": "AUTO-0002",
                "framework_key": "hypersonic",
                "entry_name": "功能测试自动化",
                "configuration_key": "func-fast",
                "test_suite_key": "suite-func-core",
                "operation_mode": "functional_test",
                "status": "success",
                "note": "占位：每日功能回归",
                "triggered_by": "admin",
                "started_at": now,
                "finished_at": now,
                "logs": [
                    "[functional_test] 占位：执行 42 条用例，42 通过，0 失败",
                ],
            }
        ],
    }


def _build_logs(framework_key: str, mode: OperationMode) -> list[str]:
    if framework_key == "frigateDynamic":
        if mode == "deploy_pressure_machine":
            return [
                "[deploy_pressure_machine] 占位：连接 172.22.67.76 并部署 frigate",
                "[deploy_pressure_machine] 占位：部署完成，等待下一步动作",
            ]
        if mode == "deploy_hyperchain":
            return [
                "[deploy_hyperchain] 占位：上传 hyperchain 二进制到 10.10.33.56 指定目录",
                "[deploy_hyperchain] 占位：同步配置文件完成",
            ]
        if mode == "deploy_and_test":
            return [
                "[deploy_pressure_machine] 占位：部署压力机组件完成",
                "[deploy_hyperchain] 占位：部署被测 hyperchain 完成",
                "[test_only] 占位：通过 SSH 在压力机上启动 frigate 压测",
            ]
        return ["[test_only] 占位：跳过部署，直接触发压测任务"]

    return [
        "[functional_test] 占位：加载 hypersonic 配置与测试套",
        "[functional_test] 占位：执行功能回归并生成报告",
    ]


_LOCK = RLock()
_FRAMEWORKS: dict[str, dict] = _build_frameworks()
_RUNS: dict[str, list[dict]] = _build_initial_runs()


def _get_framework(framework_key: str) -> dict:
    framework = _FRAMEWORKS.get(framework_key)
    if not framework:
        raise AppError("NOT_FOUND", f"自动化框架不存在: {framework_key}", status_code=404)
    return framework


def _require_editor(current_user: UserAccount) -> None:
    if current_user.role == UserRole.viewer:
        raise AppError("FORBIDDEN", "Viewer 无权限执行该操作", status_code=403)


def _find_configuration(framework: dict, config_key: str) -> dict:
    config = next((item for item in framework["configurations"] if item["config_key"] == config_key), None)
    if not config:
        raise AppError("NOT_FOUND", f"配置不存在: {config_key}", status_code=404)
    return config


def _find_test_suite(framework: dict, suite_key: str) -> dict:
    suite = next((item for item in framework["test_suites"] if item["suite_key"] == suite_key), None)
    if not suite:
        raise AppError("NOT_FOUND", f"测试套不存在: {suite_key}", status_code=404)
    return suite


@router.get("/frameworks/{framework_key}")
def get_framework(
    framework_key: str,
    request: Request,
    _: UserAccount = Depends(get_current_user),
):
    with _LOCK:
        framework = _get_framework(framework_key)
        return success_response(request, deepcopy(framework))


@router.get("/frameworks/{framework_key}/runs")
def list_framework_runs(
    framework_key: str,
    request: Request,
    _: UserAccount = Depends(get_current_user),
):
    with _LOCK:
        _get_framework(framework_key)
        runs = sorted(_RUNS.get(framework_key, []), key=lambda item: item["started_at"], reverse=True)
        return success_response(request, deepcopy(runs))


@router.put("/frameworks/{framework_key}/configurations/{config_key}")
def update_configuration(
    framework_key: str,
    config_key: str,
    payload: UpdateContentRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    _require_editor(current_user)

    with _LOCK:
        framework = _get_framework(framework_key)
        target = _find_configuration(framework, config_key)
        now = _now_iso()
        target["content"] = payload.content
        target["updated_at"] = now
        target["updated_by"] = payload.updated_by
        framework["updated_at"] = now

    write_audit(
        db,
        current_user.id,
        action="automation.configuration.update",
        object_type="automation_framework",
        object_id=framework_key,
        diff={"config_key": config_key},
    )
    db.commit()
    return success_response(request, deepcopy(framework))


@router.put("/frameworks/{framework_key}/testsuites/{suite_key}")
def update_test_suite(
    framework_key: str,
    suite_key: str,
    payload: UpdateContentRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    _require_editor(current_user)

    with _LOCK:
        framework = _get_framework(framework_key)
        target = _find_test_suite(framework, suite_key)
        now = _now_iso()
        target["content"] = payload.content
        target["updated_at"] = now
        target["updated_by"] = payload.updated_by
        framework["updated_at"] = now

    write_audit(
        db,
        current_user.id,
        action="automation.testsuite.update",
        object_type="automation_framework",
        object_id=framework_key,
        diff={"suite_key": suite_key},
    )
    db.commit()
    return success_response(request, deepcopy(framework))


@router.post("/frameworks/{framework_key}/runs")
def trigger_automation_run(
    framework_key: str,
    payload: TriggerAutomationRunRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    _require_editor(current_user)

    with _LOCK:
        framework = _get_framework(framework_key)
        _find_configuration(framework, payload.configuration_key)
        _find_test_suite(framework, payload.test_suite_key)

        supported_modes = {item["mode"] for item in framework["operation_modes"]}
        if payload.operation_mode not in supported_modes:
            raise AppError("VALIDATION_ERROR", f"不支持的执行模式: {payload.operation_mode}", status_code=422)

        run_count = sum(len(items) for items in _RUNS.values())
        run_id = f"AUTO-{run_count + 1:04d}"
        now = _now_iso()
        status = "running" if framework["framework_type"] == "performance" and payload.operation_mode == "deploy_and_test" else "success"

        run = {
            "run_id": run_id,
            "framework_key": framework_key,
            "entry_name": framework["entry_name"],
            "configuration_key": payload.configuration_key,
            "test_suite_key": payload.test_suite_key,
            "operation_mode": payload.operation_mode,
            "status": status,
            "note": payload.note,
            "triggered_by": payload.triggered_by,
            "started_at": now,
            "finished_at": None if status == "running" else now,
            "logs": _build_logs(framework_key, payload.operation_mode),
        }
        _RUNS.setdefault(framework_key, []).insert(0, run)

    write_audit(
        db,
        current_user.id,
        action="automation.run.trigger",
        object_type="automation_run",
        object_id=run_id,
        diff={
            "framework_key": framework_key,
            "configuration_key": payload.configuration_key,
            "test_suite_key": payload.test_suite_key,
            "operation_mode": payload.operation_mode,
        },
    )
    db.commit()
    return success_response(request, deepcopy(run))
