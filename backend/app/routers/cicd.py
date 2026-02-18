from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import re
from shlex import quote as shell_quote
from threading import RLock, Thread
from time import sleep
from typing import Literal, Optional

import paramiko
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import UserAccount, UserRole, get_db
from ..errors import AppError
from ..response import success_response
from ..services import write_audit
from ..settings import get_settings

router = APIRouter(prefix="/api/v1/cicd", tags=["cicd"])

StageStatus = Literal["pending", "running", "success", "failed"]


class TriggerRunRequest(BaseModel):
    repo_url: Optional[str] = None
    branch: str = Field(min_length=1)
    commit_id: Optional[str] = None
    note: Optional[str] = None
    triggered_by: str = Field(min_length=1)


class UpdateStageRequest(BaseModel):
    status: StageStatus
    note: Optional[str] = None


_LOCK = RLock()
_SETTINGS = get_settings()
_MAX_RUN_LOG_LINES = 2000
_HEX_40_RE = re.compile(r"\b[0-9a-fA-F]{40}\b")
_HEX_7_TO_40_RE = re.compile(r"\b[0-9a-fA-F]{7,40}\b")
_MD5_RE = re.compile(r"\b[0-9a-fA-F]{32}\b")


def _resolve_cicd_target_ssh_host() -> str:
    return (_SETTINGS.cicd_target_ssh_host or _SETTINGS.frigate_dynamic_ssh_host).strip()


def _resolve_cicd_target_ssh_port() -> int:
    return _SETTINGS.cicd_target_ssh_port or _SETTINGS.frigate_dynamic_ssh_port


def _resolve_cicd_target_ssh_user() -> str:
    return (_SETTINGS.cicd_target_ssh_user or _SETTINGS.frigate_dynamic_ssh_user).strip()


def _resolve_cicd_target_ssh_password() -> str:
    return (_SETTINGS.cicd_target_ssh_password or _SETTINGS.frigate_dynamic_ssh_password).strip()


def _resolve_cicd_target_ssh_timeout_sec() -> float:
    return _SETTINGS.cicd_target_ssh_timeout_sec or _SETTINGS.frigate_dynamic_ssh_timeout_sec


def _resolve_cicd_target_deploy_dir() -> str:
    return (_SETTINGS.cicd_target_deploy_dir or "").strip() or (
        "/home/hyperchain/dev_workspace/frigate-dynamic/bin_assets/new-hyperchain"
    )


def _build_project_root(branch: str) -> str:
    branch_path = _validate_branch_name(branch)
    return f"{_SETTINGS.cicd_build_root_dir}/{branch_path}/{_SETTINGS.cicd_clone_repo_dir_name}"


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
            "ip": _SETTINGS.cicd_build_ssh_host,
            "note": "支持 SSH 触发代码拉取（分支目录 + git clone -b）",
        },
        "deploy_target": {
            "name": "制品分发机",
            "ip": _resolve_cicd_target_ssh_host(),
            "note": "真实执行：构建机 scp 下发 + 目标机 SSH 校验 MD5",
        },
        "build_script_path": "/opt/hyperchain/scripts/build_hyperchain.sh",
        "artifact_path": "/opt/hyperchain/output/hyperchain",
        "deploy_path": f"{_resolve_cicd_target_deploy_dir()}/hyperchain",
        "stages_template": [
            {
                "stage_key": "prepare",
                "name": "拉取代码",
                "description": "在构建机创建分支目录并执行 git clone -b。",
                "command": (
                    "mkdir -p /data/jinpeng/go-project-build/{branch} && "
                    "cd /data/jinpeng/go-project-build/{branch} && "
                    "rm -rf go-hyperchain && "
                    "git clone -b {branch} {repo_url} go-hyperchain"
                ),
            },
            {
                "stage_key": "build",
                "name": "编译 Hyperchain 二进制",
                "description": "切换 Go1.24，修正 build.sh 的 PROJECT_PATH 后执行编译脚本。",
                "command": (
                    "cd /data/jinpeng/go-project-build/{branch}/go-hyperchain/scripts && "
                    "export GOROOT=$HOME/sdk/go1.24.0 && "
                    "export PATH=$GOROOT/bin:$(~/sdk/go1.24.0/bin/go env GOPATH)/bin:$PATH && "
                    "go version && sh build.sh"
                ),
            },
            {
                "stage_key": "package",
                "name": "归档制品",
                "description": "读取分支 HEAD、codeVersion 与构建机 MD5，并校验版本一致性。",
                "command": (
                    "cd /data/jinpeng/go-project-build/{branch}/go-hyperchain && "
                    "git rev-parse HEAD && git rev-parse --short=8 HEAD && ./hyperchain --codeVersion && md5sum ./hyperchain"
                ),
            },
            {
                "stage_key": "scp",
                "name": "SCP 分发二进制",
                "description": "从构建机 scp 到目标机并进行双端 MD5 一致性校验。",
                "command": (
                    "scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
                    "/data/jinpeng/go-project-build/{branch}/go-hyperchain/hyperchain "
                    f"{_resolve_cicd_target_ssh_user()}@{_resolve_cicd_target_ssh_host()}:"
                    f"{_resolve_cicd_target_deploy_dir().rstrip('/')}/hyperchain"
                ),
            },
        ],
        "updated_at": now,
    }


