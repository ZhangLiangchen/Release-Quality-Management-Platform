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
