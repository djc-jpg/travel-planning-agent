"""Release gate runner with hard CI blocking thresholds."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import time
from typing import Any
import uuid

from app.application.context import make_app_context
from app.application.contracts import TripRequest
from app.application.plan_trip import plan_trip
from app.domain.models import Itinerary
from app.domain.planning.day_template import infer_poi_activity_bucket
from eval.run import _metric_constraint_satisfaction, _metric_travel_feasibility

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CONFIG = _ROOT / "eval" / "release_gate.json"
_DEFAULT_CASES = _ROOT / "eval" / "cases.json"
_DEFAULT_DEGRADE_CASES = _ROOT / "eval" / "release_levels_cases.json"
_REPORT_DIR = _ROOT / "eval" / "reports"
_FACT_FIELDS_PER_ITEM = 4
_DEGRADE_LEVELS = ("L0", "L1", "L2", "L3")
_DEFAULT_L0_TARGET_RATIO = 0.30
_INFRASTRUCTURE_NAME_KEYWORDS = (
    "parking",
    "garage",
    "pickup",
    "dropoff",
    "pick-up",
    "drop-off",
    "station",
    "terminal",
    "transfer",
    "shuttle",
    "停车场",
    "停车库",
    "车库",
    "上车点",
    "下车点",
    "上客点",
    "下客点",
    "候车点",
    "落客区",
    "接驳",
    "换乘",
    "网约车",
    "地铁站",
    "公交站",
)
_FOOD_NIGHT_CASE_TOKENS = (
    "food",
    "night",
    "美食",
    "夜市",
    "夜景",
)
_HARD_GATE_THRESHOLDS = {
    "l0_real_routing_ratio": ">=0.30",
    "fallback_rate": "<=0.10",
    "verified_fact_ratio": ">=0.60",
    "routing_fixture_rate": "<=0.70",
    "infrastructure_poi_rate": "==0.0",
    "business_poi_leak_rate": "==0.0",
    "food_night_coverage_rate": ">=0.90",
    "avoid_constraint_pass_rate": ">=1.00",
    "edit_roundtrip_pass_rate": ">=1.00",
}
_NON_EXPERIENCE_BUSINESS_NAME_KEYWORDS = (
    "营业厅",
    "营业部",
    "售票处",
    "售票点",
    "服务中心",
    "客服中心",
    "造型",
    "理发",
    "发艺",
    "银行",
    "网点",
    "联通",
    "移动",
    "电信",
    "ticket office",
    "business hall",
    "service center",
    "hair salon",
    "telecom",
    "bank branch",
)


def _load_json(path: Path) -> Any:
    with open(path, encoding="utf-8-sig") as fh:
        return json.load(fh)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1))
    return ordered[idx]


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    safe_ratio = max(0.0, min(1.0, ratio))
    idx = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * safe_ratio) - 1))
    return ordered[idx]


def _match_threshold(actual: float, expected: Any) -> bool:
    if isinstance(expected, (int, float)):
        return abs(actual - float(expected)) < 1e-9
    if not isinstance(expected, str):
        return False

    text = expected.strip().replace(" ", "")
    for op in ("<=", ">=", "==", "<", ">"):
        if not text.startswith(op):
            continue
        try:
            target = float(text[len(op):])
        except ValueError:
            return False
        if op == "<=":
            return actual <= target
        if op == ">=":
            return actual >= target
        if op == "==":
            return abs(actual - target) < 1e-9
        if op == "<":
            return actual < target
        if op == ">":
            return actual > target
    return False


@contextmanager
def _env_overrides(values: dict[str, str]) -> Any:
    original: dict[str, str | None] = {}
    try:
        for key, value in values.items():
            original[key] = os.getenv(key)
            os.environ[key] = value
        yield
    finally:
        for key, previous in original.items():
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous


def _main_items_count(itinerary: Itinerary) -> int:
    return sum(
        1
        for day in itinerary.days
        for item in day.schedule
        if not item.is_backup
    )


def _main_items(itinerary: Itinerary) -> list[Any]:
    return [
        item
        for day in itinerary.days
        for item in day.schedule
        if not item.is_backup
    ]


def _is_infrastructure_stop(item: Any) -> bool:
    poi = getattr(item, "poi", None)
    if poi is None:
        return False
    semantic = str(getattr(poi, "semantic_type", "")).lower()
    if semantic.endswith("infrastructure"):
        return True
    name = str(getattr(poi, "name", "")).lower()
    return any(token in name for token in _INFRASTRUCTURE_NAME_KEYWORDS)


def _is_non_experience_business_stop(item: Any) -> bool:
    poi = getattr(item, "poi", None)
    if poi is None:
        return False
    semantic = str(getattr(poi, "semantic_type", "")).lower()
    if semantic.endswith("experience"):
        return False
    if semantic.endswith("infrastructure"):
        return False
    name = str(getattr(poi, "name", "")).lower()
    return any(token in name for token in _NON_EXPERIENCE_BUSINESS_NAME_KEYWORDS)


def _requires_food_night_case(case: dict[str, Any]) -> bool:
    case_id = str(case.get("id", "")).lower()
    request = str(case.get("user_request", "")).lower()
    payload = f"{case_id} {request}"
    return any(token in payload for token in _FOOD_NIGHT_CASE_TOKENS)


def _has_food_night_stop(itinerary: Itinerary) -> bool:
    for item in _main_items(itinerary):
        bucket = infer_poi_activity_bucket(item.poi)
        if bucket in {"food", "night"}:
            return True
    return False


def _avoid_constraint_pass(case: dict[str, Any], itinerary: Itinerary) -> tuple[bool, bool]:
    constraints = case.get("constraints", {})
    if not isinstance(constraints, dict):
        return True, False
    avoids = [str(term).strip().lower() for term in constraints.get("avoid", []) if str(term).strip()]
    if not avoids:
        return True, False
    names = [str(item.poi.name).lower() for item in _main_items(itinerary)]
    hit = any(any(term in name for name in names) for term in avoids)
    return (not hit), True


def _clamp_unit(value: Any, *, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if parsed < 0.0:
        return 0.0
    if parsed > 1.0:
        return 1.0
    return parsed


def _extract_routing_source(itinerary_payload: dict[str, Any], *, degrade_level: str) -> str:
    source = str(itinerary_payload.get("routing_source", "")).strip().lower()
    if source:
        return source
    if degrade_level == "L0":
        return "real"
    if degrade_level == "L1":
        return "fixture"
    return "unknown"


def _extract_verified_ratio(
    itinerary_payload: dict[str, Any],
    *,
    main_items: int,
    unknown_fields_count: int,
) -> float:
    raw = itinerary_payload.get("verified_fact_ratio")
    if raw is not None:
        return _clamp_unit(raw, default=0.0)
    slots = main_items * _FACT_FIELDS_PER_ITEM
    if slots <= 0:
        return 0.0
    return _clamp_unit(1.0 - (unknown_fields_count / slots), default=0.0)


def _extract_fallback_count(
    itinerary_payload: dict[str, Any],
    *,
    itinerary_obj: Itinerary,
    routing_source: str,
) -> int:
    explicit = itinerary_payload.get("fallback_count")
    if explicit is not None:
        try:
            return max(0, int(explicit))
        except (TypeError, ValueError):
            pass

    note_hits = 0
    for day in itinerary_obj.days:
        for item in day.schedule:
            if item.is_backup:
                continue
            if "fallback" in str(item.notes or "").lower():
                note_hits += 1
    if note_hits > 0:
        return note_hits
    return 1 if "fallback" in routing_source else 0


def _clamp_ratio(value: Any, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, parsed))


def _l0_target_count(cases: list[dict[str, Any]]) -> int:
    done_cases = 0
    for case in cases:
        expected = case.get("expected_properties", {})
        if str(expected.get("status", "done")) == "done":
            done_cases += 1
    if done_cases <= 0:
        return 0

    ratio = _clamp_ratio(os.getenv("RELEASE_GATE_L0_TARGET_RATIO"), default=_DEFAULT_L0_TARGET_RATIO)
    return max(1, math.ceil(done_cases * ratio))


def _case_routing_mode(
    case: dict[str, Any],
    *,
    expected_status: str,
    l0_slots_used: int,
    l0_slots_target: int,
) -> str:
    explicit = str(case.get("routing_provider", "")).strip().lower()
    if explicit in {"real", "fixture", "auto"}:
        return explicit
    if expected_status != "done":
        return "fixture"
    if l0_slots_used < l0_slots_target:
        return "real"
    return "fixture"


def _evaluate_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    latencies: list[float] = []
    confidence_scores: list[float] = []

    total_cases = len(cases)
    schema_valid_ok = 0
    clarifying_ok = 0
    constraint_ok = 0
    constraint_total = 0
    travel_ok = 0
    travel_total = 0
    success_ok = 0
    unknown_count = 0
    unknown_total = 0
    routing_total = 0
    routing_real = 0
    routing_fixture = 0
    fallback_events = 0
    fallback_total = 0
    verified_weighted_sum = 0.0
    verified_weighted_total = 0
    infrastructure_hits = 0
    infrastructure_total = 0
    business_poi_leak_hits = 0
    business_poi_leak_total = 0
    food_night_cases = 0
    food_night_hits = 0
    avoid_cases = 0
    avoid_pass_cases = 0
    l0_slots_target = _l0_target_count(cases)
    l0_slots_used = 0
    seen_degrade: set[str] = set()

    for case in cases:
        expected = case.get("expected_properties", {})
        expected_status = str(expected.get("status", "done"))
        routing_mode = _case_routing_mode(
            case,
            expected_status=expected_status,
            l0_slots_used=l0_slots_used,
            l0_slots_target=l0_slots_target,
        )
        if routing_mode == "real" and expected_status == "done":
            l0_slots_used += 1

        started = time.perf_counter()
        with _env_overrides({"ROUTING_PROVIDER": routing_mode}):
            result = plan_trip(
                TripRequest(
                    message=str(case.get("user_request", "")),
                    constraints=dict(case.get("constraints", {})),
                    metadata={"context": dict(case.get("context", {}))},
                ),
                make_app_context(),
            )
        latency_ms = (time.perf_counter() - started) * 1000.0
        latencies.append(latency_ms)

        status = result.status.value
        confidence_score_raw = getattr(result, "confidence_score", None)
        confidence_score_case = (
            float(confidence_score_raw)
            if isinstance(confidence_score_raw, (int, float))
            else None
        )
        if confidence_score_case is not None:
            confidence_scores.append(confidence_score_case)
        clarifying_expected = expected_status == "clarifying"
        clarifying_actual = status == "clarifying"
        clarifying_pass = clarifying_expected == clarifying_actual
        if clarifying_pass:
            clarifying_ok += 1

        success = status in {"done", "clarifying"}
        if success:
            success_ok += 1

        schema_valid = False
        constraint_pass: bool | None = None
        travel_pass: bool | None = None
        unknown_ratio_case = 0.0
        verified_ratio_case = 0.0
        routing_source = "unknown"
        fallback_count = 0
        degrade_level = result.degrade_level or "L3"

        itinerary_obj: Itinerary | None = None
        itinerary_payload = result.itinerary if isinstance(result.itinerary, dict) else {}
        if status == "done" and result.itinerary:
            try:
                itinerary_obj = Itinerary.model_validate(result.itinerary)
                schema_valid = True
                schema_valid_ok += 1
            except Exception:
                schema_valid = False

        if itinerary_obj is not None:
            constraint_total += 1
            constraint_check = _metric_constraint_satisfaction(case, itinerary_obj)
            constraint_pass = bool(constraint_check.passed)
            if constraint_pass:
                constraint_ok += 1

            travel_total += 1
            travel_check = _metric_travel_feasibility(itinerary_obj)
            travel_pass = bool(travel_check.passed)
            if travel_pass:
                travel_ok += 1

            main_items_count = _main_items_count(itinerary_obj)
            unknown_fields = list(itinerary_obj.unknown_fields)
            unknown_count += len(unknown_fields)
            fact_slots = main_items_count * _FACT_FIELDS_PER_ITEM
            unknown_total += fact_slots
            unknown_ratio_case = (
                len(unknown_fields) / fact_slots
                if fact_slots > 0
                else 0.0
            )
            verified_ratio_case = _extract_verified_ratio(
                itinerary_payload,
                main_items=main_items_count,
                unknown_fields_count=len(unknown_fields),
            )
            routing_source = _extract_routing_source(
                itinerary_payload,
                degrade_level=degrade_level,
            )
            fallback_count = _extract_fallback_count(
                itinerary_payload,
                itinerary_obj=itinerary_obj,
                routing_source=routing_source,
            )

            main_schedule = _main_items(itinerary_obj)
            infrastructure_total += len(main_schedule)
            infrastructure_hits += sum(1 for item in main_schedule if _is_infrastructure_stop(item))
            business_poi_leak_total += len(main_schedule)
            business_poi_leak_hits += sum(
                1 for item in main_schedule if _is_non_experience_business_stop(item)
            )
            if _requires_food_night_case(case):
                food_night_cases += 1
                if _has_food_night_stop(itinerary_obj):
                    food_night_hits += 1
            avoid_pass, avoid_enabled = _avoid_constraint_pass(case, itinerary_obj)
            if avoid_enabled:
                avoid_cases += 1
                if avoid_pass:
                    avoid_pass_cases += 1

            if main_items_count > 0:
                routing_total += 1
                if routing_source == "real":
                    routing_real += 1
                if "fixture" in routing_source:
                    routing_fixture += 1
                fallback_events += fallback_count
                fallback_total += main_items_count
                verified_weighted_sum += verified_ratio_case * fact_slots
                verified_weighted_total += fact_slots

            degrade_level = itinerary_obj.degrade_level or degrade_level

        seen_degrade.add(degrade_level)
        rows.append(
            {
                "id": case.get("id", ""),
                "status": status,
                "expected_status": expected_status,
                "clarifying_pass": clarifying_pass,
                "schema_valid": schema_valid,
                "constraint_pass": constraint_pass,
                "travel_pass": travel_pass,
                "unknown_ratio_case": round(unknown_ratio_case, 4),
                "verified_fact_ratio_case": round(verified_ratio_case, 4),
                "routing_source": routing_source,
                "fallback_count": fallback_count,
                "routing_mode_case": routing_mode,
                "degrade_level": degrade_level,
                "confidence_score_case": (
                    round(confidence_score_case, 4) if confidence_score_case is not None else None
                ),
                "latency_ms": round(latency_ms, 2),
                "request_id": result.request_id,
                "trace_id": result.trace_id,
            }
        )

    schema_valid_rate = (schema_valid_ok / max(constraint_total, 1)) if constraint_total else 1.0
    clarifying_correctness = clarifying_ok / max(total_cases, 1)
    constraint_rate = (constraint_ok / max(constraint_total, 1)) if constraint_total else 1.0
    travel_rate = (travel_ok / max(travel_total, 1)) if travel_total else 1.0
    success_rate = success_ok / max(total_cases, 1)
    unknown_fact_rate = (unknown_count / unknown_total) if unknown_total else 0.0
    l0_real_routing_ratio = (routing_real / routing_total) if routing_total else 0.0
    routing_fixture_rate = (routing_fixture / routing_total) if routing_total else 0.0
    fallback_rate = (fallback_events / fallback_total) if fallback_total else 0.0
    verified_fact_ratio = (
        (verified_weighted_sum / verified_weighted_total)
        if verified_weighted_total
        else 0.0
    )
    infrastructure_poi_rate = (
        (infrastructure_hits / infrastructure_total)
        if infrastructure_total
        else 0.0
    )
    business_poi_leak_rate = (
        (business_poi_leak_hits / business_poi_leak_total)
        if business_poi_leak_total
        else 0.0
    )
    food_night_coverage_rate = (
        (food_night_hits / food_night_cases)
        if food_night_cases
        else 1.0
    )
    avoid_constraint_pass_rate = (
        (avoid_pass_cases / avoid_cases)
        if avoid_cases
        else 1.0
    )
    confidence_samples = len(confidence_scores)
    confidence_mean = (
        (sum(confidence_scores) / confidence_samples)
        if confidence_samples
        else 0.0
    )
    confidence_p50 = _percentile(confidence_scores, 0.5) if confidence_samples else 0.0
    confidence_p90 = _percentile(confidence_scores, 0.9) if confidence_samples else 0.0

    return {
        "rows": rows,
        "latencies_ms": latencies,
        "metrics": {
            "schema_valid_rate": round(schema_valid_rate, 4),
            "clarifying_correctness": round(clarifying_correctness, 4),
            "constraint_satisfaction_rate": round(constraint_rate, 4),
            "travel_feasibility_rate": round(travel_rate, 4),
            "plan_success_rate": round(success_rate, 4),
            "unknown_fact_rate": round(unknown_fact_rate, 4),
            "l0_real_routing_ratio": round(l0_real_routing_ratio, 4),
            "fallback_rate": round(fallback_rate, 4),
            "verified_fact_ratio": round(verified_fact_ratio, 4),
            "routing_fixture_rate": round(routing_fixture_rate, 4),
            "infrastructure_poi_rate": round(infrastructure_poi_rate, 4),
            "business_poi_leak_rate": round(business_poi_leak_rate, 4),
            "food_night_coverage_rate": round(food_night_coverage_rate, 4),
            "avoid_constraint_pass_rate": round(avoid_constraint_pass_rate, 4),
            "confidence_samples": confidence_samples,
            "confidence_mean": round(confidence_mean, 4),
            "confidence_p50": round(confidence_p50, 4),
            "confidence_p90": round(confidence_p90, 4),
            "p95_latency_ms": round(_p95(latencies), 2),
        },
        "degrade_coverage": {level: (level in seen_degrade) for level in _DEGRADE_LEVELS},
        "l0_slots": {
            "target": l0_slots_target,
            "used": l0_slots_used,
        },
    }


def _concurrency_50(ctx, requests: int = 50) -> dict[str, Any]:
    def _run(idx: int) -> tuple[str, dict[str, Any]]:
        session_id = f"gate_conc_{idx:03d}"
        request = TripRequest(
            message=f"我想去杭州玩2天，出发2026-04-01，返程2026-04-02，并发{idx}",
            session_id=session_id,
            constraints={
                "city": "杭州",
                "days": 2,
                "date_start": "2026-04-01",
                "date_end": "2026-04-02",
                "cache_key": f"k_{idx:03d}",
            },
        )
        result = plan_trip(request, ctx).model_dump(mode="json")
        return session_id, result

    with ThreadPoolExecutor(max_workers=requests) as pool:
        rows = list(pool.map(_run, range(requests)))

    expected = {session_id for session_id, _ in rows}
    actual = {result.get("session_id", "") for _, result in rows}
    details: list[str] = []
    if expected != actual:
        details.append("session_id mismatch")

    success_count = 0
    for expected_id, result in rows:
        status = str(result.get("status", ""))
        if status in {"done", "clarifying"}:
            success_count += 1
        if result.get("session_id") != expected_id:
            details.append(f"session mix for {expected_id}")

    success_rate = success_count / max(requests, 1)
    isolation_score = 1.0 if not details else 0.0
    return {
        "requests": requests,
        "score": isolation_score,
        "success_rate": round(success_rate, 4),
        "details": details or ["ok"],
    }


def _run_degrade_eval_cases(path: Path = _DEFAULT_DEGRADE_CASES) -> dict[str, Any]:
    coverage: dict[str, bool] = {level: False for level in _DEGRADE_LEVELS}
    rows: list[dict[str, Any]] = []

    cases = _load_json(path)
    if not isinstance(cases, list):
        return {"coverage": coverage, "rows": rows}

    for case in cases:
        env = case.get("env", {})
        req = case.get("request", {})
        expected = str(case.get("expect_degrade_level", "")).strip()
        if not isinstance(env, dict) or not isinstance(req, dict):
            continue

        message = str(req.get("message", ""))
        constraints = dict(req.get("constraints", {})) if isinstance(req.get("constraints"), dict) else {}
        with _env_overrides({str(k): str(v) for k, v in env.items()}):
            result = plan_trip(
                TripRequest(message=message, constraints=constraints),
                make_app_context(),
            )

        actual = result.degrade_level
        if actual in coverage:
            coverage[actual] = True
        rows.append(
            {
                "id": str(case.get("id", "")),
                "expected_degrade_level": expected,
                "actual_degrade_level": actual,
                "passed": (not expected) or (actual == expected),
            }
        )

    return {"coverage": coverage, "rows": rows}


def _run_edit_roundtrip_probe() -> dict[str, Any]:
    session_id = f"gate_edit_{uuid.uuid4().hex[:8]}"
    probe_db_path = _ROOT / "data" / f"release_gate_probe_{uuid.uuid4().hex[:8]}.sqlite3"
    probe_db_path.parent.mkdir(parents=True, exist_ok=True)
    checks: dict[str, bool] = {
        "first_done": False,
        "second_done": False,
        "request_ids_present": False,
        "repo_available": False,
        "history_contains_both": False,
        "export_exists": False,
        "export_request_match": False,
        "export_session_match": False,
        "export_constraints_applied": False,
        "export_artifacts_complete": False,
    }

    try:
        with _env_overrides(
            {
                "PLAN_PERSISTENCE_ENABLED": "true",
                "PLAN_PERSISTENCE_DB": str(probe_db_path),
                "ROUTING_PROVIDER": "fixture",
            }
        ):
            ctx = make_app_context()
            first = plan_trip(
                TripRequest(
                    session_id=session_id,
                    message="北京一日游 2026-04-01",
                    constraints={
                        "city": "北京",
                        "days": 1,
                        "date_start": "2026-04-01",
                        "date_end": "2026-04-01",
                    },
                ),
                ctx,
            )
            second = plan_trip(
                TripRequest(
                    session_id=session_id,
                    message="replace stop for day 1",
                    constraints={
                        "city": "北京",
                        "days": 1,
                        "date_start": "2026-04-01",
                        "date_end": "2026-04-01",
                    },
                    metadata={
                        "edit_patch": {
                            "replace_stop": {
                                "day_number": 1,
                                "old_poi": "gate_old_stop",
                                "new_poi": "gate_new_stop",
                            }
                        }
                    },
                ),
                ctx,
            )

            checks["first_done"] = first.status.value == "done"
            checks["second_done"] = second.status.value == "done"
            checks["request_ids_present"] = bool(first.request_id) and bool(second.request_id)

            repo = getattr(ctx, "persistence_repo", None)
            checks["repo_available"] = (
                repo is not None
                and hasattr(repo, "list_session_history")
                and hasattr(repo, "get_plan_export")
            )
            if checks["repo_available"]:
                history = repo.list_session_history(session_id, limit=10)
                history_ids = {item.request_id for item in history}
                checks["history_contains_both"] = (
                    bool(first.request_id)
                    and bool(second.request_id)
                    and first.request_id in history_ids
                    and second.request_id in history_ids
                )

                export = repo.get_plan_export(second.request_id)
                checks["export_exists"] = export is not None
                if export is not None:
                    checks["export_request_match"] = export.request_id == second.request_id
                    checks["export_session_match"] = export.session_id == session_id
                    constraints = export.constraints if isinstance(export.constraints, dict) else {}
                    must_visit = {str(name) for name in constraints.get("must_visit", [])}
                    avoid = {str(name) for name in constraints.get("avoid", [])}
                    checks["export_constraints_applied"] = (
                        "gate_new_stop" in must_visit and "gate_old_stop" in avoid
                    )
                    artifact_types = {str(row.artifact_type) for row in export.artifacts}
                    checks["export_artifacts_complete"] = {
                        "itinerary",
                        "edit_patch",
                    }.issubset(artifact_types)
    except Exception as exc:
        return {"passed": False, "checks": checks, "details": [f"probe_error:{exc}"]}
    finally:
        for candidate in (
            probe_db_path,
            Path(str(probe_db_path) + "-wal"),
            Path(str(probe_db_path) + "-shm"),
        ):
            try:
                candidate.unlink()
            except FileNotFoundError:
                continue
            except OSError:
                continue

    failed = [key for key, passed in checks.items() if not passed]
    return {
        "passed": not failed,
        "checks": checks,
        "details": failed or ["ok"],
    }


def run_release_gate(
    *,
    config_path: Path = _DEFAULT_CONFIG,
    cases_path: Path = _DEFAULT_CASES,
) -> dict[str, Any]:
    thresholds = _load_json(config_path)
    cases = _load_json(cases_path)
    if not isinstance(cases, list):
        raise ValueError("eval/cases.json must be a list")
    if not isinstance(thresholds, dict):
        raise ValueError("eval/release_gate.json must be an object")

    eval_result = _evaluate_cases(cases)
    metrics = dict(eval_result["metrics"])

    concurrency_requests = max(1, int(os.getenv("RELEASE_GATE_CONCURRENCY_REQUESTS", "50")))
    conc = _concurrency_50(make_app_context(), requests=concurrency_requests)
    metrics["concurrency_isolation"] = round(float(conc["score"]), 4)
    metrics["concurrency_requests"] = concurrency_requests
    metrics["concurrency_success_rate"] = round(float(conc.get("success_rate", 0.0)), 4)
    # Enforce stress success-rate by folding it into plan_success_rate gate.
    metrics["plan_success_rate"] = round(
        min(float(metrics["plan_success_rate"]), float(conc["success_rate"])),
        4,
    )
    edit_roundtrip = _run_edit_roundtrip_probe()
    metrics["edit_roundtrip_pass_rate"] = 1.0 if edit_roundtrip.get("passed") else 0.0

    degrade_eval = _run_degrade_eval_cases()
    probe_coverage = degrade_eval["coverage"]
    merged_coverage = dict(eval_result["degrade_coverage"])
    for level, hit in probe_coverage.items():
        merged_coverage[level] = bool(merged_coverage.get(level)) or bool(hit)

    hard_thresholds = dict(_HARD_GATE_THRESHOLDS)
    for metric_name in list(hard_thresholds.keys()):
        if metric_name in thresholds:
            hard_thresholds[metric_name] = thresholds[metric_name]

    failures: list[dict[str, Any]] = []
    for metric_name, expected in hard_thresholds.items():
        actual = float(metrics.get(metric_name, 0.0))
        if _match_threshold(actual, expected):
            continue
        failures.append(
            {
                "metric": metric_name,
                "actual": round(actual, 4),
                "expected": expected,
                "hard_gate": True,
            }
        )

    if float(metrics.get("l0_real_routing_ratio", 0.0)) <= 0.0 and float(
        metrics.get("plan_success_rate", 0.0)
    ) > 0.0:
        failures.append(
            {
                "metric": "l0_real_presence",
                "actual": round(float(metrics.get("l0_real_routing_ratio", 0.0)), 4),
                "expected": ">0.0",
                "hard_gate": True,
            }
        )

    for metric_name, expected in thresholds.items():
        if metric_name in hard_thresholds:
            continue
        actual = float(metrics.get(metric_name, 0.0))
        passed = _match_threshold(actual, expected)
        if not passed:
            failures.append(
                {
                    "metric": metric_name,
                    "actual": round(actual, 4),
                    "expected": expected,
                }
            )

    missing_levels = [level for level, seen in merged_coverage.items() if not seen]
    if missing_levels:
        failures.append(
            {
                "metric": "degrade_level_coverage",
                "actual": ",".join(sorted(set(_DEGRADE_LEVELS) - set(missing_levels))),
                "expected": "L0,L1,L2,L3 all covered",
                "missing": missing_levels,
            }
        )

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "config_path": str(config_path),
        "cases_path": str(cases_path),
        "metrics": metrics,
        "thresholds": thresholds,
        "hard_thresholds": hard_thresholds,
        "concurrency": conc,
        "edit_roundtrip": edit_roundtrip,
        "degrade_coverage": merged_coverage,
        "degrade_eval_rows": degrade_eval["rows"],
        "failures": failures,
        "passed": not failures,
        "case_rows": eval_result["rows"],
    }

    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = _REPORT_DIR / "release_gate_latest.json"
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    print("release_gate metrics:")
    for key in sorted(metrics):
        print(f"- {key}: {metrics[key]}")
    print(f"- degrade_coverage: {merged_coverage}")
    print(f"- report: {report_path}")

    if failures:
        print("release_gate FAIL")
        for row in failures:
            print(f"  - {row}")
    else:
        print("release_gate PASS")
    return report


def main() -> int:
    report = run_release_gate()
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
