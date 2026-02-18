from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from shlex import quote as shell_quote, split as shell_split
from threading import Event, RLock, Thread
from time import monotonic, sleep
from typing import Any, Literal, Optional

import paramiko
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import (
    AutomationConfiguration,
    AutomationRun,
    AutomationRunLog,
    AutomationRunStatus,
    AutomationSuite,
    SessionLocal,
    UserAccount,
    UserRole,
    get_db,
    utcnow,
)
from ..errors import AppError
from ..response import success_response
from ..services import write_audit
from ..settings import get_settings

router = APIRouter(prefix="/api/v1/automation", tags=["automation"])

FrameworkType = Literal["performance", "functional"]
OperationMode = Literal[
    "deploy_pressure_machine",
    "deploy_hyperchain",
    "deploy_and_test",
    "test_only",
    "functional_test",
]
FrigateFileKind = Literal["configuration", "testsuite"]


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


def _iso_from_epoch(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


_SETTINGS = get_settings()
_LOCK = RLock()
_MAX_RUN_LOG_LINES = 2000
_TERMINAL_STATUSES = {AutomationRunStatus.success, AutomationRunStatus.failed, AutomationRunStatus.canceled}
_PATH_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._/-]+$")

_HYPERSONIC_DISPATCH_EVENT = Event()
_HYPERSONIC_DISPATCHER_STARTED = False
_HYPERSONIC_RECOVERED = False
_HYPERSONIC_MONITORING_RUN_IDS: set[str] = set()

_DEFAULT_HYPERSONIC_CONFIGS = [
    {
        "config_key": "func-default",
        "name": "默认功能配置",
        "description": "默认执行 p0 回归，保留失败日志",
        "content": "\n".join(
            [
                "level: p0",
                "log: FAILED",
                "repeat: 1",
                "timeout_sec: 7200",
                'conf_json: {"system": {"http.security": false}, "whitelist": {"whitelist.api.enable": false}}',
            ]
        ),
        "updated_by": "system",
    },
    {
        "config_key": "func-fast",
        "name": "快速回归配置",
        "description": "快速验证配置，可手工调整 pytest 参数",
        "content": "\n".join(
            [
                "level: p0",
                "log: FAILED",
                "repeat: 1",
                "timeout_sec: 3600",
                "extra_pytest_args: -s -vv",
            ]
        ),
        "updated_by": "system",
    },
]

_DEFAULT_HYPERSONIC_FALLBACK_SUITES = [
    {
        "suite_key": "demo",
        "name": "demo",
        "description": "默认 demo 套件（ci_list 不可用时兜底）",
        "module_name": "demo",
        "path_expr": ".",
        "testpaths": ["testcases/demo"],
        "python_files": ["test_*.py"],
        "source_type": "seed",
    }
]