def _render_prepare_stage_command(repo_url: str, branch: str) -> str:
    root_dir = shell_quote(_SETTINGS.cicd_build_root_dir)
    branch_dir = shell_quote(branch)
    repo_dir_name = shell_quote(_SETTINGS.cicd_clone_repo_dir_name)
    branch_arg = shell_quote(branch)
    repo_arg = shell_quote(repo_url)
    return " && ".join(
        [
            f"cd {root_dir}",
            f"mkdir -p {branch_dir}",
            f"cd {branch_dir}",
            f"rm -rf {repo_dir_name}",
            f"git clone -b {branch_arg} {repo_arg} {repo_dir_name}",
        ]
    )


def _render_build_stage_command(branch: str) -> str:
    project_root = _build_project_root(branch)
    scripts_dir = f"{project_root}/scripts"
    scripts_dir_arg = shell_quote(scripts_dir)
    project_root_arg = shell_quote(project_root)
    return " && ".join(
        [
            f"cd {scripts_dir_arg}",
            "export GOROOT=$HOME/sdk/go1.24.0",
            "export PATH=$GOROOT/bin:$(~/sdk/go1.24.0/bin/go env GOPATH)/bin:$PATH",
            "go version",
            (
                "if grep -q '^PROJECT_PATH=.*GOPATH.*go-hyperchain' build.sh; then "
                "sed -i '/^PROJECT_PATH=.*GOPATH.*go-hyperchain/s|^|# |' build.sh; "
                "fi"
            ),
            "sed -i '/^PROJECT_PATH=/d' build.sh",
            "sed -i '/^PROJECT_NAME=\"hyperchain\"/a PROJECT_PATH=$(cd \"$(dirname \"$0\")/..\" && pwd)' build.sh",
            "sh build.sh",
            f"test -f {project_root_arg}/hyperchain",
        ]
    )


def _render_package_stage_command(branch: str) -> str:
    project_root = _build_project_root(branch)
    project_root_arg = shell_quote(project_root)
    return " && ".join(
        [
            f"cd {project_root_arg}",
            "git rev-parse HEAD",
            "git rev-parse --short=8 HEAD",
            "./hyperchain --codeVersion",
            "md5sum ./hyperchain",
        ]
    )


def _render_scp_stage_command(branch: str) -> str:
    project_root = _build_project_root(branch)
    target_user = _resolve_cicd_target_ssh_user()
    target_host = _resolve_cicd_target_ssh_host()
    target_path = f"{_resolve_cicd_target_deploy_dir().rstrip('/')}/hyperchain"
    project_root_arg = shell_quote(project_root)
    target_arg = shell_quote(f"{target_user}@{target_host}:{target_path}")
    return " && ".join(
        [
            f"cd {project_root_arg}",
            "scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ./hyperchain " + target_arg,
        ]
    )


