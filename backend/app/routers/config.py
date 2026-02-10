from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import ProjectConfig, UserAccount, UserRole, Version, get_db
from ..errors import AppError
from ..response import success_response
from ..schemas import ProjectConfigOut, ProjectConfigUpdate
from ..services import find_version_by_key, write_audit

router = APIRouter(prefix="/api/v1/config", tags=["config"])


def ensure_config(db: Session) -> ProjectConfig:
    config = db.query(ProjectConfig).first()
    if config:
        return config

    current_version = db.query(Version).filter(Version.is_current.is_(True)).first()
    if not current_version:
        raise AppError("NOT_FOUND", "系统未配置默认版本", status_code=500)

    config = ProjectConfig(project_name="测试管理系统", current_version_id=current_version.id)
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


@router.get("")
def get_config(request: Request, db: Session = Depends(get_db), _: UserAccount = Depends(get_current_user)):
    config = ensure_config(db)
    current_version = db.query(Version).filter(Version.id == config.current_version_id).first()
    if not current_version:
        raise AppError("NOT_FOUND", "默认版本不存在", status_code=500)

    data = ProjectConfigOut(project_name=config.project_name, current_version_key=current_version.version_key)
    return success_response(request, data.model_dump())


@router.put("")
def update_config(
    payload: ProjectConfigUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    if current_user.role not in {UserRole.admin, UserRole.qa}:
        raise AppError("FORBIDDEN", "无权限修改配置", status_code=403)

    config = ensure_config(db)
    before = {"project_name": config.project_name, "current_version_id": config.current_version_id}

    config.project_name = payload.project_name

    if payload.current_version_key:
        if current_user.role != UserRole.admin:
            raise AppError("FORBIDDEN", "仅管理员可修改系统默认版本", status_code=403)

        version = find_version_by_key(db, payload.current_version_key)
        db.query(Version).update({Version.is_current: False})
        version.is_current = True
        config.current_version_id = version.id

    write_audit(
        db,
        current_user.id,
        action="config.update",
        object_type="project_config",
        object_id=str(config.id),
        diff={"before": before, "after": {"project_name": config.project_name, "current_version_id": config.current_version_id}},
    )

    db.commit()
    db.refresh(config)
    current_version = db.query(Version).filter(Version.id == config.current_version_id).first()
    data = ProjectConfigOut(project_name=config.project_name, current_version_key=current_version.version_key)
    return success_response(request, data.model_dump())
