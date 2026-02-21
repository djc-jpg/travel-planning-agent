"""Eval runner with scoring, regression checks, and persisted reports."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app.application.context import make_app_context
from app.application.contracts import TripRequest, TripResult
from app.application.plan_trip import plan_trip
from app.domain.models import Itinerary
from app.security.redact import redact_sensitive

_EVAL_OUTPUT_DIR = Path(__file__).parent / "reports"


def _load_cases() -> list[dict]:
    case_file = Path(__file__).parent / "cases.json"
    with open(case_file, encoding="utf-8") as fh:
        return json.load(fh)


def run_request(message: str, ctx=None) -> dict[str, Any]:
    active_ctx = ctx or make_app_context()
    result = plan_trip(TripRequest(message=message), active_ctx)
    return result.model_dump(mode="json")


def _score_concurrency_isolation(ctx, requests: int = 20) -> dict[str, Any]:
    details: list[str] = []

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
        return session_id, plan_trip(request, ctx).model_dump(mode="json")

    with ThreadPoolExecutor(max_workers=requests) as pool:
        rows = list(pool.map(_run, range(requests)))

    expected = {session_id for session_id, _ in rows}
    actual = {row.get("session_id", "") for _, row in rows}
    if expected != actual:
        details.append("session_id mismatch across concurrent requests")

    unexpected_status = [
        row.get("status", "unknown")
        for _, row in rows
        if row.get("status") not in {"done", "clarifying"}
    ]
    if unexpected_status:
        details.append("unexpected statuses: " + ",".join(sorted(set(unexpected_status))))

    exists_fn = getattr(ctx.session_store, "exists", None)
    if callable(exists_fn):
        missing = [session_id for session_id in expected if not exists_fn(session_id)]
        if missing:
            details.append(f"session store missing keys: {len(missing)}")

    score = 1.0 if not details else 0.0
    return {
        "score": score,
        "details": details or ["ok"],
        "requests": requests,
    }


def _score_case(case: dict, result: dict) -> dict[str, Any]:
    expect = case.get("expect", {})
    scores: dict[str, float] = {}
    details: list[str] = []
    status = result.get("status", "unknown")

    try:
        parsed = TripResult.model_validate(result)
        scores["contract_validity"] = 1.0
    except Exception as exc:
        parsed = None
        scores["contract_validity"] = 0.0
        details.append(f"contract validation failed: {redact_sensitive(str(exc))}")

    expects_clarifying = expect.get("status") == "clarifying"
    scores["clarifying_correctness"] = 1.0 if ((status == "clarifying") == expects_clarifying) else 0.0

    if expects_clarifying:
        scores["status_match"] = 1.0 if status == "clarifying" else 0.0
        return {
            "scores": scores,
            "details": details,
            "total": sum(scores.values()) / max(len(scores), 1),
        }

    final = result.get("itinerary")
    if final:
        try:
            itinerary = Itinerary.model_validate(final)
            scores["schema_valid"] = 1.0
        except Exception as exc:  # pragma: no cover - defensive
            itinerary = None
            scores["schema_valid"] = 0.0
            details.append(f"schema validation failed: {redact_sensitive(str(exc))}")
    else:
        itinerary = None
        scores["schema_valid"] = 0.0
        if status == "clarifying":
            details.append("entered clarifying state and no itinerary generated")

    if itinerary is None:
        scores.setdefault("days_match", 0.0)
        scores.setdefault("budget_ok", 0.5)
        scores.setdefault("theme_hit", 0.0)
        scores.setdefault("travel_time", 0.5)
        if parsed is not None and status == "done":
            scores["contract_validity"] = 0.0
            details.append("done status without itinerary")
        total = sum(scores.values()) / max(len(scores), 1)
        return {"scores": scores, "details": details, "total": total}

    expected_days = expect.get("days")
    if expected_days:
        scores["days_match"] = 1.0 if len(itinerary.days) == expected_days else 0.0
    else:
        scores["days_match"] = 1.0

    budget_per_day = expect.get("budget_per_day")
    if budget_per_day and itinerary.total_cost > 0:
        total_budget = budget_per_day * len(itinerary.days)
        if itinerary.total_cost <= total_budget:
            scores["budget_ok"] = 1.0
        elif itinerary.total_cost <= total_budget * 1.2:
            scores["budget_ok"] = 0.5
        else:
            scores["budget_ok"] = 0.0
            details.append(f"over budget: {itinerary.total_cost:.0f} > {total_budget:.0f}")
    else:
        scores["budget_ok"] = 1.0

    expected_themes = set(expect.get("themes", []))
    if expected_themes:
        found_themes: set[str] = set()
        for day in itinerary.days:
            for item in day.schedule:
                found_themes.update(item.poi.themes)
        scores["theme_hit"] = len(found_themes & expected_themes) / len(expected_themes)
    else:
        scores["theme_hit"] = 1.0

    if itinerary.days:
        avg_travel = sum(day.total_travel_minutes for day in itinerary.days) / len(itinerary.days)
        if avg_travel <= 120:
            scores["travel_time"] = 1.0
        elif avg_travel <= 180:
            scores["travel_time"] = 0.5
        else:
            scores["travel_time"] = 0.0
            details.append(f"travel time too high: {avg_travel:.0f} minutes/day")
    else:
        scores["travel_time"] = 0.0

    total = sum(scores.values()) / max(len(scores), 1)
    return {"scores": scores, "details": details, "total": total}


def run_eval():
    cases = _load_cases()
    ctx = make_app_context()

    print("=" * 60)
    print("trip-agent eval report")
    print(f"time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    results: list[dict[str, Any]] = []
    total_score = 0.0

    for case in cases:
        case_id = case["id"]
        name = case["name"]

        start = time.time()
        try:
            result = run_request(case["input"], ctx=ctx)
            elapsed = time.time() - start
            score_info = _score_case(case, result)
        except Exception as exc:
            elapsed = time.time() - start
            score_info = {
                "scores": {"error": 0.0},
                "details": [f"exception: {redact_sensitive(str(exc))}"],
                "total": 0.0,
            }

        total_score += score_info["total"]
        results.append(
            {
                "case_id": case_id,
                "name": name,
                "elapsed": round(elapsed, 2),
                **score_info,
            }
        )

        status_icon = "PASS" if score_info["total"] >= 0.8 else (
            "WARN" if score_info["total"] >= 0.5 else "FAIL"
        )
        print(f"\n{status_icon} [{case_id}] {name}")
        print(f"  score: {score_info['total']:.2f} | elapsed: {elapsed:.2f}s")
        for key, value in score_info["scores"].items():
            print(f"    {key}: {value:.2f}")
        for detail in score_info.get("details", []):
            print(f"    ! {detail}")

    avg = total_score / len(cases) if cases else 0.0
    passed = sum(1 for row in results if row["total"] >= 0.8)
    pass_rate = (passed / len(cases)) if cases else 0.0
    concurrency_metric = _score_concurrency_isolation(ctx, requests=20)

    print("\n" + "=" * 60)
    print(f"average: {avg:.2f} ({len(cases)} cases)")
    print(f"pass rate: {passed}/{len(cases)} ({pass_rate * 100:.0f}%)")
    print(
        "concurrency_isolation: "
        f"{concurrency_metric['score']:.2f} ({'; '.join(concurrency_metric['details'])})"
    )
    print("=" * 60)

    regressions = _check_regression(results)
    if regressions:
        print("\nWARNING: regression detected")
        for item in regressions:
            print(f"  {item}")

    report = {
        "timestamp": datetime.now().isoformat(),
        "average_score": round(avg, 4),
        "pass_rate": round(pass_rate, 4),
        "total_cases": len(cases),
        "passed": passed,
        "results": results,
        "regressions": regressions,
        "extra_metrics": {
            "concurrency_isolation": concurrency_metric,
        },
    }
    _save_report(report)
    return results


def _check_regression(results: list[dict]) -> list[str]:
    last_report = _load_last_report()
    if last_report is None:
        return []

    previous = {row["case_id"]: row.get("total", 0.0) for row in last_report.get("results", [])}
    regressions: list[str] = []
    for row in results:
        case_id = row["case_id"]
        if case_id not in previous:
            continue
        delta = row.get("total", 0.0) - previous[case_id]
        if delta < -0.1:
            regressions.append(
                f"[{case_id}] {row.get('name', '')} score dropped: "
                f"{previous[case_id]:.2f} -> {row.get('total', 0.0):.2f} (delta={delta:+.2f})"
            )
    return regressions


def _save_report(report: dict) -> None:
    _EVAL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path = _EVAL_OUTPUT_DIR / filename

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2, default=str)

    latest_path = _EVAL_OUTPUT_DIR / "latest.json"
    with open(latest_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2, default=str)

    print(f"\nReport saved: {path}")


def _load_last_report() -> dict | None:
    latest_path = _EVAL_OUTPUT_DIR / "latest.json"
    if not latest_path.exists():
        return None

    try:
        with open(latest_path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # pragma: no cover - defensive
        return None


if __name__ == "__main__":
    run_eval()
