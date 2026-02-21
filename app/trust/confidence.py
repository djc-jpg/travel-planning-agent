"""Trust-layer confidence computation."""

from __future__ import annotations

from typing import Any, Mapping

_ROUTING_RELIABILITY = {
    "real": 1.0,
    "fixture": 0.72,
    "fallback": 0.58,
    "fallback_fixture": 0.52,
    "heuristic": 0.6,
    "unknown": 0.55,
}
_FALLBACK_CONFIDENCE_THRESHOLD = 0.5


def _clamp_unit(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if parsed < 0:
        return 0.0
    if parsed > 1:
        return 1.0
    return parsed


def _to_non_negative_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def default_routing_source(provider_name: str | None) -> str:
    provider = str(provider_name or "").strip().lower()
    return "real" if provider == "real" else "fixture"


def _iter_schedule_notes(itinerary: Mapping[str, Any]) -> list[str]:
    notes: list[str] = []
    for day in itinerary.get("days", []):
        if not isinstance(day, dict):
            continue
        for item in day.get("schedule", []):
            if not isinstance(item, dict) or item.get("is_backup"):
                continue
            notes.append(str(item.get("notes", "")))
    return notes


def _routing_confidence_from_notes(note: str) -> float | None:
    text = str(note or "")
    marker = "routing_confidence="
    if marker not in text:
        return None
    chunk = text.split(marker, 1)[1].split("|", 1)[0].strip()
    try:
        return float(chunk)
    except ValueError:
        return None


def _count_low_confidence_routes(itinerary: Mapping[str, Any]) -> int:
    hits = 0
    for note in _iter_schedule_notes(itinerary):
        value = _routing_confidence_from_notes(note)
        if value is None:
            continue
        if value <= _FALLBACK_CONFIDENCE_THRESHOLD:
            hits += 1
    return hits


def infer_routing_source(itinerary: Mapping[str, Any] | None, *, default_source: str) -> str:
    if not isinstance(itinerary, Mapping):
        return default_source

    for key in ("routing_source", "route_source"):
        value = str(itinerary.get(key, "")).strip().lower()
        if value:
            return value

    assumptions = itinerary.get("assumptions", [])
    if isinstance(assumptions, list):
        marker = "routing_source="
        for row in assumptions:
            text = str(row or "").strip().lower()
            if marker not in text:
                continue
            value = text.split(marker, 1)[1].split("|", 1)[0].strip()
            if value:
                return value
    if str(default_source).strip().lower() == "real" and _count_low_confidence_routes(itinerary) > 0:
        return "fallback_fixture"
    return default_source


def infer_fallback_count(
    itinerary: Mapping[str, Any] | None,
    *,
    routing_source: str,
) -> int:
    if isinstance(itinerary, Mapping):
        explicit = _to_non_negative_int(itinerary.get("fallback_count"))
        if explicit > 0:
            return explicit

        count = 0
        for day in itinerary.get("days", []):
            if not isinstance(day, dict):
                continue
            for item in day.get("schedule", []):
                if not isinstance(item, dict) or item.get("is_backup"):
                    continue
                if "fallback" in str(item.get("notes", "")).lower():
                    count += 1
        if count > 0:
            return count
        low_confidence_hits = _count_low_confidence_routes(itinerary)
        if low_confidence_hits > 0:
            return low_confidence_hits

    return 1 if "fallback" in str(routing_source).lower() else 0


def derive_constraint_satisfaction(*, status: str, violation_count: int) -> float:
    normalized_status = str(status).strip().lower()
    if normalized_status == "error":
        return 0.0
    if normalized_status != "done":
        return 0.35

    penalty = min(0.6, max(0, int(violation_count)) * 0.2)
    return round(max(0.4, 1.0 - penalty), 3)


def _routing_reliability(routing_source: str) -> float:
    source = str(routing_source or "").strip().lower()
    if source in _ROUTING_RELIABILITY:
        return _ROUTING_RELIABILITY[source]
    if "fallback" in source:
        return _ROUTING_RELIABILITY["fallback"]
    if "fixture" in source:
        return _ROUTING_RELIABILITY["fixture"]
    return _ROUTING_RELIABILITY["unknown"]


def _compute_cap(verified_fact_ratio: float, routing_source: str) -> tuple[float, list[str]]:
    cap = 1.0
    reasons: list[str] = []

    if verified_fact_ratio < 0.5:
        cap = min(cap, 0.6)
        reasons.append("verified_fact_ratio<0.5")

    normalized_source = str(routing_source).strip().lower()
    if normalized_source == "fixture":
        cap = min(cap, 0.7)
        reasons.append("routing_source=fixture")
    elif "fallback" in normalized_source:
        cap = min(cap, 0.65)
        reasons.append("routing_source=fallback")

    return cap, reasons


def compute_confidence(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Compute confidence score and explainable breakdown."""
    verified_fact_ratio = _clamp_unit(payload.get("verified_fact_ratio"), default=0.0)
    constraint_satisfaction = _clamp_unit(payload.get("constraint_satisfaction"), default=0.0)
    routing_source = str(payload.get("routing_source", "unknown") or "unknown").strip().lower()
    fallback_count = _to_non_negative_int(payload.get("fallback_count"))
    repair_count = _to_non_negative_int(payload.get("repair_count"))

    routing_reliability = _routing_reliability(routing_source)
    weighted_base = (
        verified_fact_ratio * 0.55
        + constraint_satisfaction * 0.25
        + routing_reliability * 0.20
    )
    fallback_penalty = min(0.3, fallback_count * 0.08)
    repair_penalty = min(0.25, repair_count * 0.04)
    total_penalty = fallback_penalty + repair_penalty
    raw_score = max(0.0, weighted_base - total_penalty)
    cap, cap_reasons = _compute_cap(verified_fact_ratio, routing_source)
    confidence_score = round(min(cap, raw_score), 3)

    return {
        "confidence_score": confidence_score,
        "confidence_breakdown": {
            "inputs": {
                "verified_fact_ratio": round(verified_fact_ratio, 4),
                "constraint_satisfaction": round(constraint_satisfaction, 4),
                "routing_source": routing_source,
                "fallback_count": fallback_count,
                "repair_count": repair_count,
            },
            "components": {
                "verified_component": round(verified_fact_ratio * 0.55, 4),
                "constraint_component": round(constraint_satisfaction * 0.25, 4),
                "routing_component": round(routing_reliability * 0.20, 4),
                "weighted_base": round(weighted_base, 4),
            },
            "penalties": {
                "fallback_penalty": round(fallback_penalty, 4),
                "repair_penalty": round(repair_penalty, 4),
                "total_penalty": round(total_penalty, 4),
            },
            "caps": {
                "applied_cap": round(cap, 4),
                "reasons": cap_reasons,
            },
            "raw_score": round(raw_score, 4),
        },
    }


__all__ = [
    "compute_confidence",
    "default_routing_source",
    "derive_constraint_satisfaction",
    "infer_fallback_count",
    "infer_routing_source",
]
