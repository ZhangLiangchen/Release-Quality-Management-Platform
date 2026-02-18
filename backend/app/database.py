from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Generator, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from .settings import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class UserRole(str, enum.Enum):
    admin = "admin"
    qa = "qa"
    dev = "dev"
    viewer = "viewer"


class UserStatus(str, enum.Enum):
    active = "active"
    disabled = "disabled"


class CaseStatus(str, enum.Enum):
    not_run = "not_run"
    passed = "passed"
    failed = "failed"
    blocked = "blocked"
    skipped = "skipped"


class TestCaseStatus(str, enum.Enum):
    active = "active"
    deprecated = "deprecated"


class CaseTreeNodeType(str, enum.Enum):
    directory = "directory"
    file = "file"


class SuiteVersionStatus(str, enum.Enum):
    draft = "draft"
    published = "published"


class PlanStatus(str, enum.Enum):
    draft = "draft"
    in_progress = "in_progress"
    done = "done"
    archived = "archived"


class RunStatus(str, enum.Enum):
    running = "running"
    success = "success"
    failed = "failed"


class AutomationRunStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"
    canceled = "canceled"


class IssueStatus(str, enum.Enum):
    new = "new"
    assigned = "assigned"
    fixing = "fixing"
    to_verify = "to_verify"
    verify_failed = "verify_failed"
    closed = "closed"
    rejected = "rejected"
    duplicate = "duplicate"
    invalid = "invalid"
    deferred = "deferred"


class IssuePriority(str, enum.Enum):
    high = "high"
    medium = "medium"
    low = "low"


class IssueSeverity(str, enum.Enum):
    critical = "critical"
    major = "major"
    minor = "minor"


class CaseLinkType(str, enum.Enum):
    repro = "repro"
    regression = "regression"


