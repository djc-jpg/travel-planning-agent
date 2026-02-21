"""Compare two eval JSON reports and emit markdown summary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _index_cases(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row.get("id", ""): row for row in report.get("cases", [])}


def _render(base: dict[str, Any], new: dict[str, Any]) -> str:
    base_summary = base.get("summary", {})
    new_summary = new.get("summary", {})

    lines: list[str] = []
    lines.append("# Eval Comparison")
    lines.append("")
    lines.append("## Overall")
    lines.append("")
    lines.append("| Metric | Baseline | Improved | Delta |")
    lines.append("| --- | --- | --- | --- |")

    for key in ("total_cases", "passed_cases", "pass_rate", "average_score"):
        b = float(base_summary.get(key, 0.0))
        n = float(new_summary.get(key, 0.0))
        lines.append(f"| {key} | {b:.4f} | {n:.4f} | {n - b:+.4f} |")

    lines.append("")
    lines.append("## Case Deltas")
    lines.append("")
    lines.append("| Case ID | Baseline | Improved | Delta |")
    lines.append("| --- | --- | --- | --- |")

    b_cases = _index_cases(base)
    n_cases = _index_cases(new)
    all_ids = sorted(set(b_cases) | set(n_cases))
    for case_id in all_ids:
        b_score = float(b_cases.get(case_id, {}).get("score", 0.0))
        n_score = float(n_cases.get(case_id, {}).get("score", 0.0))
        lines.append(f"| {case_id} | {b_score:.4f} | {n_score:.4f} | {n_score - b_score:+.4f} |")

    lines.append("")
    return "\n".join(lines)


def run(base_path: Path, new_path: Path, out_path: Path) -> Path:
    base = _load(base_path)
    new = _load(new_path)
    markdown = _render(base, new)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(markdown, encoding="utf-8")
    print(f"saved: {out_path}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two eval reports")
    parser.add_argument("--base", required=True, help="baseline report json")
    parser.add_argument("--new", required=True, help="improved report json")
    parser.add_argument("--out", default="eval/reports/compare.md", help="output markdown path")
    args = parser.parse_args()
    run(Path(args.base), Path(args.new), Path(args.out))


if __name__ == "__main__":
    main()

