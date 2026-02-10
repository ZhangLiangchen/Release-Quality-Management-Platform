from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .database import UserAccount, UserStatus, get_db
from .errors import AppError
from .settings import get_settings

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
auth_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(username: str) -> str:
    settings = get_settings()
    expire_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_min)
    payload = {
        "sub": username,
        "exp": expire_at,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise AppError("UNAUTHORIZED", "token 无效或已过期", status_code=401) from exc


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(auth_scheme),
    db: Session = Depends(get_db),
) -> UserAccount:
    if not credentials:
        raise AppError("UNAUTHORIZED", "缺少认证信息", status_code=401)

    payload = decode_access_token(credentials.credentials)
    username = payload.get("sub")
    if not username:
        raise AppError("UNAUTHORIZED", "token 缺少主体信息", status_code=401)

    user = db.query(UserAccount).filter(UserAccount.username == username).first()
    if not user or user.status != UserStatus.active:
        raise AppError("UNAUTHORIZED", "用户不存在或已禁用", status_code=401)
    return user