class ProjectConfig(Base):
    __tablename__ = "project_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_name: Mapped[str] = mapped_column(String(128), nullable=False)
    current_version_id: Mapped[Optional[int]] = mapped_column(ForeignKey("version.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class UserAccount(Base):
    __tablename__ = "user_account"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, native_enum=False), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, native_enum=False), default=UserStatus.active, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class Version(Base):
    __tablename__ = "version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class TestCase(Base):
    __tablename__ = "test_case"
    __test__ = False

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    case_key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    tree_node_id: Mapped[Optional[int]] = mapped_column(ForeignKey("case_tree_node.id"), nullable=True)
    module: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    steps: Mapped[str] = mapped_column(Text, nullable=False)
    expected: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[IssuePriority] = mapped_column(
        Enum(IssuePriority, native_enum=False), default=IssuePriority.medium, nullable=False
    )
    tags_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[TestCaseStatus] = mapped_column(
        Enum(TestCaseStatus, native_enum=False), default=TestCaseStatus.active, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class CaseSetSnapshot(Base):
    __tablename__ = "case_set_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    version_id: Mapped[int] = mapped_column(ForeignKey("version.id"), nullable=False)
    case_set_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("user_account.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    version: Mapped[Version] = relationship()


class CaseTreeNode(Base):
    __tablename__ = "case_tree_node"
    __table_args__ = (
        UniqueConstraint("parent_id", "name", name="uq_case_tree_node_parent_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    node_type: Mapped[CaseTreeNodeType] = mapped_column(
        Enum(CaseTreeNodeType, native_enum=False), nullable=False
    )
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("case_tree_node.id"), nullable=True)
    full_path: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    parent: Mapped[Optional["CaseTreeNode"]] = relationship(remote_side="CaseTreeNode.id", back_populates="children")
    children: Mapped[list["CaseTreeNode"]] = relationship(back_populates="parent")


class VersionCaseStatus(Base):
    __tablename__ = "version_case_status"
    __table_args__ = (
        UniqueConstraint("version_id", "snapshot_id", "case_id", name="uq_version_snapshot_case"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("version.id"), nullable=False)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("case_set_snapshot.id"), nullable=False)
    case_id: Mapped[int] = mapped_column(ForeignKey("test_case.id"), nullable=False)
    status: Mapped[CaseStatus] = mapped_column(
        Enum(CaseStatus, native_enum=False), default=CaseStatus.not_run, nullable=False
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("user_account.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class CaseStatusHistory(Base):
    __tablename__ = "case_status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("version.id"), nullable=False)
    case_id: Mapped[int] = mapped_column(ForeignKey("test_case.id"), nullable=False)
    status: Mapped[CaseStatus] = mapped_column(Enum(CaseStatus, native_enum=False), nullable=False)
    executor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user_account.id"), nullable=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attachments_json: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)


class CaseSuite(Base):
    __tablename__ = "case_suite"
    __table_args__ = (
        UniqueConstraint("version_id", "name", name="uq_case_suite_version_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    suite_key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    version_id: Mapped[int] = mapped_column(ForeignKey("version.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("user_account.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    version: Mapped[Version] = relationship()


class CaseSuiteVersion(Base):
    __tablename__ = "case_suite_version"
    __table_args__ = (
        UniqueConstraint("suite_id", "ver_no", name="uq_case_suite_version_ver_no"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    suite_version_key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    suite_id: Mapped[int] = mapped_column(ForeignKey("case_suite.id"), nullable=False)
    ver_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[SuiteVersionStatus] = mapped_column(
        Enum(SuiteVersionStatus, native_enum=False), default=SuiteVersionStatus.draft, nullable=False
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("user_account.id"), nullable=True)
    published_by: Mapped[Optional[int]] = mapped_column(ForeignKey("user_account.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    suite: Mapped[CaseSuite] = relationship()


class SuiteCaseRef(Base):
    __tablename__ = "suite_case_ref"
    __table_args__ = (
        UniqueConstraint("suite_version_id", "case_id", name="uq_suite_case_ref_version_case"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    suite_version_id: Mapped[int] = mapped_column(ForeignKey("case_suite_version.id"), nullable=False)
    case_id: Mapped[int] = mapped_column(ForeignKey("test_case.id"), nullable=False)
    order_no: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    module_path_snapshot: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class TestPlan(Base):
    __tablename__ = "test_plan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    version_id: Mapped[int] = mapped_column(ForeignKey("version.id"), nullable=False)
    suite_version_id: Mapped[int] = mapped_column(ForeignKey("case_suite_version.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[PlanStatus] = mapped_column(
        Enum(PlanStatus, native_enum=False), default=PlanStatus.in_progress, nullable=False
    )
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("user_account.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    version: Mapped[Version] = relationship()
    suite_version: Mapped[CaseSuiteVersion] = relationship()


class TestRun(Base):
    __tablename__ = "test_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    plan_id: Mapped[int] = mapped_column(ForeignKey("test_plan.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    build_no: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    environment: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, native_enum=False), default=RunStatus.running, nullable=False
    )
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("user_account.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    plan: Mapped[TestPlan] = relationship()


class RunCase(Base):
    __tablename__ = "run_case"
    __table_args__ = (
        UniqueConstraint("run_id", "case_id", name="uq_run_case_run_case"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_case_key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    run_id: Mapped[int] = mapped_column(ForeignKey("test_run.id"), nullable=False)
    case_id: Mapped[int] = mapped_column(ForeignKey("test_case.id"), nullable=False)
    case_key_snapshot: Mapped[str] = mapped_column(String(32), nullable=False)
    title_snapshot: Mapped[str] = mapped_column(String(256), nullable=False)
    module_snapshot: Mapped[str] = mapped_column(String(128), nullable=False)
    steps_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    expected_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    assignee_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user_account.id"), nullable=True)
    current_status: Mapped[CaseStatus] = mapped_column(
        Enum(CaseStatus, native_enum=False), default=CaseStatus.not_run, nullable=False
    )
    last_updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("user_account.id"), nullable=True)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    run: Mapped[TestRun] = relationship()
    case: Mapped[TestCase] = relationship()


class RunCaseHistory(Base):
    __tablename__ = "run_case_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_case_id: Mapped[int] = mapped_column(ForeignKey("run_case.id"), nullable=False)
    status: Mapped[CaseStatus] = mapped_column(Enum(CaseStatus, native_enum=False), nullable=False)
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    operator_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user_account.id"), nullable=True)
    operated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    attachments_json: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)

    run_case: Mapped[RunCase] = relationship()


class AutomationConfiguration(Base):
    __tablename__ = "automation_configuration"
    __table_args__ = (
        UniqueConstraint("framework_key", "config_key", name="uq_automation_configuration_framework_config"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    framework_key: Mapped[str] = mapped_column(String(64), nullable=False)
    config_key: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class AutomationSuite(Base):
    __tablename__ = "automation_suite"
    __table_args__ = (
        UniqueConstraint("framework_key", "suite_key", name="uq_automation_suite_framework_suite"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    framework_key: Mapped[str] = mapped_column(String(64), nullable=False)
    suite_key: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    module_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    path_expr: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    testpaths_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    python_files_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class AutomationRun(Base):
    __tablename__ = "automation_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    framework_key: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_name: Mapped[str] = mapped_column(String(128), nullable=False)
    configuration_key: Mapped[str] = mapped_column(String(128), nullable=False)
    test_suite_key: Mapped[str] = mapped_column(String(128), nullable=False)
    operation_mode: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[AutomationRunStatus] = mapped_column(
        Enum(AutomationRunStatus, native_enum=False), default=AutomationRunStatus.pending, nullable=False
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    triggered_by: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    container_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    remote_run_dir: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    report_archive_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    log_cursor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    logs: Mapped[list["AutomationRunLog"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class AutomationRunLog(Base):
    __tablename__ = "automation_run_log"
    __table_args__ = (
        UniqueConstraint("run_id", "seq", name="uq_automation_run_log_run_seq"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("automation_run.id"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    line: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    run: Mapped[AutomationRun] = relationship(back_populates="logs")


class Issue(Base):
    __tablename__ = "issue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issue_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    issue_key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[IssueStatus] = mapped_column(
        Enum(IssueStatus, native_enum=False), default=IssueStatus.new, nullable=False
    )
    priority: Mapped[IssuePriority] = mapped_column(
        Enum(IssuePriority, native_enum=False), default=IssuePriority.medium, nullable=False
    )
    severity: Mapped[IssueSeverity] = mapped_column(
        Enum(IssueSeverity, native_enum=False), default=IssueSeverity.major, nullable=False
    )
    assignee_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user_account.id"), nullable=True)
    reporter_id: Mapped[int] = mapped_column(ForeignKey("user_account.id"), nullable=False)
    found_version_id: Mapped[int] = mapped_column(ForeignKey("version.id"), nullable=False)
    fix_version_id: Mapped[Optional[int]] = mapped_column(ForeignKey("version.id"), nullable=True)
    verify_version_id: Mapped[Optional[int]] = mapped_column(ForeignKey("version.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    links: Mapped[list["IssueCaseLink"]] = relationship(back_populates="issue", cascade="all, delete-orphan")


class IssueCaseLink(Base):
    __tablename__ = "issue_case_link"
    __table_args__ = (
        UniqueConstraint("issue_id", "case_id", "link_type", name="uq_issue_case_link"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issue.id"), nullable=False)
    case_id: Mapped[int] = mapped_column(ForeignKey("test_case.id"), nullable=False)
    link_type: Mapped[CaseLinkType] = mapped_column(Enum(CaseLinkType, native_enum=False), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    issue: Mapped[Issue] = relationship(back_populates="links")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user_account.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[str] = mapped_column(String(64), nullable=False)
    diff_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


Index("ix_issue_found_version_status", Issue.found_version_id, Issue.status)
Index(
    "ix_case_status_history_version_case_executed_at",
    CaseStatusHistory.version_id,
    CaseStatusHistory.case_id,
    CaseStatusHistory.executed_at,
)
Index("ix_case_tree_node_parent_id", CaseTreeNode.parent_id)
Index("ix_test_case_tree_node_id", TestCase.tree_node_id)
Index("ix_case_suite_version_id", CaseSuite.version_id)
Index("ix_case_suite_version_suite_id", CaseSuiteVersion.suite_id)
Index("ix_suite_case_ref_suite_version_id", SuiteCaseRef.suite_version_id)
Index("ix_test_plan_version_id", TestPlan.version_id)
Index("ix_test_plan_suite_version_id", TestPlan.suite_version_id)
Index("ix_test_run_plan_id", TestRun.plan_id)
Index("ix_test_run_started_at", TestRun.started_at)
Index("ix_run_case_run_id", RunCase.run_id)
Index("ix_run_case_case_id", RunCase.case_id)
Index("ix_run_case_history_run_case_id_operated_at", RunCaseHistory.run_case_id, RunCaseHistory.operated_at)
Index("ix_automation_configuration_framework_key", AutomationConfiguration.framework_key)
Index("ix_automation_suite_framework_key", AutomationSuite.framework_key)
Index("ix_automation_run_framework_key_started_at", AutomationRun.framework_key, AutomationRun.started_at)
Index("ix_automation_run_status_started_at", AutomationRun.status, AutomationRun.started_at)
Index("ix_automation_run_log_run_id_seq", AutomationRunLog.run_id, AutomationRunLog.seq)


settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
