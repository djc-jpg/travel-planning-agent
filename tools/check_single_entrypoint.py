"""Guard script enforcing a single planning entrypoint chain."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path

PRESENTATION_FILES = [
    Path("app/api/main.py"),
    Path("app/cli.py"),
    Path("app/eval/run_eval.py"),
    Path("eval/run.py"),
]
SERVICE_BRIDGE_FILES = [
    Path("app/services/plan_service.py"),
]
FORBIDDEN_PREFIXES = (
    "app.agent",
    "app.application.graph",
    "app.application.services.workflow",
)
ALLOWED_PLAN_TRIP_IMPORTS = {
    "app.application.plan_trip.plan_trip",
    "app.application.plan_trip",
}
ALLOWED_PRESENTATION_IMPORTS = ALLOWED_PLAN_TRIP_IMPORTS | {
    "app.services.plan_service.execute_plan",
    "app.services.plan_service",
}


def _collect_imports(tree: ast.AST) -> list[tuple[str, str | None]]:
    imports: list[tuple[str, str | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((alias.name, alias.asname))
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            for alias in node.names:
                if base:
                    imports.append((f"{base}.{alias.name}", alias.asname))
                else:
                    imports.append((alias.name, alias.asname))
    return imports


def _has_call(tree: ast.AST, names: set[str]) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in names:
                return True
            if isinstance(func, ast.Attribute) and func.attr in names:
                return True
    return False


def check_single_entrypoint(files: list[Path] | None = None) -> list[str]:
    violations: list[str] = []
    targets = files or (PRESENTATION_FILES + SERVICE_BRIDGE_FILES)

    for path in targets:
        if not path.exists():
            violations.append(f"{path.as_posix()}: file missing")
            continue

        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=str(path))
        imports = _collect_imports(tree)

        has_allowed_import = False
        for full_name, _alias in imports:
            allowed_imports = (
                ALLOWED_PRESENTATION_IMPORTS
                if path in PRESENTATION_FILES
                else ALLOWED_PLAN_TRIP_IMPORTS
            )
            if full_name in allowed_imports:
                has_allowed_import = True

            if any(
                full_name == prefix or full_name.startswith(prefix + ".")
                for prefix in FORBIDDEN_PREFIXES
            ):
                violations.append(
                    f"{path.as_posix()}: forbidden import `{full_name}`; use app.application.plan_trip only"
                )

            if full_name.endswith(".compile_graph") or full_name.endswith(".build_graph"):
                violations.append(
                    f"{path.as_posix()}: direct graph import `{full_name}` is forbidden"
                )

        if not has_allowed_import:
            if path in PRESENTATION_FILES:
                violations.append(
                    f"{path.as_posix()}: missing import of execute_plan(...) or plan_trip(...)"
                )
            else:
                violations.append(
                    f"{path.as_posix()}: missing import of single entrypoint plan_trip"
                )

        if path in PRESENTATION_FILES and not _has_call(tree, {"execute_plan", "plan_trip"}):
            violations.append(
                f"{path.as_posix()}: missing call to execute_plan(...) or plan_trip(...)"
            )
        if path in SERVICE_BRIDGE_FILES and not _has_call(tree, {"plan_trip"}):
            violations.append(
                f"{path.as_posix()}: missing call to plan_trip(...)"
            )

    return sorted(set(violations))


def main() -> int:
    parser = argparse.ArgumentParser(description="Check single plan_trip entrypoint usage")
    parser.add_argument(
        "--files",
        nargs="*",
        default=[],
        help="Optional explicit file list to scan",
    )
    args = parser.parse_args()

    files = [Path(item) for item in args.files] if args.files else None
    violations = check_single_entrypoint(files)
    if violations:
        print("Single entrypoint violations:")
        for line in violations:
            print(f"- {line}")
        return 1

    print("Single entrypoint check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
