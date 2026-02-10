from __future__ import annotations

from typing import Iterable, Optional

from fastapi import Depends

from .auth import get_current_user
from .database import UserAccount, UserRole
from .errors import AppError


def require_roles(roles: Iterable[UserRole]):
    allowed = set(roles)

    def dependency(current_user: UserAccount = Depends(get_current_user)) -> UserAccount:
        if current_user.role not in allowed:
            raise AppError("FORBIDDEN", "无权限执行该操作", status_code=403)
        return current_user

    return dependency


def ensure_issue_operator(current_user: UserAccount, assignee_id: Optional[int]) -> None:
    if current_user.role in {UserRole.admin, UserRole.qa}:
        return
    if current_user.role == UserRole.dev and assignee_id == current_user.id:
        return
    raise AppError("FORBIDDEN", "仅管理员/QA 或当前负责人可操作", status_code=403)
