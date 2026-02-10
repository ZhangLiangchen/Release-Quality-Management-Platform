from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from ..database import SessionLocal

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/healthz")
def healthz():
    return {"status": "ok"}


@router.get("/readyz")
def readyz():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready"}
    finally:
        db.close()