def _make_run(
    run_id: str,
    pipeline: dict,
    repo_url: Optional[str],
    branch: str,
    commit_id: Optional[str],
    note: Optional[str],
    triggered_by: str,
) -> dict:
    now = _now_iso()
    stages = []
    for index, stage in enumerate(pipeline["stages_template"]):
        command = stage["command"]
        if stage["stage_key"] == "prepare" and repo_url:
            command = _render_prepare_stage_command(repo_url, branch)
        if stage["stage_key"] == "build":
            command = _render_build_stage_command(branch)
        if stage["stage_key"] == "package":
            command = _render_package_stage_command(branch)
        if stage["stage_key"] == "scp":
            command = _render_scp_stage_command(branch)

        stages.append(
            {
                "stage_key": stage["stage_key"],
                "name": stage["name"],
                "description": stage["description"],
                "command": command,
                "status": "running" if index == 0 else "pending",
                "updated_at": now if index == 0 else None,
                "note": "已进入拉取流程" if index == 0 else None,
            }
        )

    return {
        "run_id": run_id,
        "pipeline_key": pipeline["pipeline_key"],
        "pipeline_name": pipeline["pipeline_name"],
        "repo_url": repo_url,
        "branch": branch,
        "commit_id": commit_id,
        "note": note,
        "status": "running",
        "triggered_by": triggered_by,
        "started_at": now,
        "finished_at": None,
        "stages": stages,
        "logs": [
            f"[trigger] {triggered_by} 触发流水线, repo={repo_url or '-'}, branch={branch}",
        ],
    }


