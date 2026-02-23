"""Single entrypoint for trip planning orchestration."""

from __future__ import annotations

import concurrent.futures
import copy
import os
import re
import time
import uuid
from collections.abc import Mapping
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config.runtime_fingerprint import build_run_fingerprint
from app.application.context import AppContext
from app.application.contracts import EvidenceSource, FieldEvidence, TripRequest, TripResult, TripStatus
from app.application.graph.nodes.merge_user_update import merge_user_update_node
from app.application.state_factory import make_initial_state
from app.observability.plan_metrics import observe_plan_request
from app.parsing.regex_extractors import extract_city, extract_days
from app.persistence.models import ArtifactRecord, PlanRecord, RequestRecord, SessionRecord
from app.application.itinerary_edit import (
    PlanEditPatch,
    apply_edit_patch_to_request,
    build_edit_patch,
    merge_itinerary_by_patch,
)
from app.security.prompt_injection import detect_prompt_injection
from app.trust.confidence import (
    compute_confidence,
    default_routing_source,
    derive_constraint_satisfaction,
    infer_fallback_count,
    infer_routing_source,
)
from app.trust.facts.fact_classification import classify_field, compute_verified_fact_ratio

_REQUIRED_FIELDS = ("city", "days", "date_start", "date_end")
_FIELD_LABELS = {
    "city": "目的地城市",
    "days": "旅行天数",
    "date_start": "出发日期（YYYY-MM-DD）",
    "date_end": "返程日期（YYYY-MM-DD）",
}
_DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
_CRITICAL_FACT_FIELDS = ("ticket_price", "reservation_required", "open_hours", "closed_rules")
_VERIFIED_SOURCE_TYPES = frozenset({"verified", "curated"})


class GraphTimeoutError(RuntimeError):
    def __init__(self, timeout: int):
        self.timeout = timeout
        super().__init__(f"graph invoke timed out after {timeout}s")


def _extract_dates_from_text(text: str) -> tuple[str | None, str | None]:
    matches = _DATE_RE.findall(text)
    if not matches:
        return None, None
    if len(matches) == 1:
        return matches[0], None
    return matches[0], matches[1]


def _infer_field_evidence(request: TripRequest) -> dict[str, FieldEvidence]:
    text_city = extract_city(request.message)
    text_days = extract_days(request.message)
    text_start, text_end = _extract_dates_from_text(request.message)

    text_values: dict[str, Any] = {
        "city": text_city,
        "days": text_days,
        "date_start": text_start,
        "date_end": text_end,
    }

    meta_sources = request.metadata.get("field_sources", {}) if isinstance(request.metadata, dict) else {}

    evidence: dict[str, FieldEvidence] = {}
    for field_name in _REQUIRED_FIELDS:
        text_value = text_values.get(field_name)
        if text_value not in (None, ""):
            evidence[field_name] = FieldEvidence(
                field=field_name,
                source=EvidenceSource.USER_TEXT,
                value=text_value,
            )
            continue

        form_value = request.constraints.get(field_name)
        if form_value not in (None, ""):
            source = EvidenceSource.USER_FORM
            if meta_sources.get(field_name) == EvidenceSource.LLM_GUESS.value:
                source = EvidenceSource.LLM_GUESS
            evidence[field_name] = FieldEvidence(
                field=field_name,
                source=source,
                value=form_value,
            )
            continue

        evidence[field_name] = FieldEvidence(
            field=field_name,
            source=EvidenceSource.DEFAULT,
            value=None,
        )

    return evidence


def _build_clarifying_result(
    session_id: str,
    evidence: dict[str, FieldEvidence],
) -> TripResult:
    issues: list[str] = []
    next_questions: list[str] = []

    for field_name in _REQUIRED_FIELDS:
        item = evidence[field_name]
        if item.source in {EvidenceSource.USER_TEXT, EvidenceSource.USER_FORM}:
            continue
        issues.append(f"{field_name} source={item.source.value}")
        next_questions.append(f"请补充{_FIELD_LABELS[field_name]}")

    message = "为了确保行程可执行，请先补充以下信息：\n- " + "\n- ".join(next_questions)

    return TripResult(
        status=TripStatus.CLARIFYING,
        message=message,
        session_id=session_id,
        issues=issues,
        next_questions=next_questions,
        field_evidence=evidence,
    )


