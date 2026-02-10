from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..auth import create_access_token, get_current_user, verify_password
from ..database import UserAccount, UserStatus, get_db
from ..errors import AppError
from ..response import success_response
from ..schemas import AuthLoginOut, LoginRequest, UserOut

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(UserAccount).filter(UserAccount.username == payload.username).first()
    if not user or user.status != UserStatus.active or not verify_password(payload.password, user.password_hash):
        raise AppError("UNAUTHORIZED", "用户名或密码错误", status_code=401)

    token = create_access_token(user.username)
    data = AuthLoginOut(
        access_token=token,
        user=UserOut(
            user_id=user.user_id,
            username=user.username,
            email=user.email,
            role=user.role,
            status=user.status,
        ),
    )
    return success_response(request, data.model_dump())


@router.get("/me")
def me(request: Request, current_user: UserAccount = Depends(get_current_user)):
    data = UserOut(
        user_id=current_user.user_id,
        username=current_user.username,
        email=current_user.email,
        role=current_user.role,
        status=current_user.status,
    )
    return success_response(request, data.model_dump())