_PIPELINES: dict[str, dict] = {"hyperchain-binary": _create_pipeline()}
_RUNS: dict[str, list[dict]] = {
    "hyperchain-binary": [
        {
            "run_id": "RUN-0001",
            "pipeline_key": "hyperchain-binary",
            "pipeline_name": "Hyperchain 二进制 CICD",
            "repo_url": None,
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
                    "name": "拉取代码",
                    "description": "在构建机创建分支目录并执行 git clone -b。",
                    "command": "mkdir -p /data/jinpeng/go-project-build/release/v1.0.0 && cd /data/jinpeng/go-project-build/release/v1.0.0 && rm -rf go-hyperchain && git clone -b release/v1.0.0 <repo_url> go-hyperchain",
                    "status": "success",
                    "updated_at": _now_iso(),
                    "note": "占位：拉取完成",
                },
                {
                    "stage_key": "build",
                    "name": "编译 Hyperchain 二进制",
                    "description": "切换 Go1.24，修正 build.sh 的 PROJECT_PATH 后执行编译脚本。",
                    "command": "cd /data/jinpeng/go-project-build/release/v1.0.0/go-hyperchain/scripts && export GOROOT=$HOME/sdk/go1.24.0 && export PATH=$GOROOT/bin:$(~/sdk/go1.24.0/bin/go env GOPATH)/bin:$PATH && go version && sh build.sh",
                    "status": "running",
                    "updated_at": _now_iso(),
                    "note": "占位：正在构建",
                },
                {
                    "stage_key": "package",
                    "name": "归档制品",
                    "description": "读取分支 HEAD、codeVersion 与构建机 MD5，并校验版本一致性。",
                    "command": "cd /data/jinpeng/go-project-build/release/v1.0.0/go-hyperchain && git rev-parse HEAD && git rev-parse --short=8 HEAD && ./hyperchain --codeVersion && md5sum ./hyperchain",
                    "status": "pending",
                    "updated_at": None,
                    "note": None,
                },
                {
                    "stage_key": "scp",
                    "name": "SCP 分发二进制",
                    "description": "从构建机 scp 到目标机并进行双端 MD5 一致性校验。",
                    "command": "scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null /data/jinpeng/go-project-build/release/v1.0.0/go-hyperchain/hyperchain user@10.10.131.192:/home/hyperchain/dev_workspace/frigate-dynamic/bin_assets/new-hyperchain/hyperchain",
                    "status": "pending",
                    "updated_at": None,
                    "note": None,
                },
            ],
            "logs": [
                "[prepare] 占位: 代码拉取完成",
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


def _append_run_log(run_id: str, message: str) -> None:
    with _LOCK:
        _, run = _find_run(run_id)
        run["logs"].append(message)
        if len(run["logs"]) > _MAX_RUN_LOG_LINES:
            run["logs"] = run["logs"][-_MAX_RUN_LOG_LINES:]


def _is_cicd_live_enabled() -> bool:
    return _SETTINGS.cicd_live_enabled


def _validate_branch_name(branch: str) -> str:
    branch_value = branch.strip()
    if not branch_value:
        raise AppError("VALIDATION_ERROR", "branch 不能为空", status_code=422)
    if branch_value.startswith("/"):
        raise AppError("VALIDATION_ERROR", f"非法 branch: {branch}", status_code=422)
    parts = branch_value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise AppError("VALIDATION_ERROR", f"非法 branch: {branch}", status_code=422)
    return branch_value


def _validate_repo_url(repo_url: Optional[str]) -> str:
    value = (repo_url or "").strip()
    if not value:
        raise AppError("VALIDATION_ERROR", "请输入仓库地址", status_code=422)
    return value


def _connect_cicd_ssh() -> paramiko.SSHClient:
    if not _SETTINGS.cicd_build_ssh_password:
        raise AppError("CONFIG_ERROR", "未配置 CICD_BUILD_SSH_PASSWORD", status_code=500)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=_SETTINGS.cicd_build_ssh_host,
            port=_SETTINGS.cicd_build_ssh_port,
            username=_SETTINGS.cicd_build_ssh_user,
            password=_SETTINGS.cicd_build_ssh_password,
            timeout=_SETTINGS.cicd_build_ssh_timeout_sec,
            auth_timeout=_SETTINGS.cicd_build_ssh_timeout_sec,
            banner_timeout=_SETTINGS.cicd_build_ssh_timeout_sec,
            look_for_keys=False,
            allow_agent=False,
        )
    except AppError:
        raise
    except Exception as exc:
        raise AppError("UPSTREAM_ERROR", f"连接 CICD 构建机失败: {exc}", status_code=502) from exc
    return client


def _connect_cicd_target_ssh() -> paramiko.SSHClient:
    target_host = _resolve_cicd_target_ssh_host()
    target_user = _resolve_cicd_target_ssh_user()
    target_password = _resolve_cicd_target_ssh_password()
    if not target_host:
        raise AppError("CONFIG_ERROR", "未配置 CICD 目标机地址", status_code=500)
    if not target_user:
        raise AppError("CONFIG_ERROR", "未配置 CICD 目标机用户名", status_code=500)
    if not target_password:
        raise AppError("CONFIG_ERROR", "未配置 CICD 目标机密码", status_code=500)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=target_host,
            port=_resolve_cicd_target_ssh_port(),
            username=target_user,
            password=target_password,
            timeout=_resolve_cicd_target_ssh_timeout_sec(),
            auth_timeout=_resolve_cicd_target_ssh_timeout_sec(),
            banner_timeout=_resolve_cicd_target_ssh_timeout_sec(),
            look_for_keys=False,
            allow_agent=False,
        )
    except Exception as exc:
        raise AppError("UPSTREAM_ERROR", f"连接 CICD 目标机失败: {exc}", status_code=502) from exc
    return client