def _invoke_with_timeout(graph: Any, state: dict[str, Any], timeout: int) -> dict[str, Any]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(graph.invoke, state)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            raise GraphTimeoutError(timeout) from None


def _extract_last_message(state: dict[str, Any]) -> str:
    messages = state.get("messages", [])
    if not messages:
        return ""
    last = messages[-1]
    if isinstance(last, dict):
        return str(last.get("content", ""))
    return str(last)


def _extract_next_questions(state: dict[str, Any]) -> list[str]:
    missing = state.get("requirements_missing", [])
    if not missing:
        return []
    result: list[str] = []
    for field_name in missing:
        label = _FIELD_LABELS.get(field_name, field_name)
        result.append(f"请补充{label}")
    return result


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _ensure_fact_field_aliases(itinerary: dict[str, Any]) -> None:
    routing_source = str(itinerary.get("routing_source", ""))
    for day in itinerary.get("days", []):
        if not isinstance(day, dict):
            continue
        for item in day.get("schedule", []):
            if not isinstance(item, dict):
                continue
            poi = item.get("poi")
            if not isinstance(poi, dict):
                continue

            if "reservation_required" not in poi:
                poi["reservation_required"] = bool(poi.get("requires_reservation", False))
            if "requires_reservation" not in poi:
                poi["requires_reservation"] = bool(poi.get("reservation_required", False))
            if "open_hours" not in poi:
                poi["open_hours"] = poi.get("open_time")
            if "open_time" not in poi:
                poi["open_time"] = poi.get("open_hours")
            if "ticket_price" not in poi:
                poi["ticket_price"] = float(poi.get("cost", 0.0) or 0.0)
            if "cost" not in poi:
                poi["cost"] = float(poi.get("ticket_price", 0.0) or 0.0)

            metadata_source = str(poi.get("metadata_source", ""))
            has_fact_sources = isinstance(poi.get("fact_sources"), dict)
            fact_sources = dict(poi.get("fact_sources", {})) if has_fact_sources else {}
            for field_name in _CRITICAL_FACT_FIELDS:
                source_hint = fact_sources.get(f"{field_name}_source_type")
                if source_hint is None:
                    source_hint = fact_sources.get(field_name)
                classified = classify_field(
                    poi.get(field_name),
                    {
                        "source_type": source_hint or metadata_source,
                        "metadata_source": metadata_source,
                        "routing_source": routing_source,
                        "has_fact_sources": has_fact_sources,
                        "field_name": field_name,
                    },
                )
                source_type = str(classified.get("source_type", "unknown"))
                fact_sources[f"{field_name}_source_type"] = source_type
                fact_sources.setdefault(field_name, source_type)
            poi["fact_sources"] = fact_sources

            if "llm" in metadata_source.lower():
                # Guardrail: never keep fabricated hard facts from model guesses.
                poi["ticket_price"] = 0.0
                poi["cost"] = 0.0
                poi["open_time"] = None
                poi["open_hours"] = None
                poi["closed_rules"] = ""
                poi["reservation_required"] = False
                poi["requires_reservation"] = False


def _compute_unknown_fields(itinerary: dict[str, Any]) -> tuple[list[str], float]:
    unknown_fields: list[str] = []
    total = 0
    unknown = 0
    routing_source = str(itinerary.get("routing_source", ""))

    for day in itinerary.get("days", []):
        if not isinstance(day, dict):
            continue
        for item in day.get("schedule", []):
            if not isinstance(item, dict) or item.get("is_backup"):
                continue
            poi = item.get("poi")
            if not isinstance(poi, dict):
                continue
            poi_name = str(poi.get("name", "unknown_poi"))
            metadata_source = str(poi.get("metadata_source", ""))
            has_fact_sources = isinstance(poi.get("fact_sources"), dict)
            fact_sources = dict(poi.get("fact_sources", {})) if has_fact_sources else {}

            for field_name in _CRITICAL_FACT_FIELDS:
                total += 1
                source_hint = fact_sources.get(f"{field_name}_source_type")
                if source_hint is None:
                    source_hint = fact_sources.get(field_name)
                classified = classify_field(
                    poi.get(field_name),
                    {
                        "source_type": source_hint or metadata_source,
                        "metadata_source": metadata_source,
                        "routing_source": routing_source,
                        "has_fact_sources": has_fact_sources,
                        "field_name": field_name,
                    },
                )
                source_type = str(classified.get("source_type", "unknown")).strip().lower()
                if source_type not in _VERIFIED_SOURCE_TYPES:
                    unknown += 1
                    unknown_fields.append(f"{poi_name}.{field_name}")

    ratio = (unknown / total) if total else 0.0
    return _dedupe(unknown_fields), ratio


