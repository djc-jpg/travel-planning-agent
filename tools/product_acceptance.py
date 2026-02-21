"""Product acceptance runner for smoke/full release checks."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Any

from app.application.context import make_app_context
from app.services.plan_service import execute_plan

_DEBUG_KEYS = {
    "unknown_fields",
    "trace_id",
    "violations",
    "repair_actions",
    "verified_fact_ratio",
    "routing_source",
    "fallback_count",
    "confidence_breakdown",
    "confidence_score",
    "degrade_level",
}


def _run_smoke_case() -> dict[str, Any]:
    ctx = make_app_context()
    result = execute_plan(
        ctx=ctx,
        message="北京3天旅行",
        constraints={
            "city": "北京",
            "days": 3,
            "date_start": "2026-03-12",
            "date_end": "2026-03-14",
            "budget_per_day": 500,
        },
        user_profile={"travelers_type": "couple", "themes": ["历史古迹"]},
        metadata={
            "source": "product_acceptance_cli",
            "field_sources": {
                "city": "user_form",
                "days": "user_form",
                "date_start": "user_form",
                "date_end": "user_form",
            },
        },
        debug=False,
    )
    itinerary = result.itinerary or {}
    hidden_debug_ok = not any(key in itinerary for key in _DEBUG_KEYS)
    days = itinerary.get("days", [])
    return {
        "status": result.status.value,
        "message_has_machine_pattern": "executable itinerary" in str(result.message).lower(),
        "hidden_debug_ok": hidden_debug_ok,
        "day_count": len(days),
        "first_day_date": days[0].get("date") if days else None,
        "run_fingerprint": (
            result.run_fingerprint.model_dump(mode="json")
            if result.run_fingerprint is not None
            else None
        ),
    }


def _run_python_module(module_name: str) -> dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, "-m", module_name],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "module": module_name,
        "returncode": proc.returncode,
        "stdout_tail": "\n".join(proc.stdout.splitlines()[-20:]),
        "stderr_tail": "\n".join(proc.stderr.splitlines()[-20:]),
    }


def _smoke_passed(smoke: dict[str, Any]) -> bool:
    run_fp = smoke.get("run_fingerprint") or {}
    run_mode = str(run_fp.get("run_mode", ""))
    route_provider = str(run_fp.get("route_provider", ""))
    return (
        smoke.get("status") == "done"
        and smoke.get("hidden_debug_ok") is True
        and smoke.get("day_count") == 3
        and smoke.get("message_has_machine_pattern") is False
        and bool(run_mode)
        and bool(route_provider)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run product acceptance checks.")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Also run full eval and release gate.",
    )
    args = parser.parse_args()

    smoke = _run_smoke_case()
    report: dict[str, Any] = {
        "smoke": smoke,
        "smoke_passed": _smoke_passed(smoke),
    }
    if args.full:
        eval_report = _run_python_module("app.eval.run_eval")
        gate_report = _run_python_module("eval.release_gate_runner")
        report["eval"] = eval_report
        report["release_gate"] = gate_report
        report["full_passed"] = (
            report["smoke_passed"]
            and eval_report["returncode"] == 0
            and gate_report["returncode"] == 0
        )

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.full:
        return 0 if report.get("full_passed") else 1
    return 0 if report.get("smoke_passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())

