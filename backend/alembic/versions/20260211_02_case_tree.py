"""add case tree node and test_case tree relation

Revision ID: 20260211_02
Revises: 20260208_01
Create Date: 2026-02-11 18:30:00
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260211_02"
down_revision: Union[str, None] = "20260208_01"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def _split_module_path(module_value: str | None) -> list[str]:
    if not module_value:
        return ["未分类"]
    parts = [item.strip() for item in module_value.replace("\\", "/").split("/") if item.strip()]
    return parts or ["未分类"]


def _backfill_legacy_tree() -> None:
    connection = op.get_bind()
    metadata = sa.MetaData()

    case_tree_node = sa.Table(
        "case_tree_node",
        metadata,
        sa.Column("id", sa.Integer),
        sa.Column("node_id", sa.String(32)),
        sa.Column("name", sa.String(128)),
        sa.Column("node_type", sa.String(16)),
        sa.Column("parent_id", sa.Integer),
        sa.Column("full_path", sa.String(512)),
    )
    test_case = sa.Table(
        "test_case",
        metadata,
        sa.Column("id", sa.Integer),
        sa.Column("module", sa.String(128)),
        sa.Column("tree_node_id", sa.Integer),
    )

    existing_nodes = connection.execute(
        sa.select(
            case_tree_node.c.id,
            case_tree_node.c.node_id,
            case_tree_node.c.node_type,
            case_tree_node.c.parent_id,
            case_tree_node.c.full_path,
        )
    ).fetchall()
    path_to_id = {str(row.full_path): int(row.id) for row in existing_nodes}
    used_node_ids = {
        int(str(row.node_id).split("-")[-1])
        for row in existing_nodes
        if row.node_id and str(row.node_id).startswith("NODE-") and str(row.node_id).split("-")[-1].isdigit()
    }
    next_node_seq = (max(used_node_ids) if used_node_ids else 0) + 1

    def next_node_id() -> str:
        nonlocal next_node_seq
        value = f"NODE-{next_node_seq:04d}"
        next_node_seq += 1
        return value

    def get_or_create_node(name: str, node_type: str, parent_id: int | None, parent_full_path: str | None) -> int:
        full_path = name if not parent_full_path else f"{parent_full_path}/{name}"
        existing_node_id = path_to_id.get(full_path)
        if existing_node_id:
            return existing_node_id

        result = connection.execute(
            case_tree_node.insert().values(
                node_id=next_node_id(),
                name=name,
                node_type=node_type,
                parent_id=parent_id,
                full_path=full_path,
                created_at=sa.func.now(),
                updated_at=sa.func.now(),
            )
        )
        node_pk = int(result.inserted_primary_key[0])
        path_to_id[full_path] = node_pk
        return node_pk

    rows: Iterable[sa.Row] = connection.execute(
        sa.select(test_case.c.id, test_case.c.module).where(test_case.c.tree_node_id.is_(None))
    ).fetchall()

    for row in rows:
        module_parts = _split_module_path(row.module)
        parent_id: int | None = None
        parent_path: str | None = None
        for part in module_parts:
            parent_id = get_or_create_node(part, "directory", parent_id, parent_path)
            parent_path = part if not parent_path else f"{parent_path}/{part}"

        file_node_id = get_or_create_node("legacy_cases", "file", parent_id, parent_path)
        connection.execute(
            test_case.update().where(test_case.c.id == row.id).values(tree_node_id=file_node_id)
        )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "case_tree_node" not in inspector.get_table_names():
        op.create_table(
            "case_tree_node",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("node_id", sa.String(length=32), nullable=False, unique=True),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("node_type", sa.String(length=16), nullable=False),
            sa.Column("parent_id", sa.Integer(), sa.ForeignKey("case_tree_node.id"), nullable=True),
            sa.Column("full_path", sa.String(length=512), nullable=False, unique=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("parent_id", "name", name="uq_case_tree_node_parent_name"),
        )

    test_case_columns = {column["name"] for column in inspector.get_columns("test_case")}
    if "tree_node_id" not in test_case_columns:
        op.add_column("test_case", sa.Column("tree_node_id", sa.Integer(), nullable=True))

    fk_names = {fk["name"] for fk in inspector.get_foreign_keys("test_case") if fk.get("name")}
    if "fk_test_case_tree_node_id_case_tree_node" not in fk_names:
        op.create_foreign_key(
            "fk_test_case_tree_node_id_case_tree_node",
            "test_case",
            "case_tree_node",
            ["tree_node_id"],
            ["id"],
        )

    case_tree_indexes = {idx["name"] for idx in inspector.get_indexes("case_tree_node")}
    if "ix_case_tree_node_parent_id" not in case_tree_indexes:
        op.create_index("ix_case_tree_node_parent_id", "case_tree_node", ["parent_id"])

    test_case_indexes = {idx["name"] for idx in inspector.get_indexes("test_case")}
    if "ix_test_case_tree_node_id" not in test_case_indexes:
        op.create_index("ix_test_case_tree_node_id", "test_case", ["tree_node_id"])

    _backfill_legacy_tree()


def downgrade() -> None:
    op.drop_index("ix_test_case_tree_node_id", table_name="test_case")
    op.drop_index("ix_case_tree_node_parent_id", table_name="case_tree_node")
    op.drop_constraint("fk_test_case_tree_node_id_case_tree_node", "test_case", type_="foreignkey")
    op.drop_column("test_case", "tree_node_id")
    op.drop_table("case_tree_node")