def _build_frameworks() -> dict[str, dict]:
    now = _now_iso()
    frigate_build_machine_ip = _SETTINGS.frigate_dynamic_build_machine_ip
    frigate_target_ip = _SETTINGS.frigate_dynamic_deploy_target_ip
    frigate_streamlit_url = _SETTINGS.frigate_dynamic_streamlit_url

    return {
        "frigateDynamic": {
            "framework_key": "frigateDynamic",
            "entry_name": "性能测试自动化",
            "display_name": "frigateDynamic",
            "framework_type": "performance",
            "description": "frigateDynamic 真实集成未启用，当前为本地占位模式。",
            "streamlit_url": frigate_streamlit_url,
            "build_machine": {
                "name": "构建/调度机",
                "ip": frigate_build_machine_ip,
                "note": "占位：启用 FRIGATE_DYNAMIC_LIVE_ENABLED 后将实时读取远端配置",
            },
            "deploy_target": {
                "name": "被测集群入口",
                "ip": frigate_target_ip,
                "note": "占位：后续补充二进制下发目录、配置目录",
            },
            "configurations": [
                {
                    "config_key": "perf-default",
                    "name": "perf-default",
                    "description": "占位配置，用于演示在线编辑与保存",
                    "content": "\n".join(
                        [
                            "job_name: frigate_dynamic_perf",
                            f"pressure_host: {frigate_build_machine_ip}",
                            f"target_cluster_host: {frigate_target_ip}",
                            "frigate_package_path: /data/frigate/frigate.tar.gz",
                            "hyperchain_binary_path: /data/hyperchain/bin/hyperchain",
                            "ssh_user: placeholder_user",
                            "ssh_port: 22",
                        ]
                    ),
                    "updated_at": now,
                    "updated_by": "qa",
                }
            ],
            "test_suites": [
                {
                    "suite_key": "suite-perf-smoke",
                    "name": "suite-perf-smoke",
                    "description": "占位测试套",
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
                }
            ],
            "operation_modes": [
                {
                    "mode": "deploy_and_test",
                    "label": "一键压测",
                    "description": "执行 main.run_main，读取 global_config 与 testsuite。",
                },
                {
                    "mode": "deploy_hyperchain",
                    "label": "仅部署链",
                    "description": "执行 tools.deploy，仅按 global_config 部署链侧。",
                },
                {
                    "mode": "deploy_pressure_machine",
                    "label": "仅部署压测机",
                    "description": "执行 tools.deploy_frigate，仅部署压测机组件。",
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
                "ip": _SETTINGS.hypersonic_ssh_host,
                "note": "执行入口：SSH + docker run（每测试套独立容器）",
            },
            "deploy_target": {
                "name": "被测服务入口",
                "ip": _SETTINGS.frigate_dynamic_deploy_target_ip,
                "note": "目标服务由配置项中的环境信息决定",
            },
            "configurations": [],
            "test_suites": [],
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
    return {
        "frigateDynamic": [],
    }


_FRAMEWORKS: dict[str, dict] = _build_frameworks()
_RUNS: dict[str, list[dict]] = _build_initial_runs()
_FRIGATE_FILE_EDITORS: dict[tuple[FrigateFileKind, str], str] = {}


def _is_frigate_live_enabled() -> bool:
    return _SETTINGS.frigate_dynamic_live_enabled


def _is_hypersonic_live_enabled() -> bool:
    return _SETTINGS.hypersonic_live_enabled


def _connect_frigate_ssh() -> paramiko.SSHClient:
    if not _SETTINGS.frigate_dynamic_ssh_password:
        raise AppError(
            "CONFIG_ERROR",
            "未配置 FRIGATE_DYNAMIC_SSH_PASSWORD，无法启用真实 frigateDynamic 集成",
            status_code=500,
        )

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=_SETTINGS.frigate_dynamic_ssh_host,
            port=_SETTINGS.frigate_dynamic_ssh_port,
            username=_SETTINGS.frigate_dynamic_ssh_user,
            password=_SETTINGS.frigate_dynamic_ssh_password,
            timeout=_SETTINGS.frigate_dynamic_ssh_timeout_sec,
            auth_timeout=_SETTINGS.frigate_dynamic_ssh_timeout_sec,
            banner_timeout=_SETTINGS.frigate_dynamic_ssh_timeout_sec,
            look_for_keys=False,
            allow_agent=False,
        )
    except Exception as exc:
        raise AppError("UPSTREAM_ERROR", f"连接 frigateDynamic SSH 失败: {exc}", status_code=502) from exc
    return client


def _connect_hypersonic_ssh() -> paramiko.SSHClient:
    if not _SETTINGS.hypersonic_ssh_password:
        raise AppError(
            "CONFIG_ERROR",
            "未配置 HYPERSONIC_SSH_PASSWORD，无法启用真实 hypersonic 集成",
            status_code=500,
        )

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=_SETTINGS.hypersonic_ssh_host,
            port=_SETTINGS.hypersonic_ssh_port,
            username=_SETTINGS.hypersonic_ssh_user,
            password=_SETTINGS.hypersonic_ssh_password,
            timeout=_SETTINGS.hypersonic_ssh_timeout_sec,
            auth_timeout=_SETTINGS.hypersonic_ssh_timeout_sec,
            banner_timeout=_SETTINGS.hypersonic_ssh_timeout_sec,
            look_for_keys=False,
            allow_agent=False,
        )
    except Exception as exc:
        raise AppError("UPSTREAM_ERROR", f"连接 hypersonic SSH 失败: {exc}", status_code=502) from exc
    return client


def _remote_dir(kind: FrigateFileKind) -> PurePosixPath:
    root = PurePosixPath(_SETTINGS.frigate_dynamic_remote_root)
    return root / ("conf" if kind == "configuration" else "testsuites")


def _normalize_toml_filename(key: str) -> str:
    filename = key.strip()
    if not filename:
        raise AppError("VALIDATION_ERROR", "文件名不能为空", status_code=422)
    if "/" in filename or "\\" in filename:
        raise AppError("VALIDATION_ERROR", f"非法文件名: {key}", status_code=422)
    if filename in {".", ".."}:
        raise AppError("VALIDATION_ERROR", f"非法文件名: {key}", status_code=422)
    if not filename.endswith(".toml"):
        filename = f"{filename}.toml"
    return filename


def _read_remote_toml_entries(kind: FrigateFileKind) -> list[dict]:
    remote_dir = _remote_dir(kind)
    client = _connect_frigate_ssh()
    sftp = None
    try:
        sftp = client.open_sftp()
        attrs = [
            attr
            for attr in sftp.listdir_attr(str(remote_dir))
            if attr.filename.endswith(".toml") and "/" not in attr.filename
        ]
        attrs.sort(key=lambda item: item.filename.lower())

        entries: list[dict] = []
        for attr in attrs:
            remote_file = str(remote_dir / attr.filename)
            with sftp.open(remote_file, "r") as file_obj:
                raw_content = file_obj.read()

            content = (
                raw_content.decode("utf-8", errors="replace")
                if isinstance(raw_content, (bytes, bytearray))
                else str(raw_content)
            )
            updated_at = _iso_from_epoch(getattr(attr, "st_mtime", 0) or 0)
            updated_by = _FRIGATE_FILE_EDITORS.get((kind, attr.filename), "frigateDynamic")

            if kind == "configuration":
                entries.append(
                    {
                        "config_key": attr.filename,
                        "name": attr.filename,
                        "description": f"读取自 {remote_file}",
                        "content": content,
                        "updated_at": updated_at,
                        "updated_by": updated_by,
                    }
                )
            else:
                entries.append(
                    {
                        "suite_key": attr.filename,
                        "name": attr.filename,
                        "description": f"读取自 {remote_file}",
                        "content": content,
                        "updated_at": updated_at,
                        "updated_by": updated_by,
                    }
                )

        return entries
    except Exception as exc:
        raise AppError("UPSTREAM_ERROR", f"读取 frigateDynamic 文件失败: {exc}", status_code=502) from exc
    finally:
        if sftp is not None:
            sftp.close()
        client.close()


def _write_remote_toml(kind: FrigateFileKind, key: str, content: str, updated_by: str) -> None:
    filename = _normalize_toml_filename(key)
    remote_file = str(_remote_dir(kind) / filename)

    client = _connect_frigate_ssh()
    sftp = None
    try:
        sftp = client.open_sftp()
        sftp.stat(remote_file)
        with sftp.open(remote_file, "w") as file_obj:
            file_obj.write(content)
        _FRIGATE_FILE_EDITORS[(kind, filename)] = updated_by
    except FileNotFoundError as exc:
        raise AppError("NOT_FOUND", f"文件不存在: {filename}", status_code=404) from exc
    except Exception as exc:
        raise AppError("UPSTREAM_ERROR", f"写入 frigateDynamic 文件失败: {exc}", status_code=502) from exc
    finally:
        if sftp is not None:
            sftp.close()
        client.close()


def _build_frigate_framework_live() -> dict:
    now = _now_iso()
    configurations = _read_remote_toml_entries("configuration")
    suites = _read_remote_toml_entries("testsuite")

    return {
        "framework_key": "frigateDynamic",
        "entry_name": "性能测试自动化",
        "display_name": "frigateDynamic",
        "framework_type": "performance",
        "description": "配置与测试套实时读取自远端 frigateDynamic 目录，并通过 SSH 触发容器内执行。",
        "streamlit_url": _SETTINGS.frigate_dynamic_streamlit_url,
        "build_machine": {
            "name": "frigateDynamic 宿主机",
            "ip": _SETTINGS.frigate_dynamic_ssh_host,
            "note": "真实执行入口：SSH + docker exec",
        },
        "deploy_target": {
            "name": "被测集群入口",
            "ip": _SETTINGS.frigate_dynamic_deploy_target_ip,
            "note": "目标机信息可按需在配置文件中维护",
        },
        "configurations": configurations,
        "test_suites": suites,
        "operation_modes": [
            {
                "mode": "deploy_and_test",
                "label": "一键压测",
                "description": "等价 Streamlit 的“一键压测”：python -m main.run_main",
            },
            {
                "mode": "deploy_hyperchain",
                "label": "仅部署链",
                "description": "等价 Streamlit 的“仅部署链”：python -m tools.deploy",
            },
            {
                "mode": "deploy_pressure_machine",
                "label": "仅部署压测机",
                "description": "等价 Streamlit 的“仅部署压测机”：python -m tools.deploy_frigate",
            },
        ],
        "updated_at": now,
    }


def _get_framework(framework_key: str, db: Session | None = None) -> dict:
    if framework_key == "frigateDynamic" and _is_frigate_live_enabled():
        return _build_frigate_framework_live()

    if framework_key == "hypersonic":
        if db is None:
            raise AppError("INTERNAL_ERROR", "缺少数据库会话", status_code=500)
        _ensure_hypersonic_seed_data(db)
        return _build_hypersonic_framework(db)

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


def _build_remote_execute_command(mode: OperationMode, config_key: str, suite_key: str) -> str:
    config_name = _normalize_toml_filename(config_key)
    suite_name = _normalize_toml_filename(suite_key)

    global_config = f"conf/{config_name}"
    testsuite = f"testsuites/{suite_name}"
    python_bin = shell_quote(_SETTINGS.frigate_dynamic_remote_python_bin)

    if mode == "deploy_and_test":
        action_cmd = (
            f"{python_bin} -m main.run_main "
            f"--global_config={shell_quote(global_config)} "
            f"--testsuite={shell_quote(testsuite)}"
        )
    elif mode == "deploy_hyperchain":
        action_cmd = f"{python_bin} -m tools.deploy --global_config={shell_quote(global_config)}"
    elif mode == "deploy_pressure_machine":
        action_cmd = f"{python_bin} -m tools.deploy_frigate --global_config={shell_quote(global_config)}"
    else:
        raise AppError("VALIDATION_ERROR", f"frigateDynamic 不支持执行模式: {mode}", status_code=422)

    inner_cmd = f"cd {shell_quote(_SETTINGS.frigate_dynamic_remote_container_workdir)} && {action_cmd}"
    container_name = shell_quote(_SETTINGS.frigate_dynamic_remote_container_name)
    return f"docker exec {container_name} bash -lc {shell_quote(inner_cmd)}"


def _append_run_log(framework_key: str, run_id: str, message: str) -> None:
    with _LOCK:
        run = next((item for item in _RUNS.get(framework_key, []) if item["run_id"] == run_id), None)
        if not run:
            return
        run["logs"].append(message)
        if len(run["logs"]) > _MAX_RUN_LOG_LINES:
            run["logs"] = run["logs"][-_MAX_RUN_LOG_LINES:]


def _finish_run(framework_key: str, run_id: str, status: str) -> None:
    with _LOCK:
        run = next((item for item in _RUNS.get(framework_key, []) if item["run_id"] == run_id), None)
        if not run:
            return
        run["status"] = status
        run["finished_at"] = _now_iso()


def _execute_frigate_run(framework_key: str, run_id: str, command: str) -> None:
    client = None
    try:
        _append_run_log(framework_key, run_id, f"[system] 远端执行命令: {command}")
        client = _connect_frigate_ssh()
        _, stdout, stderr = client.exec_command(command, get_pty=True)

        channel = stdout.channel
        buffer = ""

        while True:
            had_data = False
            if channel.recv_ready():
                had_data = True
                buffer += channel.recv(4096).decode("utf-8", errors="replace")
            if channel.recv_stderr_ready():
                had_data = True
                buffer += channel.recv_stderr(4096).decode("utf-8", errors="replace")

            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.rstrip("\r")
                if line:
                    _append_run_log(framework_key, run_id, line)

            if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                break

            if not had_data:
                sleep(0.2)

        if buffer.strip():
            _append_run_log(framework_key, run_id, buffer.strip())

        exit_code = channel.recv_exit_status()
        if exit_code == 0:
            _append_run_log(framework_key, run_id, "[system] 任务执行完成")
            _finish_run(framework_key, run_id, "success")
        else:
            _append_run_log(framework_key, run_id, f"[system] 任务执行失败，退出码: {exit_code}")
            _finish_run(framework_key, run_id, "failed")
    except Exception as exc:
        _append_run_log(framework_key, run_id, f"[system] 远端执行异常: {exc}")
        _finish_run(framework_key, run_id, "failed")
    finally:
        if client is not None:
            client.close()


def _serialize_configuration(row: AutomationConfiguration) -> dict:
    return {
        "config_key": row.config_key,
        "name": row.name,
        "description": row.description or "",
        "content": row.content,
        "updated_at": row.updated_at.isoformat(),
        "updated_by": row.updated_by,
    }


def _serialize_suite(row: AutomationSuite) -> dict:
    return {
        "suite_key": row.suite_key,
        "name": row.name,
        "description": row.description or "",
        "content": row.content,
        "updated_at": row.updated_at.isoformat(),
        "updated_by": row.updated_by,
    }


def _build_hypersonic_framework(db: Session) -> dict:
    template = deepcopy(_FRAMEWORKS["hypersonic"])
    configs = (
        db.query(AutomationConfiguration)
        .filter(AutomationConfiguration.framework_key == "hypersonic")
        .order_by(AutomationConfiguration.config_key.asc())
        .all()
    )
    suites = (
        db.query(AutomationSuite)
        .filter(AutomationSuite.framework_key == "hypersonic")
        .order_by(AutomationSuite.suite_key.asc())
        .all()
    )

    template["configurations"] = [_serialize_configuration(row) for row in configs]
    template["test_suites"] = [_serialize_suite(row) for row in suites]

    latest = None
    if configs:
        latest = max(row.updated_at for row in configs)
    if suites:
        suite_latest = max(row.updated_at for row in suites)
        latest = suite_latest if latest is None else max(latest, suite_latest)
    template["updated_at"] = (latest or utcnow()).isoformat()
    return template


def _generate_hypersonic_run_id(db: Session) -> str:
    count = db.query(func.count(AutomationRun.id)).filter(AutomationRun.run_id.like("AUTO-%")).scalar() or 0
    seq = int(count) + 1
    while True:
        run_id = f"AUTO-{seq:04d}"
        exists = db.query(AutomationRun.id).filter(AutomationRun.run_id == run_id).first()
        if not exists:
            return run_id
        seq += 1


def _append_hypersonic_log(db: Session, run: AutomationRun, message: str) -> None:
    run.log_cursor += 1
    db.add(
        AutomationRunLog(
            run_id=run.id,
            seq=run.log_cursor,
            line=message,
        )
    )
    if run.log_cursor > _MAX_RUN_LOG_LINES:
        cutoff = run.log_cursor - _MAX_RUN_LOG_LINES
        db.query(AutomationRunLog).filter(
            AutomationRunLog.run_id == run.id,
            AutomationRunLog.seq <= cutoff,
        ).delete(synchronize_session=False)


def _serialize_hypersonic_run(db: Session, run: AutomationRun, include_logs: bool = True) -> dict:
    logs: list[str] = []
    if include_logs:
        log_rows = (
            db.query(AutomationRunLog.line)
            .filter(AutomationRunLog.run_id == run.id)
            .order_by(AutomationRunLog.seq.asc())
            .all()
        )
        logs = [row.line for row in log_rows]

    return {
        "run_id": run.run_id,
        "framework_key": run.framework_key,
        "entry_name": run.entry_name,
        "configuration_key": run.configuration_key,
        "test_suite_key": run.test_suite_key,
        "operation_mode": run.operation_mode,
        "status": run.status.value,
        "note": run.note,
        "triggered_by": run.triggered_by,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "logs": logs,
        "report_archive_path": run.report_archive_path,
    }


def _run_ssh_wait(client: paramiko.SSHClient, command: str, *, get_pty: bool = False) -> tuple[int, str, str]:
    _, stdout, stderr = client.exec_command(command, get_pty=get_pty)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    return exit_code, out, err


def _validate_path_segment(value: str, field_name: str) -> str:
    text = value.strip()
    if not text:
        raise AppError("VALIDATION_ERROR", f"{field_name} 不能为空", status_code=422)
    if not _PATH_SEGMENT_RE.fullmatch(text):
        raise AppError("VALIDATION_ERROR", f"{field_name} 包含非法字符: {value}", status_code=422)
    if ".." in text or text.startswith("/") or text.startswith("./") or text.startswith("../"):
        raise AppError("VALIDATION_ERROR", f"{field_name} 非法: {value}", status_code=422)
    if "\\" in text:
        raise AppError("VALIDATION_ERROR", f"{field_name} 非法: {value}", status_code=422)
    return text


def _build_testpaths(module_name: str, path_expr: str) -> list[str]:
    module = module_name.strip()
    path = path_expr.strip()

    if not module:
        return ["testcases"]

    safe_module = _validate_path_segment(module, "module")
    if not path or path == ".":
        return [f"testcases/{safe_module}"]

    parts = [item for item in path.split(" ") if item.strip()]
    if not parts:
        return [f"testcases/{safe_module}"]

    testpaths: list[str] = []
    for part in parts:
        if part == ".":
            testpaths.append(f"testcases/{safe_module}")
            continue
        safe_part = _validate_path_segment(part, "path")
        testpaths.append(f"testcases/{safe_module}/{safe_part}")
    return testpaths


def _build_suite_content(suite_key: str, module_name: str, path_expr: str, testpaths: list[str]) -> str:
    payload = {
        "suite_key": suite_key,
        "module": module_name,
        "path": path_expr or ".",
        "testpaths": testpaths,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _load_hypersonic_ci_suites(*, raise_on_missing: bool) -> list[dict]:
    source_path = Path(_SETTINGS.hypersonic_ci_list_path)
    if not source_path.exists():
        if raise_on_missing:
            raise AppError("CONFIG_ERROR", f"未找到 ci_list.json: {source_path}", status_code=500)
        return []

    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except Exception as exc:
        if raise_on_missing:
            raise AppError("CONFIG_ERROR", f"解析 ci_list.json 失败: {exc}", status_code=500) from exc
        return []

    if not isinstance(payload, dict):
        if raise_on_missing:
            raise AppError("CONFIG_ERROR", "ci_list.json 顶层结构必须为对象", status_code=500)
        return []

    suites: list[dict] = []
    for suite_key in sorted(payload.keys()):
        info = payload.get(suite_key)
        if not isinstance(info, dict):
            continue

        module_name = str(info.get("module") or "").strip()
        path_expr = str(info.get("path") or "").strip()
        testpaths = _build_testpaths(module_name, path_expr)
        content = _build_suite_content(suite_key, module_name, path_expr, testpaths)

        suites.append(
            {
                "suite_key": suite_key,
                "name": suite_key,
                "description": f"同步自 ci_list: module={module_name or '*'} path={path_expr or '.'}",
                "content": content,
                "module_name": module_name,
                "path_expr": path_expr,
                "testpaths": testpaths,
                "python_files": ["test_*.py"],
                "source_type": "ci_list",
            }
        )

    return suites


def _ensure_hypersonic_seed_data(db: Session) -> None:
    cfg_count = (
        db.query(func.count(AutomationConfiguration.id))
        .filter(AutomationConfiguration.framework_key == "hypersonic")
        .scalar()
        or 0
    )
    if cfg_count == 0:
        for item in _DEFAULT_HYPERSONIC_CONFIGS:
            db.add(
                AutomationConfiguration(
                    framework_key="hypersonic",
                    config_key=item["config_key"],
                    name=item["name"],
                    description=item["description"],
                    content=item["content"],
                    updated_by=item["updated_by"],
                )
            )

    suite_count = (
        db.query(func.count(AutomationSuite.id))
        .filter(AutomationSuite.framework_key == "hypersonic")
        .scalar()
        or 0
    )
    if suite_count == 0:
        suites = _load_hypersonic_ci_suites(raise_on_missing=False)
        if not suites:
            suites = []
            for item in _DEFAULT_HYPERSONIC_FALLBACK_SUITES:
                suites.append(
                    {
                        **item,
                        "content": _build_suite_content(
                            item["suite_key"],
                            item["module_name"],
                            item["path_expr"],
                            item["testpaths"],
                        ),
                    }
                )

        for item in suites:
            db.add(
                AutomationSuite(
                    framework_key="hypersonic",
                    suite_key=item["suite_key"],
                    name=item["name"],
                    description=item["description"],
                    content=item["content"],
                    module_name=item["module_name"],
                    path_expr=item["path_expr"],
                    testpaths_json=item["testpaths"],
                    python_files_json=item["python_files"],
                    source_type=item["source_type"],
                    updated_by="system",
                )
            )

    db.flush()


def _sync_hypersonic_suites(db: Session, *, updated_by: str) -> dict[str, int]:
    suites = _load_hypersonic_ci_suites(raise_on_missing=True)
    if not suites:
        raise AppError("CONFIG_ERROR", "ci_list.json 中没有可同步的套件", status_code=500)

    existing_rows = (
        db.query(AutomationSuite)
        .filter(AutomationSuite.framework_key == "hypersonic")
        .all()
    )
    existing = {row.suite_key: row for row in existing_rows}

    created = 0
    updated = 0
    seen: set[str] = set()

    for item in suites:
        seen.add(item["suite_key"])
        row = existing.get(item["suite_key"])
        if row is None:
            row = AutomationSuite(
                framework_key="hypersonic",
                suite_key=item["suite_key"],
                name=item["name"],
                description=item["description"],
                content=item["content"],
                module_name=item["module_name"],
                path_expr=item["path_expr"],
                testpaths_json=item["testpaths"],
                python_files_json=item["python_files"],
                source_type=item["source_type"],
                updated_by=updated_by,
            )
            db.add(row)
            created += 1
        else:
            row.name = item["name"]
            row.description = item["description"]
            row.content = item["content"]
            row.module_name = item["module_name"]
            row.path_expr = item["path_expr"]
            row.testpaths_json = item["testpaths"]
            row.python_files_json = item["python_files"]
            row.source_type = item["source_type"]
            row.updated_by = updated_by
            updated += 1

    deleted = 0
    for row in existing_rows:
        if row.suite_key not in seen:
            db.delete(row)
            deleted += 1

    db.flush()
    return {"total": len(suites), "created": created, "updated": updated, "deleted": deleted}


def _parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_hypersonic_configuration(content: str) -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "level": "p0",
        "log": "FAILED",
        "repeat": 1,
        "data": False,
        "timeout_sec": max(60, int(_SETTINGS.hypersonic_default_timeout_sec)),
        "extra_pytest_args": "-s -vv --show-capture=no",
        "conf_json": {
            "system": {"http.security": False},
            "whitelist": {"whitelist.api.enable": False},
        },
    }

    text = (content or "").strip()
    if not text:
        return cfg

    parsed: dict[str, Any] = {}
    if text.startswith("{"):
        try:
            payload = json.loads(text)
            if isinstance(payload, dict):
                parsed = payload
        except Exception:
            parsed = {}

    if not parsed:
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            parsed[key.strip()] = value.strip()

    level = str(parsed.get("level", cfg["level"]))
    level = level.strip().lower()
    if level not in {"all", "p0", "p1", "p2"}:
        level = "p0"
    cfg["level"] = level

    log_mode = str(parsed.get("log", cfg["log"]))
    log_mode = log_mode.strip().upper()
    if log_mode not in {"FAILED", "ALL"}:
        log_mode = "FAILED"
    cfg["log"] = log_mode

    try:
        repeat = int(parsed.get("repeat", cfg["repeat"]))
    except (TypeError, ValueError):
        repeat = 1
    cfg["repeat"] = max(1, min(20, repeat))

    try:
        timeout_sec = int(parsed.get("timeout_sec", cfg["timeout_sec"]))
    except (TypeError, ValueError):
        timeout_sec = cfg["timeout_sec"]
    cfg["timeout_sec"] = max(60, min(24 * 60 * 60, timeout_sec))

    cfg["data"] = _parse_bool(parsed.get("data"), default=cfg["data"])

    extra_args = parsed.get("extra_pytest_args", cfg["extra_pytest_args"])
    cfg["extra_pytest_args"] = str(extra_args).strip() if extra_args is not None else ""

    conf_json = parsed.get("conf_json", cfg["conf_json"])
    if isinstance(conf_json, str):
        text_conf = conf_json.strip()
        if text_conf:
            try:
                conf_json = json.loads(text_conf)
            except Exception:
                conf_json = cfg["conf_json"]
        else:
            conf_json = {}
    if not isinstance(conf_json, dict):
        conf_json = cfg["conf_json"]
    cfg["conf_json"] = conf_json

    return cfg


def _build_hypersonic_selection(suite: AutomationSuite) -> list[str]:
    if suite.testpaths_json:
        result = [str(item) for item in suite.testpaths_json if str(item).strip()]
        if result:
            return result

    return _build_testpaths(suite.module_name or "", suite.path_expr or ".")


def _build_hypersonic_inner_command(config: dict[str, Any], testpaths: list[str]) -> str:
    args: list[str] = [_SETTINGS.hypersonic_remote_python_bin, "-m", "pytest"]

    extra_pytest_args = str(config.get("extra_pytest_args") or "").strip()
    if extra_pytest_args:
        try:
            args.extend(shell_split(extra_pytest_args))
        except ValueError:
            args.extend(["-s", "-vv", "--show-capture=no"])
    else:
        args.extend(["-s", "-vv", "--show-capture=no"])

    args.extend(["--alluredir=/workspace/qms-run/allure", "--clean-alluredir"])
    args.extend(["--log", str(config.get("log", "FAILED"))])

    if _parse_bool(config.get("data"), default=False):
        args.extend(["--data", "True"])

    conf_json = config.get("conf_json") or {}
    if conf_json:
        args.extend(["--conf", json.dumps(conf_json, ensure_ascii=False, separators=(",", ":"))])

    level = str(config.get("level", "p0"))
    if level in {"p0", "p1", "p2"}:
        args.extend(["-m", level])

    args.extend(testpaths)
    pytest_cmd = " ".join(shell_quote(item) for item in args)

    repeat = max(1, int(config.get("repeat", 1)))
    if repeat > 1:
        run_block = "\n".join(
            [
                f"for idx in $(seq 1 {repeat}); do",
                '  echo "[system] 开始第${idx}轮执行"',
                f"  {pytest_cmd}",
                "done",
            ]
        )
    else:
        run_block = pytest_cmd

    return "\n".join(
        [
            "set -e",
            "export PYTHONIOENCODING=utf-8",
            "cd /workspace/hypersonic",
            "mkdir -p /workspace/qms-run/allure",
            run_block,
        ]
    )


def _format_hypersonic_container_name(run_id: str) -> str:
    normalized = run_id.lower().replace("_", "-")
    return f"hs-{normalized}"


def _set_run_terminal(db: Session, run: AutomationRun, status: AutomationRunStatus, final_log: str | None = None) -> None:
    if final_log:
        _append_hypersonic_log(db, run, final_log)
    run.status = status
    run.finished_at = utcnow()


def _is_cancel_requested(db: Session, run: AutomationRun) -> bool:
    return (
        db.query(AutomationRun.cancel_requested)
        .filter(AutomationRun.id == run.id)
        .scalar()
        or False
    )


def _collect_report_archive(client: paramiko.SSHClient, db: Session, run: AutomationRun) -> None:
    if not run.remote_run_dir:
        return

    remote_dir = run.remote_run_dir.rstrip("/")
    remote_allure_dir = f"{remote_dir}/allure"
    archive_name = f"allure-{run.run_id}.tar.gz"
    remote_archive = f"{remote_dir}/{archive_name}"

    archive_inner = (
        f"if [ -d {shell_quote(remote_allure_dir)} ] && [ \"$(ls -A {shell_quote(remote_allure_dir)})\" ]; "
        f"then tar -czf {shell_quote(remote_archive)} -C {shell_quote(remote_dir)} allure; fi"
    )
    _run_ssh_wait(client, f"bash -lc {shell_quote(archive_inner)}")

    sftp = client.open_sftp()
    try:
        sftp.stat(remote_archive)
    except Exception:
        sftp.close()
        return

    local_rel = Path("automation") / "hypersonic" / run.run_id / archive_name
    local_abs = _SETTINGS.upload_path / local_rel
    local_abs.parent.mkdir(parents=True, exist_ok=True)

    sftp.get(remote_archive, str(local_abs))
    sftp.close()

    public_prefix = _SETTINGS.upload_public_prefix.rstrip("/")
    run.report_archive_path = f"{public_prefix}/{local_rel.as_posix()}"
    _append_hypersonic_log(db, run, f"[system] 报告已归档: {run.report_archive_path}")


def _dispatch_hypersonic_pending_runs() -> None:
    _HYPERSONIC_DISPATCH_EVENT.set()


def _start_hypersonic_monitor_thread(run_id: str, *, recover_existing: bool) -> None:
    with _LOCK:
        if run_id in _HYPERSONIC_MONITORING_RUN_IDS:
            return
        _HYPERSONIC_MONITORING_RUN_IDS.add(run_id)

    Thread(target=_execute_hypersonic_run, args=(run_id, recover_existing), daemon=True).start()


def _recover_hypersonic_runs(db: Session) -> None:
    rows = (
        db.query(AutomationRun)
        .filter(
            AutomationRun.framework_key == "hypersonic",
            AutomationRun.status.in_([AutomationRunStatus.pending, AutomationRunStatus.running]),
        )
        .order_by(AutomationRun.id.asc())
        .all()
    )
    if not rows:
        return

    if not _is_hypersonic_live_enabled():
        for run in rows:
            if run.status == AutomationRunStatus.running:
                _set_run_terminal(db, run, AutomationRunStatus.failed, "[system] 服务重启，任务被中断")
        db.flush()
        return

    client = None
    try:
        client = _connect_hypersonic_ssh()
        for run in rows:
            if run.status == AutomationRunStatus.pending:
                continue
            if not run.container_name:
                _set_run_terminal(db, run, AutomationRunStatus.failed, "[system] 缺少容器信息，任务被标记失败")
                continue

            cmd = f"docker inspect -f '{{{{.State.Running}}}}' {shell_quote(run.container_name)}"
            code, out, _ = _run_ssh_wait(client, cmd)
            running = code == 0 and out.strip().lower() == "true"
            if running:
                _append_hypersonic_log(db, run, "[system] 服务重启后恢复任务监控")
                _start_hypersonic_monitor_thread(run.run_id, recover_existing=True)
            else:
                _set_run_terminal(db, run, AutomationRunStatus.failed, "[system] 未发现运行中的容器，任务被标记失败")

        db.flush()
    except Exception as exc:
        for run in rows:
            if run.status == AutomationRunStatus.running:
                _set_run_terminal(db, run, AutomationRunStatus.failed, f"[system] 恢复任务失败: {exc}")
        db.flush()
    finally:
        if client is not None:
            client.close()


def _ensure_hypersonic_runtime(db: Session) -> None:
    global _HYPERSONIC_DISPATCHER_STARTED, _HYPERSONIC_RECOVERED

    with _LOCK:
        if not _HYPERSONIC_DISPATCHER_STARTED:
            Thread(target=_hypersonic_dispatcher_loop, daemon=True).start()
            _HYPERSONIC_DISPATCHER_STARTED = True

        _ensure_hypersonic_seed_data(db)
        if not _HYPERSONIC_RECOVERED:
            _recover_hypersonic_runs(db)
            _HYPERSONIC_RECOVERED = True

    _dispatch_hypersonic_pending_runs()


def _hypersonic_dispatcher_loop() -> None:
    while True:
        _HYPERSONIC_DISPATCH_EVENT.wait(timeout=2.0)
        _HYPERSONIC_DISPATCH_EVENT.clear()

        try:
            _dispatch_hypersonic_once()
        except Exception:
            sleep(0.5)


def _dispatch_hypersonic_once() -> None:
    db = SessionLocal()
    try:
        max_parallel = max(1, int(_SETTINGS.hypersonic_max_parallel))

        while True:
            running_count = (
                db.query(func.count(AutomationRun.id))
                .filter(
                    AutomationRun.framework_key == "hypersonic",
                    AutomationRun.status == AutomationRunStatus.running,
                )
                .scalar()
                or 0
            )
            if int(running_count) >= max_parallel:
                break

            pending = (
                db.query(AutomationRun)
                .filter(
                    AutomationRun.framework_key == "hypersonic",
                    AutomationRun.status == AutomationRunStatus.pending,
                )
                .order_by(AutomationRun.started_at.asc(), AutomationRun.id.asc())
                .first()
            )
            if pending is None:
                break

            pending.status = AutomationRunStatus.running
            pending.started_at = utcnow()
            db.flush()
            run_id = pending.run_id
            db.commit()

            _start_hypersonic_monitor_thread(run_id, recover_existing=False)
    finally:
        db.close()


def _execute_hypersonic_run(run_id: str, recover_existing: bool) -> None:
    db = SessionLocal()
    client = None
    try:
        run = db.query(AutomationRun).filter(AutomationRun.run_id == run_id).first()
        if run is None:
            return
        if run.status != AutomationRunStatus.running:
            return

        cfg = (
            db.query(AutomationConfiguration)
            .filter(
                AutomationConfiguration.framework_key == "hypersonic",
                AutomationConfiguration.config_key == run.configuration_key,
            )
            .first()
        )
        suite = (
            db.query(AutomationSuite)
            .filter(
                AutomationSuite.framework_key == "hypersonic",
                AutomationSuite.suite_key == run.test_suite_key,
            )
            .first()
        )
        if cfg is None or suite is None:
            _set_run_terminal(db, run, AutomationRunStatus.failed, "[system] 配置或测试套不存在")
            db.commit()
            return

        parsed_cfg = _parse_hypersonic_configuration(cfg.content)
        timeout_sec = int(parsed_cfg.get("timeout_sec", _SETTINGS.hypersonic_default_timeout_sec))

        if not _is_hypersonic_live_enabled():
            _append_hypersonic_log(db, run, "[system] HYPERSONIC_LIVE_ENABLED=false，进入本地占位执行")
            _append_hypersonic_log(db, run, f"[functional_test] 配置={cfg.config_key} 套件={suite.suite_key}")
            if _is_cancel_requested(db, run):
                _set_run_terminal(db, run, AutomationRunStatus.canceled, "[system] 任务已取消")
            else:
                _set_run_terminal(db, run, AutomationRunStatus.success, "[system] 占位任务执行完成")
            db.commit()
            return

        testpaths = _build_hypersonic_selection(suite)
        inner_cmd = _build_hypersonic_inner_command(parsed_cfg, testpaths)

        client = _connect_hypersonic_ssh()
        if not recover_existing:
            run.container_name = _format_hypersonic_container_name(run.run_id)
            run.remote_run_dir = f"{_SETTINGS.hypersonic_remote_base_dir.rstrip('/')}/{run.run_id}"
            _append_hypersonic_log(db, run, f"[system] 容器名: {run.container_name}")
            _append_hypersonic_log(db, run, f"[system] 远端运行目录: {run.remote_run_dir}")
            db.commit()

            prep_cmd = f"mkdir -p {shell_quote(run.remote_run_dir)}"
            code, _, err = _run_ssh_wait(client, prep_cmd)
            if code != 0:
                raise AppError("UPSTREAM_ERROR", f"创建远端目录失败: {err}", status_code=502)

            clean_cmd = f"docker rm -f {shell_quote(run.container_name)} >/dev/null 2>&1 || true"
            _run_ssh_wait(client, clean_cmd)

            run_cmd = " ".join(
                [
                    "docker run -d",
                    f"--name {shell_quote(run.container_name)}",
                    f"-v {shell_quote(_SETTINGS.hypersonic_remote_repo_dir)}:/workspace/hypersonic",
                    f"-v {shell_quote(run.remote_run_dir)}:/workspace/qms-run",
                    "-w /workspace/hypersonic",
                    shell_quote(_SETTINGS.hypersonic_runner_image),
                    "bash -lc",
                    shell_quote(inner_cmd),
                ]
            )
            _append_hypersonic_log(db, run, f"[system] 远端启动命令: {run_cmd}")
            db.commit()

            code, out, err = _run_ssh_wait(client, run_cmd)
            if code != 0:
                raise AppError("UPSTREAM_ERROR", f"docker run 启动失败: {err or out}", status_code=502)
            if out.strip():
                _append_hypersonic_log(db, run, f"[system] 容器启动成功: {out.strip()[:80]}")
                db.commit()
        else:
            _append_hypersonic_log(db, run, "[system] 重新接管已有容器日志")
            db.commit()

        logs_cmd = f"docker logs -f {shell_quote(run.container_name)}"
        _, stdout, stderr = client.exec_command(logs_cmd, get_pty=True)
        channel = stdout.channel
        buffer = ""
        start_at = monotonic()
        timeout_triggered = False
        stop_sent = False
        last_cancel_check = start_at

        while True:
            had_data = False
            if channel.recv_ready():
                had_data = True
                buffer += channel.recv(4096).decode("utf-8", errors="replace")
            if channel.recv_stderr_ready():
                had_data = True
                buffer += channel.recv_stderr(4096).decode("utf-8", errors="replace")

            buffer = buffer.replace("\r", "\n")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if line:
                    _append_hypersonic_log(db, run, line)
                    db.commit()

            now = monotonic()
            if not timeout_triggered and now - start_at > timeout_sec:
                timeout_triggered = True
                _append_hypersonic_log(db, run, f"[system] 任务超时（>{timeout_sec}s），准备停止容器")
                db.commit()
                _run_ssh_wait(client, f"docker stop {shell_quote(run.container_name)}")
                stop_sent = True

            if now - last_cancel_check >= 1.0:
                if _is_cancel_requested(db, run) and not stop_sent:
                    _append_hypersonic_log(db, run, "[system] 收到取消请求，准备停止容器")
                    db.commit()
                    _run_ssh_wait(client, f"docker stop {shell_quote(run.container_name)}")
                    stop_sent = True
                last_cancel_check = now

            if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                break

            if not had_data:
                sleep(0.2)

        tail = buffer.strip()
        if tail:
            _append_hypersonic_log(db, run, tail)
            db.commit()

        wait_code, wait_out, _ = _run_ssh_wait(client, f"docker wait {shell_quote(run.container_name)}")
        exit_code = -1
        if wait_code == 0 and wait_out:
            try:
                exit_code = int(wait_out.splitlines()[-1].strip())
            except Exception:
                exit_code = -1

        _run_ssh_wait(client, f"docker rm -f {shell_quote(run.container_name)} >/dev/null 2>&1 || true")

        if _is_cancel_requested(db, run):
            _set_run_terminal(db, run, AutomationRunStatus.canceled, "[system] 任务已取消")
        elif timeout_triggered:
            _set_run_terminal(db, run, AutomationRunStatus.failed, "[system] 任务执行超时")
        elif exit_code == 0:
            _set_run_terminal(db, run, AutomationRunStatus.success, "[system] 任务执行完成")
        else:
            _set_run_terminal(db, run, AutomationRunStatus.failed, f"[system] 任务执行失败，退出码: {exit_code}")

        _collect_report_archive(client, db, run)
        db.commit()
    except AppError as exc:
        run = db.query(AutomationRun).filter(AutomationRun.run_id == run_id).first()
        if run is not None and run.status == AutomationRunStatus.running:
            _set_run_terminal(db, run, AutomationRunStatus.failed, f"[system] {exc.message}")
            db.commit()
    except Exception as exc:
        run = db.query(AutomationRun).filter(AutomationRun.run_id == run_id).first()
        if run is not None and run.status == AutomationRunStatus.running:
            _set_run_terminal(db, run, AutomationRunStatus.failed, f"[system] 执行异常: {exc}")
            db.commit()
    finally:
        if client is not None:
            client.close()
        db.close()
        with _LOCK:
            _HYPERSONIC_MONITORING_RUN_IDS.discard(run_id)
        _dispatch_hypersonic_pending_runs()


def _serialize_log_chunk_for_hypersonic_run(
    db: Session,
    run: AutomationRun,
    cursor: int,
    limit: int,
) -> dict:
    rows = (
        db.query(AutomationRunLog.seq, AutomationRunLog.line)
        .filter(
            AutomationRunLog.run_id == run.id,
            AutomationRunLog.seq > cursor,
        )
        .order_by(AutomationRunLog.seq.asc())
        .limit(limit + 1)
        .all()
    )

    lines = rows[:limit]
    next_cursor = cursor
    if lines:
        next_cursor = int(lines[-1].seq)

    return {
        "run_id": run.run_id,
        "status": run.status.value,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "report_archive_path": run.report_archive_path,
        "lines": [row.line for row in lines],
        "next_cursor": next_cursor,
        "has_more": len(rows) > limit,
    }


def _request_stop_remote_container(container_name: str) -> tuple[bool, str]:
    client = None
    try:
        client = _connect_hypersonic_ssh()
        code, out, err = _run_ssh_wait(client, f"docker stop {shell_quote(container_name)}")
        if code == 0:
            return True, out or ""
        return False, err or out or ""
    except Exception as exc:
        return False, str(exc)
    finally:
        if client is not None:
            client.close()


@router.get("/frameworks/{framework_key}")
def get_framework(
    framework_key: str,
    request: Request,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(get_current_user),
):
    if framework_key == "hypersonic":
        with _LOCK:
            _ensure_hypersonic_runtime(db)
            framework = _get_framework(framework_key, db)
        return success_response(request, deepcopy(framework))

    with _LOCK:
        framework = _get_framework(framework_key)
        return success_response(request, deepcopy(framework))


@router.get("/frameworks/{framework_key}/runs")
def list_framework_runs(
    framework_key: str,
    request: Request,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(get_current_user),
):
    if framework_key == "hypersonic":
        with _LOCK:
            _ensure_hypersonic_runtime(db)
            _get_framework(framework_key, db)
            runs = (
                db.query(AutomationRun)
                .filter(AutomationRun.framework_key == framework_key)
                .order_by(AutomationRun.started_at.desc(), AutomationRun.id.desc())
                .all()
            )
            payload = [_serialize_hypersonic_run(db, row, include_logs=True) for row in runs]
        return success_response(request, payload)

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

    if framework_key == "hypersonic":
        with _LOCK:
            _ensure_hypersonic_runtime(db)
            row = (
                db.query(AutomationConfiguration)
                .filter(
                    AutomationConfiguration.framework_key == framework_key,
                    AutomationConfiguration.config_key == config_key,
                )
                .first()
            )
            if row is None:
                raise AppError("NOT_FOUND", f"配置不存在: {config_key}", status_code=404)

            row.content = payload.content
            row.updated_by = payload.updated_by
            db.flush()

            framework = _build_hypersonic_framework(db)

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

    with _LOCK:
        if framework_key == "frigateDynamic" and _is_frigate_live_enabled():
            _write_remote_toml("configuration", config_key, payload.content, payload.updated_by)
            framework = _build_frigate_framework_live()
        else:
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

    if framework_key == "hypersonic":
        with _LOCK:
            _ensure_hypersonic_runtime(db)
            row = (
                db.query(AutomationSuite)
                .filter(
                    AutomationSuite.framework_key == framework_key,
                    AutomationSuite.suite_key == suite_key,
                )
                .first()
            )
            if row is None:
                raise AppError("NOT_FOUND", f"测试套不存在: {suite_key}", status_code=404)

            row.content = payload.content
            row.updated_by = payload.updated_by
            row.source_type = "manual" if row.source_type != "ci_list" else row.source_type
            db.flush()
            framework = _build_hypersonic_framework(db)

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

    with _LOCK:
        if framework_key == "frigateDynamic" and _is_frigate_live_enabled():
            _write_remote_toml("testsuite", suite_key, payload.content, payload.updated_by)
            framework = _build_frigate_framework_live()
        else:
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


@router.post("/frameworks/hypersonic/suites:sync")
def sync_hypersonic_suites(
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    _require_editor(current_user)

    with _LOCK:
        _ensure_hypersonic_runtime(db)
        summary = _sync_hypersonic_suites(db, updated_by=current_user.username)
        framework = _build_hypersonic_framework(db)

    write_audit(
        db,
        current_user.id,
        action="automation.hypersonic.suites.sync",
        object_type="automation_framework",
        object_id="hypersonic",
        diff=summary,
    )
    db.commit()

    return success_response(request, {"framework": deepcopy(framework), "summary": summary})


@router.post("/frameworks/{framework_key}/runs")
def trigger_automation_run(
    framework_key: str,
    payload: TriggerAutomationRunRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    _require_editor(current_user)

    if framework_key == "hypersonic":
        with _LOCK:
            _ensure_hypersonic_runtime(db)
            framework = _get_framework(framework_key, db)

            config = (
                db.query(AutomationConfiguration)
                .filter(
                    AutomationConfiguration.framework_key == framework_key,
                    AutomationConfiguration.config_key == payload.configuration_key,
                )
                .first()
            )
            if config is None:
                raise AppError("NOT_FOUND", f"配置不存在: {payload.configuration_key}", status_code=404)

            suite = (
                db.query(AutomationSuite)
                .filter(
                    AutomationSuite.framework_key == framework_key,
                    AutomationSuite.suite_key == payload.test_suite_key,
                )
                .first()
            )
            if suite is None:
                raise AppError("NOT_FOUND", f"测试套不存在: {payload.test_suite_key}", status_code=404)

            supported_modes = {item["mode"] for item in framework["operation_modes"]}
            if payload.operation_mode not in supported_modes:
                raise AppError("VALIDATION_ERROR", f"不支持的执行模式: {payload.operation_mode}", status_code=422)

            run_id = _generate_hypersonic_run_id(db)
            run = AutomationRun(
                run_id=run_id,
                framework_key=framework_key,
                entry_name=framework["entry_name"],
                configuration_key=payload.configuration_key,
                test_suite_key=payload.test_suite_key,
                operation_mode=payload.operation_mode,
                status=AutomationRunStatus.pending,
                note=payload.note,
                triggered_by=payload.triggered_by,
                started_at=utcnow(),
                finished_at=None,
                cancel_requested=False,
                meta_json={
                    "source": "web",
                    "suite_source_type": suite.source_type,
                    "live_enabled": _is_hypersonic_live_enabled(),
                },
            )
            db.add(run)
            db.flush()
            _append_hypersonic_log(db, run, "[system] 已创建任务，等待调度")
            db.flush()
            run_payload = _serialize_hypersonic_run(db, run, include_logs=True)

        write_audit(
            db,
            current_user.id,
            action="automation.run.trigger",
            object_type="automation_run",
            object_id=run.run_id,
            diff={
                "framework_key": framework_key,
                "configuration_key": payload.configuration_key,
                "test_suite_key": payload.test_suite_key,
                "operation_mode": payload.operation_mode,
            },
        )
        db.commit()
        _dispatch_hypersonic_pending_runs()
        return success_response(request, run_payload)

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

        if framework_key == "frigateDynamic" and _is_frigate_live_enabled():
            command = _build_remote_execute_command(payload.operation_mode, payload.configuration_key, payload.test_suite_key)
            run = {
                "run_id": run_id,
                "framework_key": framework_key,
                "entry_name": framework["entry_name"],
                "configuration_key": payload.configuration_key,
                "test_suite_key": payload.test_suite_key,
                "operation_mode": payload.operation_mode,
                "status": "running",
                "note": payload.note,
                "triggered_by": payload.triggered_by,
                "started_at": now,
                "finished_at": None,
                "logs": [
                    "[system] 已创建任务，正在连接远端 frigateDynamic 容器执行",
                ],
            }
            _RUNS.setdefault(framework_key, []).insert(0, run)
            Thread(target=_execute_frigate_run, args=(framework_key, run_id, command), daemon=True).start()
        else:
            status = (
                "running"
                if framework["framework_type"] == "performance" and payload.operation_mode == "deploy_and_test"
                else "success"
            )
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
                "logs": [
                    "[system] 占位任务已触发",
                ],
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


@router.get("/runs/{run_id}/logs")
def get_automation_run_logs(
    run_id: str,
    request: Request,
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: UserAccount = Depends(get_current_user),
):
    with _LOCK:
        run = db.query(AutomationRun).filter(AutomationRun.run_id == run_id).first()
        if run is not None:
            if run.framework_key == "hypersonic":
                _ensure_hypersonic_runtime(db)
            payload = _serialize_log_chunk_for_hypersonic_run(db, run, cursor, limit)
            return success_response(request, payload)

        for framework_runs in _RUNS.values():
            target = next((item for item in framework_runs if item["run_id"] == run_id), None)
            if not target:
                continue
            lines = target.get("logs", [])
            start = min(cursor, len(lines))
            end = min(start + limit, len(lines))
            return success_response(
                request,
                {
                    "run_id": run_id,
                    "status": target.get("status"),
                    "finished_at": target.get("finished_at"),
                    "report_archive_path": None,
                    "lines": lines[start:end],
                    "next_cursor": end,
                    "has_more": end < len(lines),
                },
            )

    raise AppError("NOT_FOUND", f"自动化任务不存在: {run_id}", status_code=404)


@router.post("/runs/{run_id}:cancel")
def cancel_automation_run(
    run_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    _require_editor(current_user)

    with _LOCK:
        run = db.query(AutomationRun).filter(AutomationRun.run_id == run_id).first()
        if run is None:
            raise AppError("NOT_FOUND", f"自动化任务不存在: {run_id}", status_code=404)

        if run.framework_key != "hypersonic":
            raise AppError("VALIDATION_ERROR", "仅支持取消 hypersonic 任务", status_code=422)

        _ensure_hypersonic_runtime(db)

        if run.status in _TERMINAL_STATUSES:
            payload = _serialize_hypersonic_run(db, run, include_logs=True)
        elif run.status == AutomationRunStatus.pending:
            run.cancel_requested = True
            _set_run_terminal(db, run, AutomationRunStatus.canceled, "[system] 任务已取消")
            payload = _serialize_hypersonic_run(db, run, include_logs=True)
        else:
            run.cancel_requested = True
            _append_hypersonic_log(db, run, "[system] 已收到取消请求，正在停止容器")
            if _is_hypersonic_live_enabled() and run.container_name:
                ok, detail = _request_stop_remote_container(run.container_name)
                if ok:
                    _append_hypersonic_log(db, run, "[system] 已发送 docker stop")
                else:
                    _append_hypersonic_log(db, run, f"[system] 停止容器失败: {detail}")
            elif not _is_hypersonic_live_enabled():
                _set_run_terminal(db, run, AutomationRunStatus.canceled, "[system] 任务已取消")
            payload = _serialize_hypersonic_run(db, run, include_logs=True)

    write_audit(
        db,
        current_user.id,
        action="automation.run.cancel",
        object_type="automation_run",
        object_id=run_id,
        diff={"framework_key": "hypersonic"},
    )
    db.commit()
    _dispatch_hypersonic_pending_runs()
    return success_response(request, payload)
