"""Single source of truth for fact field trust classification."""

from __future__ import annotations

import math
import re
from typing import Any

CRITICAL_FACT_FIELDS = (
    "ticket_price",
    "reservation_required",
    "open_hours",
    "closed_rules",
)

_VERIFIED_SOURCE_TYPES = frozenset({"verified", "curated"})
_SOURCE_CONFIDENCE = {
    "verified": 0.95,
    "curated": 0.82,
    "heuristic": 0.45,
    "fallback": 0.25,
    "unknown": 0.0,
}

_SOURCE_KEYS = (
    "source_type",
    "source",
    "fact_source",
    "provider",
    "metadata_source",
    "routing_source",
)

_VERIFIED_HINTS = ("verified", "official", "trusted_api", "government")
_CURATED_HINTS = ("curated", "data", "dataset", "tool_data", "catalog")
_HEURISTIC_HINTS = ("heuristic", "llm", "estimate", "inferred", "derived", "guess")
_FALLBACK_HINTS = ("fallback", "fixture", "degraded", "tool_failed", "routing_fallback")

_PLACEHOLDER_SNIPPETS = (
    "\u4ee5\u516c\u544a\u4e3a\u51c6",
    "\u5efa\u8bae\u54a8\u8be2\u5b98\u65b9",
    "\u8bf7\u4ee5\u5b98\u65b9\u516c\u544a\u4e3a\u51c6",
    "\u4ee5\u666f\u533a\u516c\u544a\u4e3a\u51c6",
    "\u4ee5\u5f53\u65e5\u516c\u544a\u4e3a\u51c6",
    "consult official",
    "check official",
    "to be confirmed",
    "tbd",
    "pending update",
)
_PLACEHOLDER_PATTERNS = (
    re.compile(r"\u4ee5.{0,10}\u4e3a\u51c6"),
    re.compile(r"\u5efa\u8bae.{0,8}\u5b98\u65b9"),
)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_missing_value(field_value: Any) -> bool:
    if field_value is None:
        return True
    if isinstance(field_value, float) and math.isnan(field_value):
        return True
    if isinstance(field_value, str):
        return field_value.strip() == ""
    if isinstance(field_value, (dict, list, tuple, set)):
        return len(field_value) == 0
    return False


def _is_placeholder_value(field_value: Any) -> bool:
    if not isinstance(field_value, str):
        return False
    normalized = _normalized_text(field_value)
    if not normalized:
        return True
    if normalized in {"unknown", "n/a", "na", "none"}:
        return True
    if any(snippet in normalized for snippet in _PLACEHOLDER_SNIPPETS):
        return True
    return any(pattern.search(normalized) for pattern in _PLACEHOLDER_PATTERNS)


def _as_meta_dict(source_meta: Any) -> dict[str, Any]:
    if isinstance(source_meta, dict):
        return dict(source_meta)
    if isinstance(source_meta, str):
        return {"source_type": source_meta}
    return {}


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _normalized_text(value) in {"1", "true", "yes", "y"}


def _meta_missing_fact_sources(meta: dict[str, Any]) -> bool:
    if _is_truthy(meta.get("fact_sources_missing")):
        return True
    if "has_fact_sources" in meta and not _is_truthy(meta.get("has_fact_sources")):
        return True
    if "fact_sources_present" in meta and not _is_truthy(meta.get("fact_sources_present")):
        return True
    return False


def _meta_indicates_fallback(meta: dict[str, Any]) -> bool:
    for key in ("fallback", "is_fallback", "tool_failed", "tool_failure", "routing_fallback"):
        if _is_truthy(meta.get(key)):
            return True

    for key in ("tool_status", "routing_status", "status"):
        status = _normalized_text(meta.get(key))
        if status in {"fallback", "failed", "error", "timeout", "unavailable"}:
            return True

    for key in ("routing_source", "source_type", "source"):
        text = _normalized_text(meta.get(key))
        if "fallback" in text or "fixture" in text:
            return True
    return False


def _extract_source_hint(meta: dict[str, Any]) -> str:
    for key in _SOURCE_KEYS:
        value = _normalized_text(meta.get(key))
        if value:
            return value
    return ""


def _source_type_from_hint(source_hint: str) -> str:
    if not source_hint or source_hint in {"unknown", "unverified", "missing", "none"}:
        return "unknown"
    if any(hint in source_hint for hint in _FALLBACK_HINTS):
        return "fallback"
    if any(hint in source_hint for hint in _HEURISTIC_HINTS):
        return "heuristic"
    if any(hint in source_hint for hint in _VERIFIED_HINTS):
        return "verified"
    if any(hint in source_hint for hint in _CURATED_HINTS):
        return "curated"
    return "unknown"


def _allow_missing_for_field(*, field_name: str, source_type: str) -> bool:
    # Some providers encode "no special closure rule" as an empty field.
    return field_name == "closed_rules" and source_type in _VERIFIED_SOURCE_TYPES


def classify_field(field_value: Any, source_meta: Any) -> dict[str, Any]:
    """Classify one fact field into trust type and confidence."""
    meta = _as_meta_dict(source_meta)
    field_name = _normalized_text(meta.get("field_name"))
    if not meta or _meta_missing_fact_sources(meta):
        return {"source_type": "unknown", "field_confidence": 0.0}
    if _meta_indicates_fallback(meta):
        return {"source_type": "fallback", "field_confidence": _SOURCE_CONFIDENCE["fallback"]}

    source_type = _source_type_from_hint(_extract_source_hint(meta))
    confidence = _SOURCE_CONFIDENCE[source_type]
    if _is_missing_value(field_value) or _is_placeholder_value(field_value):
        if _allow_missing_for_field(field_name=field_name, source_type=source_type):
            return {"source_type": source_type, "field_confidence": confidence * 0.85}
        return {"source_type": "unknown", "field_confidence": 0.0}
    return {"source_type": source_type, "field_confidence": confidence}


def compute_verified_fact_ratio(itinerary: dict[str, Any]) -> float:
    """Compute ratio of fact fields classified as verified/curated only."""
    total = 0
    verified = 0
    for day in itinerary.get("days", []):
        if not isinstance(day, dict):
            continue
        for item in day.get("schedule", []):
            if not isinstance(item, dict) or item.get("is_backup"):
                continue
            poi = item.get("poi")
            if not isinstance(poi, dict):
                continue

            fact_sources = poi.get("fact_sources")
            fact_sources_dict = fact_sources if isinstance(fact_sources, dict) else {}
            for field_name in CRITICAL_FACT_FIELDS:
                total += 1
                source_hint = fact_sources_dict.get(f"{field_name}_source_type")
                if source_hint is None:
                    source_hint = fact_sources_dict.get(field_name)
                classified = classify_field(
                    poi.get(field_name),
                    {
                        "source_type": source_hint,
                        "has_fact_sources": isinstance(fact_sources, dict),
                        "field_name": field_name,
                    },
                )
                if classified["source_type"] in _VERIFIED_SOURCE_TYPES:
                    verified += 1
    return round((verified / total) if total else 0.0, 4)


__all__ = ["CRITICAL_FACT_FIELDS", "classify_field", "compute_verified_fact_ratio"]