def _run_stage_command(
    client: paramiko.SSHClient,
    run_id: str,
    stage_key: str,
    command: str,
    auto_password: Optional[str] = None,
) -> tuple[int, list[str]]:
    _, stdout, stderr = client.exec_command(command, get_pty=True)
    channel = stdout.channel
    buffer = ""
    lines: list[str] = []
    password_sent = False

    while True:
        had_data = False
        if channel.recv_ready():
            had_data = True
            buffer += channel.recv(4096).decode("utf-8", errors="replace")
        if channel.recv_stderr_ready():
            had_data = True
            buffer += channel.recv_stderr(4096).decode("utf-8", errors="replace")

        if auto_password and not password_sent:
            lowered = buffer.lower()
            if "password:" in lowered or "password for" in lowered:
                channel.send(auto_password + "\n")
                password_sent = True
                _append_run_log(run_id, f"[{stage_key}] 检测到密码提示，已自动输入")

        buffer = buffer.replace("\r", "\n")
        while "\n" in buffer:
            raw_line, buffer = buffer.split("\n", 1)
            line = raw_line.strip()
            if line:
                lines.append(line)
                _append_run_log(run_id, line)

        if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
            break

        if not had_data:
            sleep(0.2)

    tail = buffer.strip()
    if tail:
        lines.append(tail)
        _append_run_log(run_id, tail)

    return channel.recv_exit_status(), lines


def _extract_first_match(pattern: re.Pattern[str], lines: list[str]) -> Optional[str]:
    for line in lines:
        match = pattern.search(line)
        if match:
            return match.group(0).lower()
    return None


def _extract_last_sha_fragment(lines: list[str]) -> Optional[str]:
    candidate: Optional[str] = None
    for line in lines:
        matches = _HEX_7_TO_40_RE.findall(line)
        if matches:
            candidate = matches[-1].lower()
    return candidate


def _build_prepare_clone_command(repo_url: str, branch: str) -> str:
    repo = _validate_repo_url(repo_url)
    branch_name = _validate_branch_name(branch)

    root_dir = shell_quote(_SETTINGS.cicd_build_root_dir)
    branch_dir = shell_quote(branch_name)
    repo_dir_name = shell_quote(_SETTINGS.cicd_clone_repo_dir_name)
    branch_arg = shell_quote(branch_name)
    repo_arg = shell_quote(repo)

    return " && ".join(
        [
            f"cd {root_dir}",
            f"mkdir -p {branch_dir}",
            f"cd {branch_dir}",
            f"rm -rf {repo_dir_name}",
            f"git clone -b {branch_arg} {repo_arg} {repo_dir_name}",
        ]
    )


def _mark_stage_success(run_id: str, stage_key: str, note: str) -> None:
    with _LOCK:
        _, run = _find_run(run_id)
        now = _now_iso()
        stage_index = next((idx for idx, item in enumerate(run["stages"]) if item["stage_key"] == stage_key), -1)
        if stage_index < 0:
            return

        stage = run["stages"][stage_index]
        stage["status"] = "success"
        stage["updated_at"] = now
        stage["note"] = note

        next_stage = run["stages"][stage_index + 1] if stage_index + 1 < len(run["stages"]) else None
        if next_stage and next_stage["status"] == "pending":
            next_stage["status"] = "running"
            next_stage["updated_at"] = now
            next_stage["note"] = "等待后续自动化回调"

        all_success = all(item["status"] == "success" for item in run["stages"])
        run["status"] = "success" if all_success else "running"
        run["finished_at"] = now if all_success else None


def _mark_stage_failed(run_id: str, stage_key: str, reason: str) -> None:
    with _LOCK:
        _, run = _find_run(run_id)
        now = _now_iso()
        stage_index = next((idx for idx, item in enumerate(run["stages"]) if item["stage_key"] == stage_key), -1)
        if stage_index >= 0:
            stage = run["stages"][stage_index]
            stage["status"] = "failed"
            stage["updated_at"] = now
            stage["note"] = reason
        run["status"] = "failed"
        run["finished_at"] = now


