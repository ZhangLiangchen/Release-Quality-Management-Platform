"""add suite plan run execution model

Revision ID: 20260212_03
Revises: 20260211_02
Create Date: 2026-02-12 01:10:00
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260212_03"
down_revision: Union[str, None] = "20260211_02"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "case_suite" not in inspector.get_table_names():
        op.create_table(
            "case_suite",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("suite_key", sa.String(length=32), nullable=False, unique=True),
            sa.Column("version_id", sa.Integer(), sa.ForeignKey("version.id"), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_account.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("version_id", "name", name="uq_case_suite_version_name"),
        )

    if "case_suite_version" not in inspector.get_table_names():
        op.create_table(
            "case_suite_version",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("suite_version_key", sa.String(length=32), nullable=False, unique=True),
            sa.Column("suite_id", sa.Integer(), sa.ForeignKey("case_suite.id"), nullable=False),
            sa.Column("ver_no", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_account.id"), nullable=True),
            sa.Column("published_by", sa.Integer(), sa.ForeignKey("user_account.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("suite_id", "ver_no", name="uq_case_suite_version_ver_no"),
        )

    if "suite_case_ref" not in inspector.get_table_names():
        op.create_table(
            "suite_case_ref",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("suite_version_id", sa.Integer(), sa.ForeignKey("case_suite_version.id"), nullable=False),
            sa.Column("case_id", sa.Integer(), sa.ForeignKey("test_case.id"), nullable=False),
            sa.Column("order_no", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("module_path_snapshot", sa.String(length=256), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("suite_version_id", "case_id", name="uq_suite_case_ref_version_case"),
        )

    if "test_plan" not in inspector.get_table_names():
        op.create_table(
            "test_plan",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("plan_key", sa.String(length=32), nullable=False, unique=True),
            sa.Column("version_id", sa.Integer(), sa.ForeignKey("version.id"), nullable=False),
            sa.Column("suite_version_id", sa.Integer(), sa.ForeignKey("case_suite_version.id"), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_account.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if "test_run" not in inspector.get_table_names():
        op.create_table(
            "test_run",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("run_key", sa.String(length=32), nullable=False, unique=True),
            sa.Column("plan_id", sa.Integer(), sa.ForeignKey("test_plan.id"), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("build_no", sa.String(length=128), nullable=True),
            sa.Column("environment", sa.String(length=128), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("user_account.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        )

    if "run_case" not in inspector.get_table_names():
        op.create_table(
            "run_case",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("run_case_key", sa.String(length=32), nullable=False, unique=True),
            sa.Column("run_id", sa.Integer(), sa.ForeignKey("test_run.id"), nullable=False),
            sa.Column("case_id", sa.Integer(), sa.ForeignKey("test_case.id"), nullable=False),
            sa.Column("case_key_snapshot", sa.String(length=32), nullable=False),
            sa.Column("title_snapshot", sa.String(length=256), nullable=False),
            sa.Column("module_snapshot", sa.String(length=128), nullable=False),
            sa.Column("steps_snapshot", sa.Text(), nullable=False),
            sa.Column("expected_snapshot", sa.Text(), nullable=False),
            sa.Column("assignee_id", sa.Integer(), sa.ForeignKey("user_account.id"), nullable=True),
            sa.Column("current_status", sa.String(length=16), nullable=False),
            sa.Column("last_updated_by", sa.Integer(), sa.ForeignKey("user_account.id"), nullable=True),
            sa.Column("last_updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("run_id", "case_id", name="uq_run_case_run_case"),
        )

    if "run_case_history" not in inspector.get_table_names():
        op.create_table(
            "run_case_history",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("run_case_id", sa.Integer(), sa.ForeignKey("run_case.id"), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("remark", sa.Text(), nullable=True),
            sa.Column("operator_id", sa.Integer(), sa.ForeignKey("user_account.id"), nullable=True),
            sa.Column("operated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("attachments_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        )

    indexes = {idx["name"] for idx in inspector.get_indexes("case_suite")}
    if "ix_case_suite_version_id" not in indexes:
        op.create_index("ix_case_suite_version_id", "case_suite", ["version_id"])

    indexes = {idx["name"] for idx in inspector.get_indexes("case_suite_version")}
    if "ix_case_suite_version_suite_id" not in indexes:
        op.create_index("ix_case_suite_version_suite_id", "case_suite_version", ["suite_id"])

    indexes = {idx["name"] for idx in inspector.get_indexes("suite_case_ref")}
    if "ix_suite_case_ref_suite_version_id" not in indexes:
        op.create_index("ix_suite_case_ref_suite_version_id", "suite_case_ref", ["suite_version_id"])

    indexes = {idx["name"] for idx in inspector.get_indexes("test_plan")}
    if "ix_test_plan_version_id" not in indexes:
        op.create_index("ix_test_plan_version_id", "test_plan", ["version_id"])
    if "ix_test_plan_suite_version_id" not in indexes:
        op.create_index("ix_test_plan_suite_version_id", "test_plan", ["suite_version_id"])

    indexes = {idx["name"] for idx in inspector.get_indexes("test_run")}
    if "ix_test_run_plan_id" not in indexes:
        op.create_index("ix_test_run_plan_id", "test_run", ["plan_id"])
    if "ix_test_run_started_at" not in indexes:
        op.create_index("ix_test_run_started_at", "test_run", ["started_at"])

    indexes = {idx["name"] for idx in inspector.get_indexes("run_case")}
    if "ix_run_case_run_id" not in indexes:
        op.create_index("ix_run_case_run_id", "run_case", ["run_id"])
    if "ix_run_case_case_id" not in indexes:
        op.create_index("ix_run_case_case_id", "run_case", ["case_id"])

    indexes = {idx["name"] for idx in inspector.get_indexes("run_case_history")}
    if "ix_run_case_history_run_case_id_operated_at" not in indexes:
        op.create_index("ix_run_case_history_run_case_id_operated_at", "run_case_history", ["run_case_id", "operated_at"])


def downgrade() -> None:
    op.drop_index("ix_run_case_history_run_case_id_operated_at", table_name="run_case_history")
    op.drop_index("ix_run_case_case_id", table_name="run_case")
    op.drop_index("ix_run_case_run_id", table_name="run_case")
    op.drop_index("ix_test_run_started_at", table_name="test_run")
    op.drop_index("ix_test_run_plan_id", table_name="test_run")
    op.drop_index("ix_test_plan_suite_version_id", table_name="test_plan")
    op.drop_index("ix_test_plan_version_id", table_name="test_plan")
    op.drop_index("ix_suite_case_ref_suite_version_id", table_name="suite_case_ref")
    op.drop_index("ix_case_suite_version_suite_id", table_name="case_suite_version")
    op.drop_index("ix_case_suite_version_id", table_name="case_suite")

    op.drop_table("run_case_history")
    op.drop_table("run_case")
    op.drop_table("test_run")
    op.drop_table("test_plan")
    op.drop_table("suite_case_ref")
    op.drop_table("case_suite_version")
    op.drop_table("case_suite")
