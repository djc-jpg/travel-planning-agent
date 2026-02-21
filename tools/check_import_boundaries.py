"""Static import boundary guard for layered architecture."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path

KNOWN_LAYERS = {"api", "application", "domain", "ports", "infrastructure", "legacy"}
FORBIDDEN_IMPORTS = {
    ("api", "legacy"): "api layer must not import legacy layer",
    ("domain", "infrastructure"): "domain layer must not import infrastructure layer",
    ("domain", "api"): "domain layer must not import api layer",
}


@dataclass(frozen=True)
class ImportRecord:
    source_file: Path
    source_module: str
    source_layer: str | None
    target_module: str
    target_layer: str | None
    lineno: int


def _module_from_path(path: Path) -> str:
    parts = list(path.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _layer_from_module(module_name: str) -> str | None:
    if module_name == "app":
        return None
    if not module_name.startswith("app."):
        return None
    parts = module_name.split(".")
    if len(parts) < 2:
        return None
    layer = parts[1]
    return layer if layer in KNOWN_LAYERS else None


def _resolve_relative_base(
    current_module: str,
    is_package_module: bool,
    level: int,
    module: str | None,
) -> str | None:
    if level <= 0:
        return module

    if is_package_module:
        current_package = current_module
    elif "." in current_module:
        current_package = current_module.rsplit(".", 1)[0]
    else:
        current_package = current_module

    package_parts = current_package.split(".")
    trim = level - 1
    if trim > len(package_parts):
        return None

    base_parts = package_parts[: len(package_parts) - trim]
    if module:
        base_parts.extend(module.split("."))
    return ".".join(part for part in base_parts if part)


def _extract_target_modules(
    node: ast.stmt,
    current_module: str,
    is_package_module: bool,
) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]

    if isinstance(node, ast.ImportFrom):
        if node.level == 0:
            if node.module:
                return [node.module]
            return []

        base = _resolve_relative_base(
            current_module=current_module,
            is_package_module=is_package_module,
            level=node.level,
            module=node.module,
        )
        if not base:
            return []

        if node.module:
            return [base]

        modules: list[str] = []
        for alias in node.names:
            if alias.name == "*":
                continue
            modules.append(f"{base}.{alias.name}")
        return modules

    return []


def collect_import_records(root: str | Path = "app") -> list[ImportRecord]:
    root_path = Path(root)
    records: list[ImportRecord] = []

    for path in sorted(root_path.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            source_text = path.read_text(encoding="utf-8")
            tree = ast.parse(source_text, filename=str(path))
        except Exception:
            continue

        source_module = _module_from_path(path)
        source_layer = _layer_from_module(source_module)
        is_package_module = path.name == "__init__.py"

        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue

            targets = _extract_target_modules(node, source_module, is_package_module)
            for target in targets:
                if not target.startswith("app."):
                    continue
                records.append(
                    ImportRecord(
                        source_file=path,
                        source_module=source_module,
                        source_layer=source_layer,
                        target_module=target,
                        target_layer=_layer_from_module(target),
                        lineno=getattr(node, "lineno", 1),
                    )
                )

    return records


def check_import_boundaries(root: str | Path = "app") -> list[str]:
    violations: list[str] = []
    for rec in collect_import_records(root):
        if rec.source_layer is None or rec.target_layer is None:
            continue
        rule = FORBIDDEN_IMPORTS.get((rec.source_layer, rec.target_layer))
        if not rule:
            continue
        violations.append(
            f"{rec.source_file.as_posix()}:{rec.lineno} "
            f"{rec.source_module} -> {rec.target_module}: {rule}"
        )
    return sorted(set(violations))


def main() -> int:
    parser = argparse.ArgumentParser(description="Check architecture import boundaries")
    parser.add_argument("--root", default="app", help="Root directory to scan")
    args = parser.parse_args()

    violations = check_import_boundaries(args.root)
    if violations:
        print("Import boundary violations:")
        for line in violations:
            print(f"- {line}")
        return 1

    print("Import boundary check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

