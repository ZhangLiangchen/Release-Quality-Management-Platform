from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field

from .database import (
    CaseLinkType,
    CaseStatus,
    IssuePriority,
    IssueSeverity,
    IssueStatus,
    UserRole,
    UserStatus,
)


class Attachment(BaseModel):
    name: str
    url: str
    size: Optional[int] = None
    mime: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    user_id: str
    username: str
    email: str
    role: UserRole
    status: UserStatus


class AuthLoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ProjectConfigOut(BaseModel):
    project_name: str
    current_version_key: str


class ProjectConfigUpdate(BaseModel):
    project_name: str = Field(min_length=1, max_length=128)
    current_version_key: Optional[str] = None


class VersionOut(BaseModel):
    version_key: str
    name: str
    is_current: bool
    created_at: datetime


class VersionCreateRequest(BaseModel):
    version_key: str = Field(min_length=1, max_length=64)


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    email: EmailStr
    role: UserRole


class CaseListItem(BaseModel):
    case_key: str
    title: str
    module: str
    latest_status: CaseStatus
    latest_updated_at: Optional[datetime] = None
    latest_updated_by: Optional[str] = None


class CaseModuleGroup(BaseModel):
    module: str
    cases: list[CaseListItem]


class CaseDetailOut(BaseModel):
    case_key: str
    title: str
    module: str
    steps: str
    expected: str
    tags: list[str]
    latest_status: CaseStatus


class CaseHistoryOut(BaseModel):
    id: int
    executed_at: datetime
    executor: str
    status: CaseStatus
    note: Optional[str] = None
    attachments: list[Attachment]


class CaseStatusUpdateRequest(BaseModel):
    status: CaseStatus
    note: Optional[str] = None
    attachments: list[Attachment] = Field(default_factory=list)


class IssueCaseLinkPayload(BaseModel):
    case_key: str
    link_type: CaseLinkType
    note: Optional[str] = None


class IssueOut(BaseModel):
    issue_key: str
    title: str
    description: str
    status: IssueStatus
    priority: IssuePriority
    severity: IssueSeverity
    assignee: Optional[str]
    reporter: str
    found_version_key: str
    fix_version_key: Optional[str] = None
    verify_version_key: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    links: list[IssueCaseLinkPayload]


class IssueCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    description: str = ""
    priority: IssuePriority = IssuePriority.medium
    severity: IssueSeverity = IssueSeverity.major
    assignee: Optional[str] = None
    reporter: str
    found_version_key: str
    links: list[IssueCaseLinkPayload]


class IssueUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=256)
    description: Optional[str] = None
    priority: Optional[IssuePriority] = None
    assignee: Optional[str] = None


class IssueTransitionRequest(BaseModel):
    target_status: IssueStatus


class IssueCloseRequest(BaseModel):
    fix_version_key: str
    verify_version_key: str
    regression_case_keys: list[str]


class DashboardQualityOut(BaseModel):
    total_cases: int
    executed_cases: int
    passed_cases: int
    skipped_cases: int
    execution_rate: float
    pass_rate: Optional[float]
    total_issues: int
    resolved_issues: int
    resolution_rate: float
    pending_issue_count: int


class ImportValidateOut(BaseModel):
    total_rows: int
    valid_rows: int
    errors: list[str]


class UploadedFileOut(BaseModel):
    name: str
    url: str
    size: int
    mime: Optional[str]


class SuccessEnvelope(BaseModel):
    data: Any
    trace_id: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Optional[dict[str, Any]] = None


class ErrorEnvelope(BaseModel):
    error: ErrorBody
    trace_id: str
