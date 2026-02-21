"""Presentation helpers for user/debug itinerary payloads."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from typing import Any

_TOP_LEVEL_DEBUG_KEYS = {
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
_POI_DEBUG_KEYS = {
    "metadata_source",
    "cluster",
    "fact_sources",
    "is_verified",
    "food_min_nearby",
}
_NOTE_DEBUG_PREFIXES = (
    "cluster=",
    "buffer=",
    "routing_confidence=",
    "closed_rules=",
)
_NOTE_DEBUG_EXACT = {
    "avoid_peak_hours",
    "fallback_schedule",
    "backup_option",
}
_NOTE_SPLITTER = re.compile(r"[|｜]")


def _strip_debug_tokens(note: str) -> str:
    parts = [part.strip() for part in _NOTE_SPLITTER.split(str(note or "")) if part.strip()]
    visible: list[str] = []
    for part in parts:
        lowered = part.lower()
        if lowered in _NOTE_DEBUG_EXACT:
            continue
        if any(lowered.startswith(prefix) for prefix in _NOTE_DEBUG_PREFIXES):
            continue
        visible.append(part)
    return " | ".join(visible)


def _present_poi(poi_payload: Any) -> Any:
    if not isinstance(poi_payload, Mapping):
        return poi_payload
    presented = dict(poi_payload)
    for key in _POI_DEBUG_KEYS:
        presented.pop(key, None)
    return presented


def _present_schedule_items(items: Any, *, debug: bool) -> Any:
    if not isinstance(items, list):
        return items

    rows: list[Any] = []
    for item in items:
        if not isinstance(item, Mapping):
            rows.append(item)
            continue
        shown = dict(item)
        shown["poi"] = _present_poi(shown.get("poi"))
        if not debug:
            note = _strip_debug_tokens(str(shown.get("notes", "")))
            if note:
                shown["notes"] = note
            else:
                shown.pop("notes", None)
        rows.append(shown)
    return rows


def _present_days(days: Any, *, debug: bool) -> Any:
    if not isinstance(days, list):
        return days
    rows: list[Any] = []
    for day in days:
        if not isinstance(day, Mapping):
            rows.append(day)
            continue
        shown = dict(day)
        shown["schedule"] = _present_schedule_items(shown.get("schedule"), debug=debug)
        shown["backups"] = _present_schedule_items(shown.get("backups"), debug=debug)
        rows.append(shown)
    return rows


def present_itinerary(itinerary: dict[str, Any] | None, *, debug: bool) -> dict[str, Any] | None:
    if itinerary is None:
        return None
    if debug:
        return copy.deepcopy(itinerary)

    shown = copy.deepcopy(itinerary)
    for key in _TOP_LEVEL_DEBUG_KEYS:
        shown.pop(key, None)
    shown["days"] = _present_days(shown.get("days"), debug=False)

    budget = shown.get("budget_breakdown")
    if isinstance(budget, Mapping):
        budget_payload = dict(budget)
        budget_payload.pop("routing_confidence", None)
        shown["budget_breakdown"] = budget_payload
    return shown


__all__ = ["present_itinerary"]
