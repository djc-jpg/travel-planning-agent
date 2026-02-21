"""Application service for trip planning use-cases."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from app.application.context import AppContext
from app.application.contracts import TripRequest, TripResult
from app.application.plan_trip import plan_trip
from app.services.itinerary_presenter import present_itinerary

_MACHINE_MESSAGE_HINTS = re.compile(
    r"(executable itinerary|day\d+\s*:|cluster=|routing_confidence=)",
    re.IGNORECASE,
)


def _normalize_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    return dict(value)


def _with_presented_itinerary(result: TripResult, *, debug: bool) -> TripResult:
    if result.itinerary is None:
        return result
    presented = present_itinerary(result.itinerary, debug=debug)
    return result.model_copy(update={"itinerary": presented}, deep=True)


def _normalize_user_message(result: TripResult) -> TripResult:
    raw = str(result.message or "").strip()
    has_itinerary = result.itinerary is not None
    if not raw:
        default_message = "行程已生成，可在下方查看每天安排。" if has_itinerary else ""
        return result.model_copy(update={"message": default_message})
    if _MACHINE_MESSAGE_HINTS.search(raw):
        normalized = "行程已生成，可在下方查看每天安排。" if has_itinerary else "已收到需求，正在生成行程。"
        return result.model_copy(update={"message": normalized})
    return result


def execute_plan(
    *,
    ctx: AppContext,
    message: str,
    session_id: str | None = None,
    constraints: Mapping[str, Any] | None = None,
    user_profile: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    debug: bool = False,
) -> TripResult:
    trip_req = TripRequest(
        message=message,
        session_id=session_id,
        constraints=_normalize_mapping(constraints),
        user_profile=_normalize_mapping(user_profile),
        metadata=_normalize_mapping(metadata),
    )
    result = plan_trip(trip_req, ctx)
    presented = _with_presented_itinerary(result, debug=debug)
    return _normalize_user_message(presented)


__all__ = ["execute_plan"]
