"""add automation runtime persistence model

Revision ID: 20260213_04
Revises: 20260212_03
Create Date: 2026-02-13 18:10:00
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260213_04"
down_revision: Union[str, None] = "20260212_03"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "automation_configuration" not in inspector.get_table_names():
        op.create_table(
            "automation_configuration",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("framework_key", sa.String(length=64), nullable=False),
            sa.Column("config_key", sa.String(length=128), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("updated_by", sa.String(length=64), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("framework_key", "config_key", name="uq_automation_configuration_framework_config"),
        )

    if "automation_suite" not in inspector.get_table_names():
        op.create_table(
            "automation_suite",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("framework_key", sa.String(length=64), nullable=False),
            sa.Column("suite_key", sa.String(length=128), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("module_name", sa.String(length=128), nullable=True),
            sa.Column("path_expr", sa.String(length=256), nullable=True),
            sa.Column("testpaths_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("python_files_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("source_type", sa.String(length=32), nullable=False, server_default="manual"),
            sa.Column("updated_by", sa.String(length=64), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("framework_key", "suite_key", name="uq_automation_suite_framework_suite"),
        )

    if "automation_run" not in inspector.get_table_names():
        op.create_table(
            "automation_run",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("run_id", sa.String(length=32), nullable=False, unique=True),
            sa.Column("framework_key", sa.String(length=64), nullable=False),
            sa.Column("entry_name", sa.String(length=128), nullable=False),
            sa.Column("configuration_key", sa.String(length=128), nullable=False),
            sa.Column("test_suite_key", sa.String(length=128), nullable=False),
            sa.Column("operation_mode", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("triggered_by", sa.String(length=64), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("container_name", sa.String(length=128), nullable=True),
            sa.Column("remote_run_dir", sa.String(length=512), nullable=True),
            sa.Column("report_archive_path", sa.String(length=512), nullable=True),
            sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("log_cursor", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("meta_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if "automation_run_log" not in inspector.get_table_names():
        op.create_table(
            "automation_run_log",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("run_id", sa.Integer(), sa.ForeignKey("automation_run.id"), nullable=False),
            sa.Column("seq", sa.Integer(), nullable=False),
            sa.Column("line", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("run_id", "seq", name="uq_automation_run_log_run_seq"),
        )

    indexes = {idx["name"] for idx in inspector.get_indexes("automation_configuration")}
    if "ix_automation_configuration_framework_key" not in indexes:
        op.create_index("ix_automation_configuration_framework_key", "automation_configuration", ["framework_key"])

    indexes = {idx["name"] for idx in inspector.get_indexes("automation_suite")}
    if "ix_automation_suite_framework_key" not in indexes:
        op.create_index("ix_automation_suite_framework_key", "automation_suite", ["framework_key"])

    indexes = {idx["name"] for idx in inspector.get_indexes("automation_run")}
    if "ix_automation_run_framework_key_started_at" not in indexes:
        op.create_index(
            "ix_automation_run_framework_key_started_at",
            "automation_run",
            ["framework_key", "started_at"],
        )
    if "ix_automation_run_status_started_at" not in indexes:
        op.create_index("ix_automation_run_status_started_at", "automation_run", ["status", "started_at"])

    indexes = {idx["name"] for idx in inspector.get_indexes("automation_run_log")}
    if "ix_automation_run_log_run_id_seq" not in indexes:
        op.create_index("ix_automation_run_log_run_id_seq", "automation_run_log", ["run_id", "seq"])


def downgrade() -> None:
    op.drop_index("ix_automation_run_log_run_id_seq", table_name="automation_run_log")
    op.drop_index("ix_automation_run_status_started_at", table_name="automation_run")
    op.drop_index("ix_automation_run_framework_key_started_at", table_name="automation_run")
    op.drop_index("ix_automation_suite_framework_key", table_name="automation_suite")
    op.drop_index("ix_automation_configuration_framework_key", table_name="automation_configuration")

    op.drop_table("automation_run_log")
    op.drop_table("automation_run")
    op.drop_table("automation_suite")
    op.drop_table("automation_configuration")
