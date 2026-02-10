"""initial schema

Revision ID: 20260208_01
Revises: 
Create Date: 2026-02-08 00:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260208_01"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "version",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("version_key", sa.String(length=64), nullable=False, unique=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "user_account",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=32), nullable=False, unique=True),
        sa.Column("username", sa.String(length=64), nullable=False, unique=True),
        sa.Column("email", sa.String(length=128), nullable=False, unique=True),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("password_hash", sa.String(length=256), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "project_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_name", sa.String(length=128), nullable=False),
        sa.Column("current_version_id", sa.Integer(), sa.ForeignKey("version.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "test_case",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.String(length=32), nullable=False, unique=True),
        sa.Column("case_key", sa.String(length=32), nullable=False, unique=True),
        sa.Column("module", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("steps", sa.Text(), nullable=False),
        sa.Column("expected", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="medium"),
        sa.Column("tags_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "case_set_snapshot",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("snapshot_id", sa.String(length=32), nullable=False, unique=True),
        sa.Column("version_id", sa.Integer(), sa.ForeignKey("version.id"), nullable=False),
        sa.Column("case_set_id", sa.String(length=32), nullable=True),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_account.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "version_case_status",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("version_id", sa.Integer(), sa.ForeignKey("version.id"), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("case_set_snapshot.id"), nullable=False),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("test_case.id"), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="not_run"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("user_account.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("version_id", "snapshot_id", "case_id", name="uq_version_snapshot_case"),
    )

    op.create_table(
        "case_status_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("version_id", sa.Integer(), sa.ForeignKey("version.id"), nullable=False),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("test_case.id"), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("executor_id", sa.Integer(), sa.ForeignKey("user_account.id"), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("attachments_json", sa.JSON(), nullable=False),
    )

    op.create_table(
        "issue",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("issue_id", sa.String(length=32), nullable=False, unique=True),
        sa.Column("issue_key", sa.String(length=32), nullable=False, unique=True),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="new"),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="medium"),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="major"),
        sa.Column("assignee_id", sa.Integer(), sa.ForeignKey("user_account.id"), nullable=True),
        sa.Column("reporter_id", sa.Integer(), sa.ForeignKey("user_account.id"), nullable=False),
        sa.Column("found_version_id", sa.Integer(), sa.ForeignKey("version.id"), nullable=False),
        sa.Column("fix_version_id", sa.Integer(), sa.ForeignKey("version.id"), nullable=True),
        sa.Column("verify_version_id", sa.Integer(), sa.ForeignKey("version.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "issue_case_link",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("issue_id", sa.Integer(), sa.ForeignKey("issue.id"), nullable=False),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("test_case.id"), nullable=False),
        sa.Column("link_type", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.UniqueConstraint("issue_id", "case_id", "link_type", name="uq_issue_case_link"),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("user_account.id"), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("object_type", sa.String(length=64), nullable=False),
        sa.Column("object_id", sa.String(length=64), nullable=False),
        sa.Column("diff_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_index("ix_issue_found_version_status", "issue", ["found_version_id", "status"])
    op.create_index(
        "ix_case_status_history_version_case_executed_at",
        "case_status_history",
        ["version_id", "case_id", "executed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_case_status_history_version_case_executed_at", table_name="case_status_history")
    op.drop_index("ix_issue_found_version_status", table_name="issue")
    op.drop_table("audit_log")
    op.drop_table("issue_case_link")
    op.drop_table("issue")
    op.drop_table("case_status_history")
    op.drop_table("version_case_status")
    op.drop_table("case_set_snapshot")
    op.drop_table("test_case")
    op.drop_table("project_config")
    op.drop_table("user_account")
    op.drop_table("version")