def _extract_violations(state: dict[str, Any]) -> list[str]:
    rows = state.get("validation_issues", [])
    violations: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            code = str(row.get("code", "")).strip()
            message = str(row.get("message", "")).strip()
            if code and message:
                violations.append(f"{code}:{message}")
            elif code:
                violations.append(code)
            elif message:
                violations.append(message)
        else:
            violations.append(str(row))
    return _dedupe(violations)


def _compute_result_confidence(
    *,
    itinerary: dict[str, Any] | None,
    status: TripStatus,
    violations: list[str],
    repair_attempts: int,
) -> tuple[float, dict[str, Any], float, str, int]:
    routing_source = infer_routing_source(
        itinerary,
        default_source=default_routing_source(os.getenv("ROUTING_PROVIDER", "fixture")),
    )
    fallback_count = infer_fallback_count(itinerary, routing_source=routing_source)
    verified_fact_ratio = compute_verified_fact_ratio(itinerary) if isinstance(itinerary, dict) else 0.0
    constraint_satisfaction = derive_constraint_satisfaction(
        status=status.value,
        violation_count=len(violations),
    )
    confidence_payload = compute_confidence(
        {
            "verified_fact_ratio": verified_fact_ratio,
            "routing_source": routing_source,
            "fallback_count": fallback_count,
            "repair_count": repair_attempts,
            "constraint_satisfaction": constraint_satisfaction,
        }
    )
    breakdown = confidence_payload.get("confidence_breakdown")
    return float(confidence_payload.get("confidence_score", 0.0)), (
        breakdown if isinstance(breakdown, dict) else {}
    ), verified_fact_ratio, routing_source, fallback_count


def _derive_degrade_level(
    *,
    status: TripStatus,
    unknown_fields: list[str],
    violations: list[str],
) -> str:
    if status != TripStatus.DONE:
        return "L3"
    if unknown_fields:
        return "L2"
    if violations:
        return "L3"

    provider = os.getenv("ROUTING_PROVIDER", "fixture").strip().lower()
    return "L1" if provider != "real" else "L0"


