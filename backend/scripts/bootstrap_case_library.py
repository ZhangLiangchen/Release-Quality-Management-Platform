from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.database import (  # noqa: E402
    CaseTreeNode,
    CaseTreeNodeType,
    TestCase,
    TestCaseStatus,
    UserAccount,
    UserRole,
    Version,
    SessionLocal,
)
from app.services import (  # noqa: E402
    cleanup_placeholder_cases,
    ensure_version_case_status_rows,
    find_or_create_case_tree_node,
    get_or_create_default_snapshot,
    write_audit,
)

DEFAULT_CASE_JSON = ROOT_DIR / "app" / "data" / "hypersonic_cases.json"


def init_case_seq(session) -> int:
    max_seq = 0
    for (case_id,) in session.query(TestCase.case_id).all():
        if not case_id or not str(case_id).startswith("HSC-"):
            continue
        suffix = str(case_id).replace("HSC-", "")
        if suffix.isdigit():
            max_seq = max(max_seq, int(suffix))
    return max_seq + 1


def get_actor_id(session) -> int | None:
    actor = session.query(UserAccount).filter(UserAccount.role == UserRole.admin).order_by(UserAccount.id.asc()).first()
    return actor.id if actor else None


def upsert_cases(case_json_path: Path) -> None:
    payload = json.loads(case_json_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError("case json format invalid: top-level must be list")

    session = SessionLocal()
    try:
        actor_id = get_actor_id(session)

        cleanup_stats = cleanup_placeholder_cases(session)
        created = 0
        updated = 0
        next_seq = init_case_seq(session)
        reserved_case_ids = {str(item.case_id) for item in session.query(TestCase.case_id).all()}

        def allocate_case_id() -> str:
            nonlocal next_seq
            while True:
                candidate = f"HSC-{next_seq:07d}"
                next_seq += 1
                if candidate not in reserved_case_ids:
                    reserved_case_ids.add(candidate)
                    return candidate

        for item in payload:
            case_key = str(item.get("case_key", "")).strip()
            title = str(item.get("title", "")).strip()
            module = str(item.get("module", "")).strip()
            steps = str(item.get("steps", "")).strip()
            expected = str(item.get("expected", "")).strip()
            tags = [str(tag).strip() for tag in item.get("tags", []) if str(tag).strip()]
            tree_segments = [str(segment).strip() for segment in item.get("tree_segments", []) if str(segment).strip()]

            if not case_key or not title or not module or not steps or not expected or len(tree_segments) < 2:
                continue

            parent = None
            for segment in tree_segments[:-1]:
                parent = find_or_create_case_tree_node(
                    session,
                    name=segment,
                    node_type=CaseTreeNodeType.directory,
                    parent=parent,
                )

            file_node = find_or_create_case_tree_node(
                session,
                name=tree_segments[-1],
                node_type=CaseTreeNodeType.file,
                parent=parent,
            )

            existing = session.query(TestCase).filter(TestCase.case_key == case_key).first()
            if existing:
                existing.title = title
                existing.module = module
                existing.steps = steps
                existing.expected = expected
                existing.tags_json = sorted(set(tags))
                existing.tree_node_id = file_node.id
                existing.status = TestCaseStatus.active
                updated += 1
                continue

            session.add(
                TestCase(
                    case_id=allocate_case_id(),
                    case_key=case_key,
                    tree_node_id=file_node.id,
                    module=module,
                    title=title,
                    steps=steps,
                    expected=expected,
                    tags_json=sorted(set(tags)),
                    status=TestCaseStatus.active,
                )
            )
            created += 1

        session.flush()
        versions = session.query(Version).all()
        for version in versions:
            snapshot = get_or_create_default_snapshot(session, version, actor_id)
            ensure_version_case_status_rows(session, version, snapshot, actor_id)

        write_audit(
            session,
            actor_id,
            action="case.bootstrap.hypersonic",
            object_type="test_case",
            object_id="bulk",
            diff={
                "source": str(case_json_path),
                "created": created,
                "updated": updated,
                "cleanup": cleanup_stats,
                "case_tree_nodes": session.query(CaseTreeNode).count(),
                "total_cases": session.query(TestCase).filter(TestCase.status == TestCaseStatus.active).count(),
            },
        )
        session.commit()
        print(
            json.dumps(
                {
                    "cleanup": cleanup_stats,
                    "created": created,
                    "updated": updated,
                    "case_tree_nodes": session.query(CaseTreeNode).count(),
                    "total_cases": session.query(TestCase).filter(TestCase.status == TestCaseStatus.active).count(),
                },
                ensure_ascii=False,
            )
        )
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap case tree and text cases from hypersonic export json.")
    parser.add_argument("--case-json", type=Path, default=DEFAULT_CASE_JSON)
    args = parser.parse_args()

    case_json_path = args.case_json.resolve()
    if not case_json_path.exists():
        raise SystemExit(f"case json not found: {case_json_path}")
    upsert_cases(case_json_path)


if __name__ == "__main__":
    main()
