from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import Issue, UserAccount, get_db
from ..response import success_response
from ..services import ISSUE_GROUP_STATUSES, calculate_dashboard, find_version_by_key, issue_to_dict

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/quality")
def dashboard_quality(
    version_key: str,
    request: Request,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(get_current_user),
):
    version = find_version_by_key(db, version_key)
    data = calculate_dashboard(db, version)
    return success_response(request, data)


@router.get("/issues/pending")
def dashboard_pending_issues(
    version_key: str,
    request: Request,
    db: Session = Depends(get_db),
    _: UserAccount = Depends(get_current_user),
):
    version = find_version_by_key(db, version_key)
    issues = (
        db.query(Issue)
        .filter(Issue.found_version_id == version.id, Issue.status.in_(ISSUE_GROUP_STATUSES["pending"]))
        .order_by(Issue.updated_at.desc())
        .all()
    )
    data = [issue_to_dict(issue, db) for issue in issues]
    return success_response(request, data)