def _mark_prepare_stage_success(run_id: str) -> None:
    _mark_stage_success(run_id, "prepare", "代码拉取完成")


def _mark_prepare_stage_failed(run_id: str, reason: str) -> None:
    _mark_stage_failed(run_id, "prepare", reason)


def _mark_build_stage_success(run_id: str) -> None:
    _mark_stage_success(run_id, "build", "二进制编译完成")


def _mark_build_stage_failed(run_id: str, reason: str) -> None:
    _mark_stage_failed(run_id, "build", reason)


def _mark_package_stage_success(run_id: str, note: str) -> None:
    _mark_stage_success(run_id, "package", note)


def _mark_package_stage_failed(run_id: str, reason: str) -> None:
    _mark_stage_failed(run_id, "package", reason)


def _mark_scp_stage_success(run_id: str, note: str) -> None:
    _mark_stage_success(run_id, "scp", note)


def _mark_scp_stage_failed(run_id: str, reason: str) -> None:
    _mark_stage_failed(run_id, "scp", reason)


def _execute_build_binary(run_id: str, branch: str) -> None:
    client = None
    try:
        command = _render_build_stage_command(branch)
        _append_run_log(run_id, f"[build] 远端执行: {command}")

        client = _connect_cicd_ssh()
        exit_code, _ = _run_stage_command(client, run_id, "build", command)
        if exit_code == 0:
            _append_run_log(run_id, "[build] 二进制编译完成")
            _mark_build_stage_success(run_id)
            _execute_package_verify(run_id, branch)
        else:
            message = f"二进制编译失败，退出码: {exit_code}"
            _append_run_log(run_id, f"[build] {message}")
            _mark_build_stage_failed(run_id, message)
    except Exception as exc:
        reason = f"二进制编译异常: {exc}"
        _append_run_log(run_id, f"[build] {reason}")
        _mark_build_stage_failed(run_id, reason)
    finally:
        if client is not None:
            client.close()


def _execute_package_verify(run_id: str, branch: str) -> None:
    client = None
    try:
        project_root = _build_project_root(branch)
        project_root_arg = shell_quote(project_root)
        _append_run_log(run_id, f"[package] 远端执行: {_render_package_stage_command(branch)}")

        client = _connect_cicd_ssh()

        exit_code, full_sha_lines = _run_stage_command(client, run_id, "package", f"cd {project_root_arg} && git rev-parse HEAD")
        if exit_code != 0:
            raise AppError("UPSTREAM_ERROR", f"读取 full SHA 失败，退出码: {exit_code}", status_code=502)
        full_sha = _extract_first_match(_HEX_40_RE, full_sha_lines)
        if not full_sha:
            raise AppError("UPSTREAM_ERROR", "未解析到 full SHA", status_code=502)

        exit_code, short_sha_lines = _run_stage_command(
            client, run_id, "package", f"cd {project_root_arg} && git rev-parse --short=8 HEAD"
        )
        if exit_code != 0:
            raise AppError("UPSTREAM_ERROR", f"读取 short SHA 失败，退出码: {exit_code}", status_code=502)
        short_sha = _extract_first_match(_HEX_7_TO_40_RE, short_sha_lines)
        if not short_sha:
            raise AppError("UPSTREAM_ERROR", "未解析到 short SHA", status_code=502)

        exit_code, code_version_lines = _run_stage_command(
            client, run_id, "package", f"cd {project_root_arg} && ./hyperchain --codeVersion"
        )
        if exit_code != 0:
            raise AppError("UPSTREAM_ERROR", f"读取 codeVersion 失败，退出码: {exit_code}", status_code=502)
        code_version = next((line for line in reversed(code_version_lines) if line.strip()), "")
        if not code_version:
            raise AppError("UPSTREAM_ERROR", "codeVersion 输出为空", status_code=502)
        code_sha = _extract_last_sha_fragment([code_version])
        if not code_sha:
            raise AppError("UPSTREAM_ERROR", f"无法从 codeVersion 提取 SHA: {code_version}", status_code=502)

        exit_code, source_md5_lines = _run_stage_command(client, run_id, "package", f"cd {project_root_arg} && md5sum ./hyperchain")
        if exit_code != 0:
            raise AppError("UPSTREAM_ERROR", f"读取构建机 MD5 失败，退出码: {exit_code}", status_code=502)
        source_md5 = _extract_first_match(_MD5_RE, source_md5_lines)
        if not source_md5:
            raise AppError("UPSTREAM_ERROR", "未解析到构建机 MD5", status_code=502)

        _append_run_log(run_id, f"[package] full_sha={full_sha}")
        _append_run_log(run_id, f"[package] short_sha={short_sha}")
        _append_run_log(run_id, f"[package] codeVersion={code_version}")
        _append_run_log(run_id, f"[package] code_version_sha={code_sha}")
        _append_run_log(run_id, f"[package] source_md5={source_md5}")

        if not full_sha.startswith(short_sha):
            raise AppError("UPSTREAM_ERROR", f"short SHA 与 full SHA 不一致: {short_sha} vs {full_sha}", status_code=502)
        if not full_sha.startswith(code_sha):
            raise AppError(
                "UPSTREAM_ERROR",
                f"codeVersion 中的 SHA 与当前分支 HEAD 不一致: {code_sha} vs {full_sha}",
                status_code=502,
            )

        _append_run_log(run_id, "[package] 版本与 MD5 校验通过")
        _mark_package_stage_success(run_id, f"版本校验通过，short_sha={short_sha}")
        _execute_scp_distribute(run_id, branch, source_md5)
    except Exception as exc:
        reason = str(exc) if isinstance(exc, AppError) else f"归档校验异常: {exc}"
        _append_run_log(run_id, f"[package] {reason}")
        _mark_package_stage_failed(run_id, reason)
    finally:
        if client is not None:
            client.close()


