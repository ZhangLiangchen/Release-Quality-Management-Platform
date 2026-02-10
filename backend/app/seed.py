from __future__ import annotations

from sqlalchemy.orm import Session

from .auth import hash_password
from .database import (
    CaseLinkType,
    CaseSetSnapshot,
    CaseStatus,
    CaseStatusHistory,
    Issue,
    IssueCaseLink,
    IssuePriority,
    IssueSeverity,
    IssueStatus,
    ProjectConfig,
    TestCase,
    UserAccount,
    UserRole,
    UserStatus,
    Version,
    VersionCaseStatus,
)
from .services import ensure_version_case_status_rows, get_or_create_default_snapshot, make_snapshot_payload


DEFAULT_PASSWORD = "password123"


def seed_database(db: Session) -> None:
    if db.query(UserAccount).first():
        return

    users = [
        UserAccount(
            user_id="U-001",
            username="admin",
            email="admin@example.com",
            role=UserRole.admin,
            status=UserStatus.active,
            password_hash=hash_password(DEFAULT_PASSWORD),
        ),
        UserAccount(
            user_id="U-002",
            username="qa",
            email="qa@example.com",
            role=UserRole.qa,
            status=UserStatus.active,
            password_hash=hash_password(DEFAULT_PASSWORD),
        ),
        UserAccount(
            user_id="U-003",
            username="dev",
            email="dev@example.com",
            role=UserRole.dev,
            status=UserStatus.active,
            password_hash=hash_password(DEFAULT_PASSWORD),
        ),
        UserAccount(
            user_id="U-004",
            username="viewer",
            email="viewer@example.com",
            role=UserRole.viewer,
            status=UserStatus.active,
            password_hash=hash_password(DEFAULT_PASSWORD),
        ),
    ]
    db.add_all(users)
    db.flush()

    versions = [
        Version(version_key="v1.0.0", name="v1.0.0", is_current=True),
        Version(version_key="v1.1.0", name="v1.1.0", is_current=False),
    ]
    db.add_all(versions)
    db.flush()

    config = ProjectConfig(project_name="测试管理系统", current_version_id=versions[0].id)
    db.add(config)

    cases = [
        TestCase(
            case_id="C-001",
            case_key="TC-001",
            module="用户登录",
            title="用户登录成功",
            steps="输入正确用户名和密码，点击登录",
            expected="进入首页",
            tags_json=["登录", "核心流程"],
        ),
        TestCase(
            case_id="C-002",
            case_key="TC-002",
            module="用户登录",
            title="用户登录失败提示",
            steps="输入错误密码后登录",
            expected="提示密码错误",
            tags_json=["登录", "异常流程"],
        ),
        TestCase(
            case_id="C-003",
            case_key="TC-003",
            module="用户管理",
            title="新增用户成功",
            steps="管理员新增用户",
            expected="列表新增用户",
            tags_json=["用户管理"],
        ),
        TestCase(
            case_id="C-004",
            case_key="TC-004",
            module="数据导出",
            title="问题单导出 XLSX",
            steps="导出当前问题单",
            expected="下载文件成功",
            tags_json=["导出"],
        ),
    ]
    db.add_all(cases)
    db.flush()

    snapshots: dict[str, CaseSetSnapshot] = {}
    for version in versions:
        snapshot = get_or_create_default_snapshot(db, version, users[0].id)
        snapshot.snapshot_json = make_snapshot_payload(
            version.version_key,
            [case.case_key for case in cases],
            "seed default snapshot",
        )
        snapshots[version.version_key] = snapshot
        ensure_version_case_status_rows(db, version, snapshot, users[1].id)

    db.flush()

    def set_case_status(version_key: str, case_key: str, status: CaseStatus, note: str) -> None:
        version = next(item for item in versions if item.version_key == version_key)
        snapshot = snapshots[version_key]
        test_case = next(item for item in cases if item.case_key == case_key)
        row = (
            db.query(VersionCaseStatus)
            .filter(
                VersionCaseStatus.version_id == version.id,
                VersionCaseStatus.snapshot_id == snapshot.id,
                VersionCaseStatus.case_id == test_case.id,
            )
            .first()
        )
        if row is None:
            return

        row.status = status
        row.note = note
        row.updated_by = users[1].id

        db.add(
            CaseStatusHistory(
                version_id=version.id,
                case_id=test_case.id,
                status=status,
                executor_id=users[1].id,
                note=note,
                attachments_json=[],
            )
        )

    set_case_status("v1.0.0", "TC-001", CaseStatus.passed, "登录流程通过")
    set_case_status("v1.0.0", "TC-002", CaseStatus.failed, "验证码校验异常")
    set_case_status("v1.0.0", "TC-003", CaseStatus.passed, "用户新增通过")

    issue = Issue(
        issue_id="I-001",
        issue_key="ISS-001",
        title="验证码校验失败",
        description="输入正确验证码仍提示失败",
        status=IssueStatus.to_verify,
        priority=IssuePriority.high,
        severity=IssueSeverity.major,
        assignee_id=users[2].id,
        reporter_id=users[1].id,
        found_version_id=versions[0].id,
        fix_version_id=versions[0].id,
        verify_version_id=versions[1].id,
    )
    db.add(issue)
    db.flush()

    repro_case = next(item for item in cases if item.case_key == "TC-002")
    db.add(
        IssueCaseLink(
            issue_id=issue.id,
            case_id=repro_case.id,
            link_type=CaseLinkType.repro,
        )
    )
    db.add(
        IssueCaseLink(
            issue_id=issue.id,
            case_id=repro_case.id,
            link_type=CaseLinkType.regression,
        )
    )

    db.commit()
