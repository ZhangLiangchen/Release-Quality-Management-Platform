from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import get_current_user, hash_password
from ..database import UserAccount, UserRole, UserStatus, get_db
from ..errors import AppError
from ..response import success_response
from ..schemas import UserCreateRequest, UserOut
from ..services import write_audit

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("")
def list_users(request: Request, db: Session = Depends(get_db), _: UserAccount = Depends(get_current_user)):
    users = db.query(UserAccount).order_by(UserAccount.id.asc()).all()
    data = [
        UserOut(
            user_id=user.user_id,
            username=user.username,
            email=user.email,
            role=user.role,
            status=user.status,
        ).model_dump()
        for user in users
    ]
    return success_response(request, data)


@router.post("")
def create_user(
    payload: UserCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    if current_user.role != UserRole.admin:
        raise AppError("FORBIDDEN", "仅管理员可新增用户", status_code=403)

    if db.query(UserAccount).filter(UserAccount.username == payload.username).first():
        raise AppError("VALIDATION_ERROR", "用户名已存在", status_code=422)
    if db.query(UserAccount).filter(UserAccount.email == payload.email).first():
        raise AppError("VALIDATION_ERROR", "邮箱已存在", status_code=422)

    count = db.query(func.count(UserAccount.id)).scalar() or 0
    user = UserAccount(
        user_id=f"U-{count + 1:03d}",
        username=payload.username,
        email=payload.email,
        role=payload.role,
        status=UserStatus.active,
        password_hash=hash_password("password123"),
    )
    db.add(user)

    write_audit(
        db,
        current_user.id,
        action="user.create",
        object_type="user",
        object_id=user.user_id,
        diff={"username": user.username, "role": user.role.value},
    )
    db.commit()
    db.refresh(user)

    data = UserOut(
        user_id=user.user_id,
        username=user.username,
        email=user.email,
        role=user.role,
        status=user.status,
    )
    return success_response(request, data.model_dump())


@router.delete("/{user_id}")
def disable_user(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    if current_user.role != UserRole.admin:
        raise AppError("FORBIDDEN", "仅管理员可禁用用户", status_code=403)

    user = db.query(UserAccount).filter(UserAccount.user_id == user_id).first()
    if not user:
        raise AppError("NOT_FOUND", "用户不存在", status_code=404)

    if user.user_id == current_user.user_id:
        raise AppError("VALIDATION_ERROR", "不可禁用当前登录用户", status_code=422)

    user.status = UserStatus.disabled
    write_audit(
        db,
        current_user.id,
        action="user.disable",
        object_type="user",
        object_id=user.user_id,
        diff={"status": "disabled"},
    )
    db.commit()
    return success_response(request, {"user_id": user.user_id, "status": "disabled"})
