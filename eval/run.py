"""General evaluation runner for customer-centric travel planning quality."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.application.context import make_app_context
from app.application.contracts import TripRequest, TripResult
from app.application.plan_trip import plan_trip
from app.domain.models import Itinerary


@dataclass
class CheckResult:
    name: str
    passed: bool
    evidence: str


def _load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("cases file must be a JSON array")
    return payload


def _validate_case_schema(case: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = ["id", "user_request", "constraints", "context", "expected_properties"]
    for key in required:
        if key not in case:
            errors.append(f"missing field: {key}")

    if not isinstance(case.get("id"), str) or not case.get("id", "").strip():
        errors.append("id must be non-empty string")
    if not isinstance(case.get("user_request"), str) or not case.get("user_request", "").strip():
        errors.append("user_request must be non-empty string")
    for key in ("constraints", "context", "expected_properties"):
        if key in case and not isinstance(case[key], dict):
            errors.append(f"{key} must be object")
    if "human_notes" in case and not isinstance(case["human_notes"], str):
        errors.append("human_notes must be string when provided")
    return errors


def _invoke_graph(case: dict[str, Any], ctx) -> dict[str, Any]:
    req = TripRequest(
        message=str(case.get("user_request", "")),
        constraints=dict(case.get("constraints", {})) if isinstance(case.get("constraints"), dict) else {},
        metadata={"context": dict(case.get("context", {})) if isinstance(case.get("context"), dict) else {}},
    )
    result = plan_trip(req, ctx)
    return result.model_dump(mode="json")


def _main_items(itinerary: Itinerary):
    for day in itinerary.days:
        for item in day.schedule:
            if not item.is_backup:
                yield item


def _to_minutes(clock: str | None) -> int | None:
    if not clock or ":" not in clock:
        return None
    hh, mm = clock.split(":", 1)
    try:
        return int(hh) * 60 + int(mm)
    except ValueError:
        return None


def _metric_constraint_satisfaction(case: dict[str, Any], itinerary: Itinerary) -> CheckResult:
    constraints = case.get("constraints", {})
    violations: list[str] = []

    expected_days = constraints.get("days")
    if isinstance(expected_days, int) and expected_days > 0 and len(itinerary.days) != expected_days:
        violations.append(f"days={len(itinerary.days)} expected={expected_days}")

    must_visit = constraints.get("must_visit", [])
    if isinstance(must_visit, list) and must_visit:
        names = {item.poi.name for item in _main_items(itinerary)}
        missing = [name for name in must_visit if name not in names]
        if missing:
            violations.append("missing_must_visit=" + ",".join(missing))

    avoid = constraints.get("avoid", [])
    if isinstance(avoid, list) and avoid:
        names = [item.poi.name for item in _main_items(itinerary)]
        hit = [item for item in avoid if any(item in name for name in names)]
        if hit:
            violations.append("avoid_hit=" + ",".join(hit))

    budget_limit = 0.0
    if isinstance(constraints.get("total_budget"), (int, float)):
        budget_limit = float(constraints["total_budget"])
    elif isinstance(constraints.get("budget_per_day"), (int, float)):
        budget_limit = float(constraints["budget_per_day"]) * max(len(itinerary.days), 1)
    if budget_limit > 0 and itinerary.total_cost > budget_limit and not itinerary.budget_warning:
        violations.append("over_budget_without_warning")

    daily_total_minutes_max = constraints.get("daily_total_minutes_max")
    if isinstance(daily_total_minutes_max, (int, float)) and daily_total_minutes_max > 0:
        for day in itinerary.days:
            main = [item for item in day.schedule if not item.is_backup]
            if not main:
                continue
            start_min = _to_minutes(main[0].start_time)
            end_min = _to_minutes(main[-1].end_time)
            if start_min is None or end_min is None:
                continue
            day_minutes = end_min - start_min
            if day_minutes > float(daily_total_minutes_max):
                violations.append(
                    f"day{day.day_number}_minutes={day_minutes} > {int(daily_total_minutes_max)}"
                )

    return CheckResult(
        name="constraint_satisfaction",
        passed=not violations,
        evidence="ok" if not violations else "; ".join(violations),
    )


def _metric_fact_verifiability(itinerary: Itinerary) -> CheckResult:
    main = list(_main_items(itinerary))
    if not main:
        return CheckResult("fact_verifiability", False, "no main schedule items")
    missing: list[str] = []
    for item in main:
        poi = item.poi
        # Curated POI facts should be fully verifiable.
        if poi.metadata_source:
            if poi.ticket_price < 0:
                missing.append(f"{poi.name}:ticket_price")
            if not poi.open_time:
                missing.append(f"{poi.name}:open_time")
            if not poi.closed_rules:
                missing.append(f"{poi.name}:closed_rules")
            continue

        # Non-curated cities: accept minimum verifiable fields from local mock dataset.
        fallback_ticket = max(poi.ticket_price, poi.cost)
        if fallback_ticket < 0:
            missing.append(f"{poi.name}:ticket_or_cost")
        if not poi.open_time:
            missing.append(f"{poi.name}:open_time")
    return CheckResult(
        name="fact_verifiability",
        passed=not missing,
        evidence="ok" if not missing else "; ".join(missing[:6]),
    )


def _metric_travel_feasibility(itinerary: Itinerary) -> CheckResult:
    violations: list[str] = []
    for day in itinerary.days:
        main = [item for item in day.schedule if not item.is_backup]
        if not day.meal_windows:
            violations.append(f"day{day.day_number}:missing_meal_window")
        for idx, item in enumerate(main):
            if idx > 0 and not (0 < item.travel_minutes < 180):
                violations.append(f"day{day.day_number}:{item.poi.name}:travel={item.travel_minutes}")
            if item.buffer_minutes <= 0:
                violations.append(f"day{day.day_number}:{item.poi.name}:buffer={item.buffer_minutes}")
    return CheckResult(
        name="travel_feasibility",
        passed=not violations,
        evidence="ok" if not violations else "; ".join(violations[:6]),
    )


def _metric_budget_realism(case: dict[str, Any], itinerary: Itinerary) -> CheckResult:
    breakdown = itinerary.budget_breakdown
    tickets = float(breakdown.get("tickets", 0.0))
    transport = float(breakdown.get("local_transport", 0.0))
    food = float(breakdown.get("food_min", 0.0))
    expected_total = round(tickets + transport + food, 2)
    warnings: list[str] = []

    if abs(itinerary.total_cost - expected_total) > 1.0:
        warnings.append(f"sum_mismatch total={itinerary.total_cost} expected={expected_total}")

    travelers = int(case.get("constraints", {}).get("travelers_count") or 2)
    food_floor = 60.0 * travelers * max(len(itinerary.days), 1)
    if food < food_floor:
        warnings.append(f"food_floor_violation actual={food:.0f} expected>={food_floor:.0f}")

    constraints = case.get("constraints", {})
    budget_limit = 0.0
    if isinstance(constraints.get("total_budget"), (int, float)):
        budget_limit = float(constraints["total_budget"])
    elif isinstance(constraints.get("budget_per_day"), (int, float)):
        budget_limit = float(constraints["budget_per_day"]) * max(len(itinerary.days), 1)
    if budget_limit > 0 and budget_limit < itinerary.minimum_feasible_budget and not itinerary.budget_warning:
        warnings.append("missing_budget_warning")

    return CheckResult(
        name="budget_realism",
        passed=not warnings,
        evidence="ok" if not warnings else "; ".join(warnings),
    )


def _metric_duplication_backtracking(itinerary: Itinerary) -> CheckResult:
    ids: list[str] = []
    switches = 0
    for day in itinerary.days:
        main = [item for item in day.schedule if not item.is_backup]
        ids.extend(item.poi.id for item in main)
        clusters = [item.poi.cluster for item in main if item.poi.cluster]
        for idx in range(1, len(clusters)):
            if clusters[idx] != clusters[idx - 1]:
                switches += 1

    duplicate = len(ids) != len(set(ids))
    max_switches = max(2, len(itinerary.days))
    pass_flag = (not duplicate) and switches <= max_switches
    evidence = f"duplicates={duplicate}, cluster_switches={switches}, limit={max_switches}"
    return CheckResult("duplication_backtracking", pass_flag, evidence)


def _metric_structured_output_quality(itinerary: Itinerary) -> CheckResult:
    violations: list[str] = []
    if not itinerary.summary.strip():
        violations.append("missing_summary")
    if not itinerary.days:
        violations.append("missing_days")
    for day in itinerary.days:
        main = [item for item in day.schedule if not item.is_backup]
        if not main:
            violations.append(f"day{day.day_number}:missing_main_schedule")
        for item in main:
            if not item.start_time or not item.end_time:
                violations.append(f"day{day.day_number}:{item.poi.name}:missing_time_range")
            if not item.notes:
                violations.append(f"day{day.day_number}:{item.poi.name}:missing_notes")
    return CheckResult(
        name="structured_output_quality",
        passed=not violations,
        evidence="ok" if not violations else "; ".join(violations[:6]),
    )


def _metric_expected_properties(case: dict[str, Any], itinerary: Itinerary) -> CheckResult:
    expected = case.get("expected_properties", {})
    issues: list[str] = []

    includes = expected.get("includes_pois", [])
    if isinstance(includes, list) and includes:
        names = {item.poi.name for item in _main_items(itinerary)}
        missing = [poi for poi in includes if poi not in names]
        if missing:
            issues.append("missing_pois=" + ",".join(missing))

    if "has_buffer" in expected:
        has_buffer = all(item.buffer_minutes > 0 for item in _main_items(itinerary))
        if has_buffer != bool(expected["has_buffer"]):
            issues.append(f"has_buffer={has_buffer}")

    if "expect_budget_warning" in expected:
        warned = bool(itinerary.budget_warning.strip())
        if warned != bool(expected["expect_budget_warning"]):
            issues.append(f"budget_warning={warned}")

    avoids = expected.get("avoids_pois", [])
    if isinstance(avoids, list) and avoids:
        names = {item.poi.name for item in _main_items(itinerary)}
        hit = [poi for poi in avoids if poi in names]
        if hit:
            issues.append("avoid_hit=" + ",".join(hit))

    if expected.get("has_reservation_reminders") is True:
        main = list(_main_items(itinerary))
        missing = [
            item.poi.name
            for item in main
            if item.poi.requires_reservation and "预约" not in item.notes
        ]
        if missing:
            issues.append("missing_reservation_note=" + ",".join(missing))

    if expected.get("free_only") is True:
        non_free = [item.poi.name for item in _main_items(itinerary) if item.poi.ticket_price > 0]
        if non_free:
            issues.append("non_free=" + ",".join(non_free[:6]))

    if expected.get("has_backups") is True:
        bad_days = [str(day.day_number) for day in itinerary.days if not day.backups]
        if bad_days:
            issues.append("missing_backup_days=" + ",".join(bad_days))

    expected_degrade = expected.get("degrade_level")
    if isinstance(expected_degrade, str) and expected_degrade.strip():
        actual_degrade = itinerary.degrade_level
        if actual_degrade != expected_degrade:
            issues.append(f"degrade_level={actual_degrade} expected={expected_degrade}")

    daily_limit = expected.get("daily_total_minutes_max")
    if isinstance(daily_limit, (int, float)) and daily_limit > 0:
        for day in itinerary.days:
            main = [item for item in day.schedule if not item.is_backup]
            if not main:
                continue
            start_min = _to_minutes(main[0].start_time)
            end_min = _to_minutes(main[-1].end_time)
            if start_min is None or end_min is None:
                continue
            day_minutes = end_min - start_min
            if day_minutes > float(daily_limit):
                issues.append(f"day{day.day_number}_minutes={day_minutes}")

    return CheckResult(
        name="expected_properties_match",
        passed=not issues,
        evidence="ok" if not issues else "; ".join(issues),
    )


def _metric_contract_validity(result: dict[str, Any], itinerary: Itinerary | None) -> CheckResult:
    try:
        parsed = TripResult.model_validate(result)
    except Exception as exc:
        return CheckResult("contract_validity", False, f"trip_result_invalid: {exc}")

    if parsed.status.value == "done" and itinerary is None:
        return CheckResult("contract_validity", False, "done_without_valid_itinerary")
    return CheckResult("contract_validity", True, "ok")


def _metric_clarifying_correctness(target_status: str, actual_status: str) -> CheckResult:
    expects_clarifying = target_status == "clarifying"
    passed = (actual_status == "clarifying") == expects_clarifying
    return CheckResult(
        name="clarifying_correctness",
        passed=passed,
        evidence=f"actual={actual_status}, expected_clarifying={expects_clarifying}",
    )


def _metric_concurrency_isolation(ctx, requests: int = 20) -> dict[str, Any]:
    def _run(idx: int) -> tuple[str, dict[str, Any]]:
        session_id = f"eval_iso_{idx:02d}"
        request = TripRequest(
            message=f"我想去杭州玩2天，出发2026-04-01，返程2026-04-02，请求{idx}",
            session_id=session_id,
            constraints={
                "city": "杭州",
                "days": 2,
                "date_start": "2026-04-01",
                "date_end": "2026-04-02",
            },
        )
        result = plan_trip(request, ctx)
        return session_id, result.model_dump(mode="json")

    with ThreadPoolExecutor(max_workers=requests) as pool:
        rows = list(pool.map(_run, range(requests)))

    expected_ids = {session_id for session_id, _ in rows}
    actual_ids = {result.get("session_id", "") for _, result in rows}
    details: list[str] = []
    if expected_ids != actual_ids:
        details.append("session_id mismatch")

    bad_statuses = [
        result.get("status", "unknown")
        for _, result in rows
        if result.get("status") not in {"done", "clarifying"}
    ]
    if bad_statuses:
        details.append("unexpected statuses: " + ",".join(sorted(set(bad_statuses))))

    exists_fn = getattr(ctx.session_store, "exists", None)
    if callable(exists_fn):
        missing = [session_id for session_id in expected_ids if not exists_fn(session_id)]
        if missing:
            details.append(f"session_store_missing={len(missing)}")

    return {
        "score": 1.0 if not details else 0.0,
        "details": details or ["ok"],
        "requests": requests,
    }


def _run_checks(
    case: dict[str, Any],
    result: dict[str, Any],
    itinerary: Itinerary | None,
) -> list[CheckResult]:
    checks: list[CheckResult] = []
    expected = case.get("expected_properties", {})

    status = str(result.get("status", "unknown"))
    target_status = str(expected.get("status", "done"))
    checks.append(
        CheckResult(
            name="status_match",
            passed=status == target_status,
            evidence=f"actual={status}, expected={target_status}",
        )
    )
    checks.append(_metric_clarifying_correctness(target_status, status))
    checks.append(_metric_contract_validity(result, itinerary))

    if target_status != "done":
        checks.append(
            CheckResult(
                name="schema_requirement",
                passed=itinerary is None,
                evidence="itinerary omitted for non-done status",
            )
        )
        return checks

    checks.append(
        CheckResult(
            name="schema_valid",
            passed=itinerary is not None,
            evidence="itinerary parsed by app.domain.models.Itinerary" if itinerary else "no itinerary parsed",
        )
    )
    if itinerary is None:
        return checks

    checks.append(_metric_constraint_satisfaction(case, itinerary))
    checks.append(_metric_fact_verifiability(itinerary))
    checks.append(_metric_travel_feasibility(itinerary))
    checks.append(_metric_budget_realism(case, itinerary))
    checks.append(_metric_duplication_backtracking(itinerary))
    checks.append(_metric_structured_output_quality(itinerary))
    checks.append(_metric_expected_properties(case, itinerary))

    return checks


def _case_to_report_row(
    case: dict[str, Any],
    checks: list[CheckResult],
    schema_errors: list[str] | None = None,
) -> dict[str, Any]:
    schema_errors = schema_errors or []
    passed = sum(1 for check in checks if check.passed)
    total = len(checks)
    score = round(passed / total, 4) if total else 0.0
    status = "PASS" if score >= 0.85 else ("WARN" if score >= 0.6 else "FAIL")
    return {
        "id": case.get("id", ""),
        "user_request": case.get("user_request", ""),
        "score": score,
        "status": status,
        "schema_errors": schema_errors,
        "checks": [
            {"name": check.name, "passed": check.passed, "evidence": check.evidence}
            for check in checks
        ],
    }


def _build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Eval Report")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at']}")
    lines.append(f"- Cases: {report['summary']['total_cases']}")
    lines.append(f"- Pass: {report['summary']['passed_cases']}")
    lines.append(f"- Average score: {report['summary']['average_score']:.2f}")
    lines.append(f"- Pass rate: {report['summary']['pass_rate']:.0%}")
    concurrency = report["summary"].get("concurrency_isolation", {})
    if concurrency:
        lines.append(
            "- Concurrency isolation: "
            f"{concurrency.get('score', 0.0):.2f} "
            f"({'; '.join(concurrency.get('details', []))})"
        )
    lines.append("")
    metrics = report["summary"].get("metric_pass_rates", {})
    if metrics:
        lines.append("## Metric Pass Rates")
        lines.append("")
        lines.append("| Metric | Pass Rate |")
        lines.append("| --- | --- |")
        for name, value in metrics.items():
            lines.append(f"| {name} | {value:.0%} |")
        lines.append("")

    lines.append("## Case Summary")
    lines.append("")
    lines.append("| Case ID | Status | Score |")
    lines.append("| --- | --- | --- |")
    for row in report["cases"]:
        lines.append(f"| {row['id']} | {row['status']} | {row['score']:.2f} |")

    lines.append("")
    lines.append("## Failed Checks")
    lines.append("")
    has_failure = False
    for row in report["cases"]:
        failed = [check for check in row["checks"] if not check["passed"]]
        if row["schema_errors"]:
            has_failure = True
            lines.append(f"- `{row['id']}` schema_errors: {', '.join(row['schema_errors'])}")
        for check in failed:
            has_failure = True
            lines.append(f"- `{row['id']}` {check['name']}: {check['evidence']}")
    if not has_failure:
        lines.append("- none")
    lines.append("")

    lines.append("## Top Failure Modes")
    lines.append("")
    modes = report["summary"].get("top_failure_modes", [])
    if modes:
        for mode in modes:
            lines.append(f"- {mode['check']}: {mode['count']}")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Priority Suggestions")
    lines.append("")
    suggestions = report["summary"].get("priority_suggestions", [])
    if suggestions:
        for idx, item in enumerate(suggestions, start=1):
            lines.append(f"{idx}. {item}")
    else:
        lines.append("1. No blocking issues in current case set.")
    lines.append("")
    return "\n".join(lines)


def _save_report(report: dict[str, Any], out_dir: Path, tag: str) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    tagged_json = out_dir / f"{tag}_report.json"
    tagged_md = out_dir / f"{tag}_report.md"
    latest_json = out_dir / "latest_report.json"
    latest_md = out_dir / "latest_report.md"

    tagged_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    tagged_md.write_text(_build_markdown(report), encoding="utf-8")
    latest_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_md.write_text(_build_markdown(report), encoding="utf-8")
    return tagged_json, tagged_md


def _compute_metric_pass_rates(rows: list[dict[str, Any]]) -> dict[str, float]:
    total: dict[str, int] = {}
    passed: dict[str, int] = {}
    for row in rows:
        for check in row.get("checks", []):
            name = str(check.get("name", "unknown"))
            total[name] = total.get(name, 0) + 1
            if bool(check.get("passed")):
                passed[name] = passed.get(name, 0) + 1
    rates: dict[str, float] = {}
    for name, count in sorted(total.items()):
        rates[name] = (passed.get(name, 0) / count) if count else 0.0
    return rates


def _top_failure_modes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for row in rows:
        for check in row.get("checks", []):
            if not check.get("passed"):
                counter[str(check.get("name", "unknown"))] += 1
    return [{"check": name, "count": count} for name, count in counter.most_common(5)]


def _priority_suggestions(modes: list[dict[str, Any]]) -> list[str]:
    mapping = {
        "constraint_satisfaction": "优先补齐约束解析与硬约束执行（days/budget/must_visit/avoid）。",
        "fact_verifiability": "优先扩展多城市POI元数据并在输出中保留数据来源字段。",
        "travel_feasibility": "优先增强交通时长、排队缓冲和日程可行性检查。",
        "budget_realism": "优先修复预算解析和最低可行预算提示逻辑。",
        "duplication_backtracking": "优先加强地理聚类与去重，减少跨区折返。",
        "structured_output_quality": "优先强制输出schema字段完整（时间段、预算拆分、备选）。",
        "expected_properties_match": "优先检查case预期字段与产品行为的一致性。",
        "schema_valid": "优先修复final_itinerary结构化输出链路。",
        "status_match": "优先修复clarify/planning分流逻辑。",
    }
    suggestions: list[str] = []
    for item in modes:
        check = item.get("check", "")
        if check in mapping and mapping[check] not in suggestions:
            suggestions.append(mapping[check])
    return suggestions[:3]


def run(cases_path: Path, out_dir: Path, tag: str) -> dict[str, Any]:
    os.environ.setdefault("ROUTING_PROVIDER", "fixture")

    cases = _load_cases(cases_path)
    ctx = make_app_context()
    rows: list[dict[str, Any]] = []
    for case in cases:
        schema_errors = _validate_case_schema(case)
        if schema_errors:
            row = _case_to_report_row(case, checks=[], schema_errors=schema_errors)
            rows.append(row)
            continue

        result = _invoke_graph(case, ctx)
        itinerary: Itinerary | None = None
        if result.get("status") == "done" and result.get("itinerary"):
            try:
                itinerary = Itinerary.model_validate(result["itinerary"])
            except Exception:
                itinerary = None
        checks = _run_checks(case, result, itinerary)
        rows.append(_case_to_report_row(case, checks=checks))

    total_cases = len(rows)
    passed_cases = sum(1 for row in rows if row["status"] == "PASS")
    avg_score = round(sum(row["score"] for row in rows) / total_cases, 4) if rows else 0.0
    pass_rate = round((passed_cases / total_cases), 4) if total_cases else 0.0
    metric_pass_rates = _compute_metric_pass_rates(rows)
    modes = _top_failure_modes(rows)
    concurrency = _metric_concurrency_isolation(ctx, requests=20)
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "cases_file": str(cases_path),
        "summary": {
            "total_cases": total_cases,
            "passed_cases": passed_cases,
            "average_score": avg_score,
            "pass_rate": pass_rate,
            "metric_pass_rates": metric_pass_rates,
            "concurrency_isolation": concurrency,
            "top_failure_modes": modes,
            "priority_suggestions": _priority_suggestions(modes),
        },
        "cases": rows,
    }

    json_path, md_path = _save_report(report, out_dir, tag)
    print(f"saved: {json_path}")
    print(f"saved: {md_path}")
    print(
        "summary: "
        f"passed={passed_cases}/{total_cases}, avg_score={avg_score:.2f}, "
        f"concurrency={concurrency['score']:.2f}"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run structured eval cases for trip-agent")
    parser.add_argument("--cases", default="eval/cases.json", help="Path to eval cases JSON")
    parser.add_argument("--out", default="eval/reports", help="Output report directory")
    parser.add_argument("--tag", default="baseline", help="Report tag prefix")
    args = parser.parse_args()
    run(Path(args.cases), Path(args.out), args.tag)


if __name__ == "__main__":
    main()
