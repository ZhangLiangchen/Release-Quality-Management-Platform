from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Request, UploadFile

from ..auth import get_current_user
from ..database import UserAccount, UserRole
from ..errors import AppError
from ..response import success_response
from ..schemas import UploadedFileOut
from ..settings import get_settings

router = APIRouter(prefix="/api/v1/files", tags=["files"])


@router.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    current_user: UserAccount = Depends(get_current_user),
):
    if current_user.role == UserRole.viewer:
        raise AppError("FORBIDDEN", "无权限上传附件", status_code=403)

    settings = get_settings()
    settings.upload_path.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename or "").suffix
    stored_name = f"{uuid4().hex}{suffix}"
    target_path = settings.upload_path / stored_name

    file_bytes = await file.read()
    target_path.write_bytes(file_bytes)

    data = UploadedFileOut(
        name=file.filename or stored_name,
        url=f"{settings.upload_public_prefix}{stored_name}",
        size=len(file_bytes),
        mime=file.content_type,
    )
    return success_response(request, data.model_dump())
