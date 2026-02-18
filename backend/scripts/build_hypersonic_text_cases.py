from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_SOURCE_ROOT = Path("/Users/zhangliangchen/PycharmProjects/hypersonic-dev/hypersonic/testcases")
DEFAULT_OUTPUT = Path(
    "/Users/zhangliangchen/PycharmProjects/Release-Quality-Management-Platform/backend/app/data/hypersonic_cases.json"
)


@dataclass
class ParsedFunction:
    class_name: str | None
    function_name: str
    lineno: int
    docstring: str | None
    priority: str | None
    features: list[str]


def _safe_token(value: str, max_len: int) -> str:
    token = re.sub(r"[^A-Za-z0-9]", "", value).upper()
    if not token:
        token = "X"
    return token[:max_len]


def _file_token(file_stem: str) -> str:
    match = re.match(r"test_0*([0-9]+)_?(.*)", file_stem)
    if match:
        number = match.group(1)[-2:].rjust(2, "0")
        remain = _safe_token(match.group(2), 5)
        return f"TEST{number}{remain}"[:8]
    return _safe_token(file_stem, 8)


def _humanize_function_name(function_name: str) -> str:
    name = function_name
    if name.startswith("test_"):
        name = name[5:]
    name = name.replace("_", " ").strip()
    if not name:
        return function_name
    return name[0].upper() + name[1:]


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Call):
        return _dotted_name(node.func)
    return ""


def _extract_feature_from_decorator(decorator: ast.AST) -> str | None:
    if not isinstance(decorator, ast.Call):
        return None
    if _dotted_name(decorator.func) not in {"allure.feature", "allure.story"}:
        return None
    if not decorator.args:
        return None
    arg = decorator.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        value = arg.value.strip()
        return value if value else None
    return None


def _extract_priority_from_decorator(decorator: ast.AST) -> str | None:
    dotted = _dotted_name(decorator)
    if not dotted.startswith("pytest.mark.p"):
        return None
    tail = dotted.split(".")[-1]
    return tail if re.fullmatch(r"p[0-9]+", tail) else None


def _parse_test_functions(file_path: Path) -> list[ParsedFunction]:
    source = file_path.read_text(encoding="utf-8", errors="ignore")
    tree = ast.parse(source)
    parsed: list[ParsedFunction] = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            class_features = [value for value in (_extract_feature_from_decorator(dec) for dec in node.decorator_list) if value]
            for member in node.body:
                if not isinstance(member, ast.FunctionDef) or not member.name.startswith("test_"):
                    continue
                priority = None
                features = list(class_features)
                for decorator in member.decorator_list:
                    priority = priority or _extract_priority_from_decorator(decorator)
                    feature = _extract_feature_from_decorator(decorator)
                    if feature:
                        features.append(feature)
                parsed.append(
                    ParsedFunction(
                        class_name=node.name,
                        function_name=member.name,
                        lineno=member.lineno,
                        docstring=ast.get_docstring(member),
                        priority=priority,
                        features=sorted(set(features)),
                    )
                )
            continue

        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            priority = None
            features: list[str] = []
            for decorator in node.decorator_list:
                priority = priority or _extract_priority_from_decorator(decorator)
                feature = _extract_feature_from_decorator(decorator)
                if feature:
                    features.append(feature)
            parsed.append(
                ParsedFunction(
                    class_name=None,
                    function_name=node.name,
                    lineno=node.lineno,
                    docstring=ast.get_docstring(node),
                    priority=priority,
                    features=sorted(set(features)),
                )
            )

    parsed.sort(key=lambda item: item.lineno)
    return parsed


def _extract_expected_from_doc(docstring: str | None, fallback_title: str) -> str:
    if docstring:
        for raw_line in docstring.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if any(keyword in line for keyword in ["预期", "期望", "expected", "Expected"]):
                cleaned = line.split("：", 1)[-1].split(":", 1)[-1].strip()
                if cleaned:
                    return cleaned
    return f"执行 {fallback_title} 后，结果应与自动化断言保持一致。"


def _build_steps(source_location: str, docstring: str | None) -> str:
    body = (docstring or "").strip()
    if body:
        return f"{body}\n\n来源定位：{source_location}"
    return f"按自动化脚本执行对应场景并记录关键结果。\n\n来源定位：{source_location}"


def _iter_test_files(root: Path) -> Iterable[Path]:
    files = sorted(root.rglob("test_*.py"))
    for file_path in files:
        if "__pycache__" in file_path.parts:
            continue
        yield file_path


def build_cases(source_root: Path) -> list[dict]:
    items: list[dict] = []
    used_case_keys: set[str] = set()

    for file_path in _iter_test_files(source_root):
        rel = file_path.relative_to(source_root)
        if len(rel.parts) < 2:
            continue

        top_dir = rel.parts[0]
        second_dir = rel.parts[1] if len(rel.parts) > 2 else None
        file_stem = file_path.stem
        parsed_functions = _parse_test_functions(file_path)

        top_token = _safe_token(top_dir, 6)
        second_token = _safe_token(second_dir or "GEN", 6)
        node_file = file_stem
        file_token = _file_token(file_stem)

        for index, parsed in enumerate(parsed_functions, start=1):
            base_case_key = f"HS-{top_token}-{second_token}-{file_token}-{index:03d}"
            case_key = base_case_key
            collision_seq = 2
            while case_key in used_case_keys:
                suffix = f"{collision_seq:02d}"
                case_key = f"{base_case_key[:29]}{suffix}"[:32]
                collision_seq += 1
            used_case_keys.add(case_key)

            first_line = ""
            if parsed.docstring:
                for line in parsed.docstring.splitlines():
                    line = line.strip()
                    if line:
                        first_line = line
                        break
            title = first_line or _humanize_function_name(parsed.function_name)

            source_location = f"{rel.as_posix()}::{parsed.class_name + '::' if parsed.class_name else ''}{parsed.function_name}"
            tags = [top_dir]
            if second_dir:
                tags.append(second_dir)
            if parsed.priority:
                tags.append(parsed.priority)
            tags.extend(parsed.features)

            tree_segments = [top_dir]
            if second_dir:
                tree_segments.append(second_dir)
            tree_segments.append(node_file)

            items.append(
                {
                    "case_key": case_key,
                    "title": title,
                    "module": top_dir if not second_dir else f"{top_dir}/{second_dir}",
                    "steps": _build_steps(source_location, parsed.docstring),
                    "expected": _extract_expected_from_doc(parsed.docstring, title),
                    "tags": sorted(set(tag for tag in tags if tag)),
                    "tree_segments": tree_segments,
                    "source": source_location,
                }
            )

    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Build text test cases from hypersonic automation scripts.")
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    source_root = args.source_root.resolve()
    output = args.output.resolve()
    if not source_root.exists():
        raise SystemExit(f"source root not found: {source_root}")

    cases = build_cases(source_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"generated {len(cases)} cases -> {output}")


if __name__ == "__main__":
    main()