def _normalize_constraint_dates(constraints: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(constraints)
    for key in ("date_start", "date_end"):
        value = normalized.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        candidate = text.replace("/", "-").replace(".", "-")
        try:
            normalized[key] = datetime.fromisoformat(candidate[:10]).date().isoformat()
        except ValueError:
            normalized[key] = text
    return normalized


def _prepare_state(
    request: TripRequest,
    ctx: AppContext,
    session_id: str,
    *,
    request_id: str,
    trace_id: str,
) -> dict[str, Any]:
    if request.session_id:
        persisted = ctx.session_store.get(session_id)
        if persisted is None:
            state = make_initial_state()
        else:
            # Detach per-request mutations from stored snapshots to avoid cross-request leaks.
            state = copy.deepcopy(persisted)
    else:
        state = make_initial_state()

    constraints = dict(state.get("trip_constraints", {}))
    constraints.update(request.constraints)
    state["trip_constraints"] = _normalize_constraint_dates(constraints)

    profile = dict(state.get("user_profile", {}))
    profile.update(request.user_profile)
    state["user_profile"] = profile

    state.setdefault("messages", [])
    state["messages"].append({"role": "user", "content": request.message})
    state["session_id"] = session_id
    state["request_id"] = request_id
    state["trace_id"] = trace_id
    metrics = dict(state.get("metrics", {}))
    metrics.setdefault("llm_call_count", 0)
    state["metrics"] = metrics

    if state.get("status") == "clarifying":
        merge_result = merge_user_update_node(state)
        state.update(merge_result)

    return state


def _load_previous_itinerary(ctx: AppContext, session_id: str, *, has_session: bool) -> dict[str, Any] | None:
    if not has_session:
        return None
    try:
        state = ctx.session_store.get(session_id)
    except Exception:
        return None
    if not isinstance(state, Mapping):
        return None
    itinerary = state.get("final_itinerary")
    if isinstance(itinerary, dict):
        return copy.deepcopy(itinerary)
    return None


def _normalize_status(raw_status: str) -> TripStatus:
    if raw_status == TripStatus.DONE.value:
        return TripStatus.DONE
    if raw_status == TripStatus.CLARIFYING.value:
        return TripStatus.CLARIFYING
    return TripStatus.ERROR


def _parse_date(value: Any) -> date_cls | None:
    if value is None:
        return None
    if isinstance(value, date_cls):
        return value
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("/", "-").replace(".", "-")
    if normalized:
        try:
            return datetime.fromisoformat(normalized[:10]).date()
        except ValueError:
            pass
    for fmt in ("%Y/%m/%d", "%Y.%m.%d", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _apply_requested_dates(itinerary: dict[str, Any], state: dict[str, Any]) -> None:
    constraints = state.get("trip_constraints", {})
    if isinstance(constraints, Mapping):
        start_raw = constraints.get("date_start")
    else:
        start_raw = getattr(constraints, "date_start", None)
    start_date = _parse_date(start_raw)
    if start_date is None:
        return

    days = itinerary.get("days")
    if not isinstance(days, list):
        return
    for idx, day in enumerate(days):
        if not isinstance(day, dict):
            continue
        day["date"] = (start_date + timedelta(days=idx)).isoformat()


def _invoke_graph(
    request: TripRequest,
    ctx: AppContext,
    session_id: str,
    *,
    request_id: str,
    trace_id: str,
) -> tuple[TripResult, dict[str, Any]]:
    state = _prepare_state(
        request,
        ctx,
        session_id,
        request_id=request_id,
        trace_id=trace_id,
    )
    graph = ctx.get_graph()
    result_state = _invoke_with_timeout(graph, state, timeout=ctx.graph_timeout_seconds)
    ctx.session_store.save(session_id, result_state)

    status = _normalize_status(str(result_state.get("status", "error")))
    itinerary = result_state.get("final_itinerary")
    message = _extract_last_message(result_state)
    issues: list[str] = []

    if status == TripStatus.ERROR:
        error_msg = result_state.get("error_message")
        if error_msg:
            issues.append(str(error_msg))

    if result_state.get("validation_issues") and status != TripStatus.DONE:
        issues.append("validation_issues_present")

    result = TripResult(
        status=status,
        message=message,
        itinerary=itinerary,
        session_id=session_id,
        issues=issues,
        next_questions=_extract_next_questions(result_state) if status == TripStatus.CLARIFYING else [],
    )
    return result, result_state


def _enrich_result(
    *,
    result: TripResult,
    state: dict[str, Any],
    request_id: str,
    trace_id: str,
) -> tuple[list[str], float, str, int, int]:
    unknown_fields: list[str] = []
    unknown_ratio = 0.0
    confidence = 0.0
    violations = _extract_violations(state)
    repair_attempts = int(state.get("repair_attempts", 0) or 0)

    itinerary = result.itinerary if isinstance(result.itinerary, dict) else None
    if itinerary is not None:
        _apply_requested_dates(itinerary, state)
        _ensure_fact_field_aliases(itinerary)
        unknown_fields, unknown_ratio = _compute_unknown_fields(itinerary)

        assumptions = list(itinerary.get("assumptions", []))
        if unknown_fields:
            assumptions.append("部分关键事实来自未知来源，建议出发前二次确认票价、开放时间与预约规则。")
        itinerary["assumptions"] = _dedupe([str(item) for item in assumptions if str(item).strip()])
        itinerary["unknown_fields"] = unknown_fields
        itinerary["trace_id"] = trace_id
        itinerary["violations"] = violations

        repair_actions: list[str] = []
        existing_repair_actions = itinerary.get("repair_actions", [])
        if isinstance(existing_repair_actions, list):
            repair_actions.extend(
                [
                    str(item).strip()
                    for item in existing_repair_actions
                    if str(item).strip()
                ]
            )
        if repair_attempts > 0:
            repair_actions.append(f"repair_loop_attempts={repair_attempts}")
        itinerary["repair_actions"] = _dedupe(repair_actions)

        (
            confidence,
            confidence_breakdown,
            verified_fact_ratio,
            routing_source,
            fallback_count,
        ) = _compute_result_confidence(
            itinerary=itinerary,
            status=result.status,
            violations=violations,
            repair_attempts=repair_attempts,
        )
        itinerary["verified_fact_ratio"] = round(verified_fact_ratio, 4)
        itinerary["routing_source"] = routing_source
        itinerary["fallback_count"] = fallback_count
        itinerary["confidence_breakdown"] = confidence_breakdown
        itinerary["confidence_score"] = confidence

        degrade_level = _derive_degrade_level(
            status=result.status,
            unknown_fields=unknown_fields,
            violations=violations,
        )
        itinerary["degrade_level"] = degrade_level
        result.itinerary = itinerary
    else:
        degrade_level = _derive_degrade_level(
            status=result.status,
            unknown_fields=[],
            violations=violations,
        )
        (
            confidence,
            _confidence_breakdown,
            _verified_fact_ratio,
            _routing_source,
            _fallback_count,
        ) = _compute_result_confidence(
            itinerary=None,
            status=result.status,
            violations=violations,
            repair_attempts=repair_attempts,
        )

    result.request_id = request_id
    result.trace_id = trace_id
    result.degrade_level = degrade_level
    result.confidence_score = confidence
    return unknown_fields, unknown_ratio, degrade_level, int(state.get("metrics", {}).get("llm_call_count", 0)), repair_attempts


def _attach_run_fingerprint(*, result: TripResult, trace_id: str) -> None:
    itinerary_payload = result.itinerary if isinstance(result.itinerary, dict) else None
    result.run_fingerprint = build_run_fingerprint(
        trace_id=trace_id,
        itinerary=itinerary_payload,
    )


def _persist_trip_run(
    *,
    ctx: AppContext,
    request: TripRequest,
    result: TripResult,
    session_id: str,
    request_id: str,
    trace_id: str,
    unknown_ratio: float,
    llm_call_count: int,
    repair_attempts: int,
    edit_patch: PlanEditPatch | None = None,
) -> None:
    repo = getattr(ctx, "persistence_repo", None)
    if repo is None:
        return

    timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    field_evidence_payload = {
        name: item.model_dump(mode="json")
        for name, item in result.field_evidence.items()
    }
    run_fingerprint_payload = (
        result.run_fingerprint.model_dump(mode="json")
        if result.run_fingerprint is not None
        else None
    )
    metrics_payload = {
        "engine_version": ctx.engine_version,
        "strict_required_fields": bool(ctx.strict_required_fields),
        "unknown_ratio": round(max(0.0, unknown_ratio), 4),
        "llm_call_count": max(0, int(llm_call_count)),
        "repair_attempts": max(0, int(repair_attempts)),
    }

    try:
        repo.save_session(
            SessionRecord(
                session_id=session_id,
                updated_at=timestamp,
                status=result.status.value,
                trace_id=trace_id,
            )
        )
        repo.save_request(
            RequestRecord(
                request_id=request_id,
                session_id=session_id,
                trace_id=trace_id,
                message=request.message,
                constraints=dict(request.constraints),
                user_profile=dict(request.user_profile),
                metadata=dict(request.metadata),
                created_at=timestamp,
            )
        )
        repo.save_plan(
            PlanRecord(
                request_id=request_id,
                session_id=session_id,
                trace_id=trace_id,
                status=result.status.value,
                degrade_level=result.degrade_level,
                confidence_score=result.confidence_score,
                run_fingerprint=run_fingerprint_payload,
                itinerary=result.itinerary if isinstance(result.itinerary, dict) else None,
                issues=list(result.issues),
                next_questions=list(result.next_questions),
                field_evidence=field_evidence_payload,
                metrics=metrics_payload,
                created_at=timestamp,
            )
        )
        if isinstance(result.itinerary, dict):
            repo.save_artifact(
                ArtifactRecord(
                    request_id=request_id,
                    artifact_type="itinerary",
                    payload=result.itinerary,
                    created_at=timestamp,
                )
            )
        if edit_patch is not None:
            repo.save_artifact(
                ArtifactRecord(
                    request_id=request_id,
                    artifact_type="edit_patch",
                    payload=edit_patch.model_dump(mode="json"),
                    created_at=timestamp,
                )
            )
    except Exception as exc:
        logger = getattr(ctx, "logger", None)
        if logger and hasattr(logger, "warning"):
            logger.warning("persistence", f"persist failed: {exc}")


def plan_trip(request: TripRequest, ctx: AppContext) -> TripResult:
    started = time.perf_counter()
    status_for_metrics = TripStatus.ERROR.value
    request_id = str(uuid.uuid4())[:12]
    trace_id = str(uuid.uuid4())[:12]
    degrade_for_metrics = "L3"
    llm_calls_for_metrics = 0
    repair_loops_for_metrics = 0
    unknown_ratio_for_persistence = 0.0
    session_id = request.session_id or str(uuid.uuid4())[:8]
    previous_itinerary = _load_previous_itinerary(
        ctx,
        session_id,
        has_session=bool(request.session_id),
    )
    edit_patch = build_edit_patch(
        message=request.message,
        metadata=request.metadata,
        previous_itinerary=previous_itinerary,
    )
    effective_request = apply_edit_patch_to_request(request, edit_patch) if edit_patch is not None else request

    try:
        evidence = _infer_field_evidence(effective_request)
        injection_flags = detect_prompt_injection(effective_request.message)

        strict_gate = ctx.engine_version != "v1" and ctx.strict_required_fields
        if strict_gate:
            clarify = _build_clarifying_result(session_id, evidence)
            if clarify.next_questions:
                clarify.request_id = request_id
                clarify.trace_id = trace_id
                clarify.degrade_level = "L3"
                clarify.confidence_score = 0.0
                _attach_run_fingerprint(result=clarify, trace_id=trace_id)
                if injection_flags:
                    clarify.issues = _dedupe(list(clarify.issues) + ["prompt_injection_suspected"])
                _persist_trip_run(
                    ctx=ctx,
                    request=effective_request,
                    result=clarify,
                    session_id=session_id,
                    request_id=request_id,
                    trace_id=trace_id,
                    unknown_ratio=0.0,
                    llm_call_count=0,
                    repair_attempts=0,
                    edit_patch=edit_patch,
                )
                status_for_metrics = clarify.status.value
                degrade_for_metrics = clarify.degrade_level
                return clarify

        result, state = _invoke_graph(
            effective_request,
            ctx,
            session_id,
            request_id=request_id,
            trace_id=trace_id,
        )
        result.field_evidence = evidence
        if injection_flags:
            result.issues = _dedupe(list(result.issues) + ["prompt_injection_suspected"])

        if edit_patch is not None:
            merged = merge_itinerary_by_patch(
                current_itinerary=result.itinerary if isinstance(result.itinerary, dict) else None,
                previous_itinerary=previous_itinerary,
                patch=edit_patch,
            )
            if isinstance(merged, dict):
                result.itinerary = merged
                if merged.get("summary"):
                    result.message = str(merged.get("summary"))

        (
            _unknown_fields,
            unknown_ratio,
            degrade_level,
            llm_call_count,
            repair_attempts,
        ) = _enrich_result(
            result=result,
            state=state,
            request_id=request_id,
            trace_id=trace_id,
        )
        _attach_run_fingerprint(result=result, trace_id=trace_id)
        unknown_ratio_for_persistence = unknown_ratio

        if result.status == TripStatus.ERROR and not result.message:
            result.message = "规划失败，请稍后重试"

        if result.status == TripStatus.CLARIFYING and not result.next_questions:
            result.next_questions = ["请补充目的地城市", "请补充旅行天数"]

        status_for_metrics = result.status.value
        degrade_for_metrics = degrade_level
        llm_calls_for_metrics = llm_call_count
        repair_loops_for_metrics = repair_attempts
        _persist_trip_run(
            ctx=ctx,
            request=effective_request,
            result=result,
            session_id=session_id,
            request_id=request_id,
            trace_id=trace_id,
            unknown_ratio=unknown_ratio_for_persistence,
            llm_call_count=llm_calls_for_metrics,
            repair_attempts=repair_loops_for_metrics,
            edit_patch=edit_patch,
        )
        return result
    finally:
        observe_plan_request(
            status=status_for_metrics,
            engine_version=ctx.engine_version,
            strict_required_fields=ctx.strict_required_fields,
            request_id=request_id,
            trace_id=trace_id,
            degrade_level=degrade_for_metrics,
            llm_call_count=llm_calls_for_metrics,
            repair_loop_count=repair_loops_for_metrics,
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )


__all__ = [
    "GraphTimeoutError",
    "plan_trip",
]