def _execute_scp_distribute(run_id: str, branch: str, source_md5: str) -> None:
    build_client = None
    target_client = None
    try:
        project_root = _build_project_root(branch)
        project_root_arg = shell_quote(project_root)
        target_host = _resolve_cicd_target_ssh_host()
        target_user = _resolve_cicd_target_ssh_user()
        target_password = _resolve_cicd_target_ssh_password()
        target_deploy_dir = _resolve_cicd_target_deploy_dir().rstrip("/")
        target_binary_path = f"{target_deploy_dir}/hyperchain"
        target_binary_path_arg = shell_quote(target_binary_path)

        if not target_password:
            raise AppError("CONFIG_ERROR", "未配置 CICD 目标机密码", status_code=500)

        target_client = _connect_cicd_target_ssh()
        mkdir_cmd = f"mkdir -p {shell_quote(target_deploy_dir)}"
        _append_run_log(run_id, f"[scp] 目标机执行: {mkdir_cmd}")
        mkdir_exit, _ = _run_stage_command(target_client, run_id, "scp", mkdir_cmd)
        if mkdir_exit != 0:
            raise AppError("UPSTREAM_ERROR", f"目标目录创建失败，退出码: {mkdir_exit}", status_code=502)

        scp_cmd = (
            f"cd {project_root_arg} && "
            "scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ./hyperchain "
            f"{shell_quote(f'{target_user}@{target_host}:{target_binary_path}')}"
        )
        _append_run_log(run_id, f"[scp] 构建机执行: {scp_cmd}")
        build_client = _connect_cicd_ssh()
        scp_exit, _ = _run_stage_command(build_client, run_id, "scp", scp_cmd, auto_password=target_password)
        if scp_exit != 0:
            raise AppError("UPSTREAM_ERROR", f"SCP 分发失败，退出码: {scp_exit}", status_code=502)

        target_md5_cmd = f"md5sum {target_binary_path_arg}"
        target_md5_exit, target_md5_lines = _run_stage_command(target_client, run_id, "scp", target_md5_cmd)
        if target_md5_exit != 0:
            raise AppError("UPSTREAM_ERROR", f"读取目标机 MD5 失败，退出码: {target_md5_exit}", status_code=502)
        target_md5 = _extract_first_match(_MD5_RE, target_md5_lines)
        if not target_md5:
            raise AppError("UPSTREAM_ERROR", "未解析到目标机 MD5", status_code=502)

        _append_run_log(run_id, f"[scp] source_md5={source_md5}")
        _append_run_log(run_id, f"[scp] target_md5={target_md5}")
        if target_md5 != source_md5:
            _append_run_log(run_id, "[scp] MD5 不一致，开始删除目标文件")
            _run_stage_command(target_client, run_id, "scp", f"rm -f {target_binary_path_arg}")
            raise AppError("UPSTREAM_ERROR", f"MD5 校验失败: {source_md5} != {target_md5}", status_code=502)

        _append_run_log(run_id, "[scp] 分发与 MD5 校验通过")
        _mark_scp_stage_success(run_id, "SCP 分发成功，MD5 校验通过")
    except Exception as exc:
        reason = str(exc) if isinstance(exc, AppError) else f"SCP 分发异常: {exc}"
        _append_run_log(run_id, f"[scp] {reason}")
        _mark_scp_stage_failed(run_id, reason)
    finally:
        if build_client is not None:
            build_client.close()
        if target_client is not None:
            target_client.close()


def _execute_prepare_clone(run_id: str, repo_url: str, branch: str) -> None:
    client = None
    try:
        command = _build_prepare_clone_command(repo_url, branch)
        _append_run_log(run_id, f"[prepare] 远端执行: {command}")

        client = _connect_cicd_ssh()
        exit_code, _ = _run_stage_command(client, run_id, "prepare", command)
        if exit_code == 0:
            _append_run_log(run_id, "[prepare] 代码拉取完成")
            _mark_prepare_stage_success(run_id)
            _execute_build_binary(run_id, branch)
        else:
            message = f"代码拉取失败，退出码: {exit_code}"
            _append_run_log(run_id, f"[prepare] {message}")
            _mark_prepare_stage_failed(run_id, message)
    except Exception as exc:
        reason = f"代码拉取异常: {exc}"
        _append_run_log(run_id, f"[prepare] {reason}")
        _mark_prepare_stage_failed(run_id, reason)
    finally:
        if client is not None:
            client.close()


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


@router.get("/runs/{run_id}/logs")
def get_run_logs(
    run_id: str,
    request: Request,
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
    _: UserAccount = Depends(get_current_user),
):
    with _LOCK:
        _, run = _find_run(run_id)
        total = len(run["logs"])
        start = min(cursor, total)
        end = min(start + limit, total)
        return success_response(
            request,
            {
                "run_id": run["run_id"],
                "status": run["status"],
                "finished_at": run["finished_at"],
                "stages": deepcopy(run["stages"]),
                "lines": run["logs"][start:end],
                "next_cursor": end,
                "has_more": end < total,
            },
        )


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

        repo_url = payload.repo_url
        if _is_cicd_live_enabled():
            repo_url = _validate_repo_url(repo_url)
            _validate_branch_name(payload.branch)

        run = _make_run(run_id, pipeline, repo_url, payload.branch, payload.commit_id, payload.note, payload.triggered_by)
        _RUNS.setdefault(pipeline_key, []).insert(0, run)

    if _is_cicd_live_enabled():
        Thread(target=_execute_prepare_clone, args=(run_id, repo_url or "", payload.branch), daemon=True).start()

    write_audit(
        db,
        current_user.id,
        action="cicd.run.trigger",
        object_type="cicd_run",
        object_id=run_id,
        diff={"pipeline": pipeline_key, "branch": payload.branch, "repo_url": repo_url},
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
        run["logs"].append(f"[{stage_key}] {payload.status}{' - ' + payload.note if payload.note else ''}")

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
