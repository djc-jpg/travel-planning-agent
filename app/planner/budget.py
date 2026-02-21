"""Budget calculation utilities with realistic minimums."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from app.domain.models import Itinerary, TripConstraints, UserProfile

_DEFAULT_FOOD_MIN_PER_PERSON_PER_DAY = 60.0
_DEFAULT_TRANSPORT_PER_SEGMENT = {
    "walking": 0.0,
    "public_transit": 6.0,
    "taxi": 35.0,
    "driving": 20.0,
}
_DEFAULT_TRAVELERS_BY_TYPE = {
    "solo": 1,
    "couple": 2,
    "family": 3,
    "friends": 3,
    "elderly": 2,
}
_SOURCE_CONFIDENCE = {
    "verified": 0.95,
    "curated": 0.85,
    "heuristic": 0.55,
    "fallback": 0.40,
    "unknown": 0.30,
}
_CITY_TICKET_BASELINE = {
    "beijing": 35.0,
    "北京": 35.0,
    "shanghai": 45.0,
    "上海": 45.0,
    "guangzhou": 35.0,
    "广州": 35.0,
    "shenzhen": 40.0,
    "深圳": 40.0,
    "hangzhou": 30.0,
    "杭州": 30.0,
    "chengdu": 30.0,
    "成都": 30.0,
    "chongqing": 28.0,
    "重庆": 28.0,
    "xian": 32.0,
    "西安": 32.0,
    "guiyang": 25.0,
    "贵阳": 25.0,
    "testcity": 20.0,
}
_LIKELY_PAID_TOKENS = (
    "museum",
    "博物馆",
    "寺",
    "祠",
    "塔",
    "乐园",
    "景区",
    "遗址",
    "动物园",
    "演出",
)
_LIKELY_FREE_TOKENS = (
    "park",
    "公园",
    "湖",
    "江",
    "河",
    "步行街",
    "广场",
    "walk",
)


def _food_min_per_person_per_day() -> float:
    raw = os.getenv("FOOD_MIN_PER_PERSON_PER_DAY", "").strip()
    if not raw:
        return _DEFAULT_FOOD_MIN_PER_PERSON_PER_DAY
    try:
        val = float(raw)
    except ValueError:
        return _DEFAULT_FOOD_MIN_PER_PERSON_PER_DAY
    return max(30.0, val)


def resolve_travelers_count(constraints: TripConstraints, profile: UserProfile) -> int:
    if constraints.travelers_count and constraints.travelers_count > 0:
        return constraints.travelers_count
    return _DEFAULT_TRAVELERS_BY_TYPE.get(profile.travelers_type.value, 2)


def _normalize_source_type(raw: str | None) -> str:
    text = str(raw or "").strip().lower()
    if not text:
        return "unknown"
    if "verified" in text or text in {"official", "real"}:
        return "verified"
    if "curated" in text or text in {"data", "tool_data"} or text.startswith("poi_"):
        return "curated"
    if "fallback" in text:
        return "fallback"
    if "heuristic" in text or text in {"estimate", "mock"}:
        return "heuristic"
    if "unknown" in text:
        return "unknown"
    return "heuristic"


def _ticket_source_hint(item) -> str:
    sources = getattr(item.poi, "fact_sources", {}) or {}
    source_hint = sources.get("ticket_price_source_type") or sources.get("ticket_price")
    if source_hint:
        return _normalize_source_type(str(source_hint))

    metadata_source = str(getattr(item.poi, "metadata_source", "") or "").lower()
    if "llm" in metadata_source:
        return "unknown"
    if metadata_source:
        return "heuristic"
    return "unknown"


def _city_ticket_baseline(city: str) -> float:
    normalized = str(city or "").strip().lower()
    return _CITY_TICKET_BASELINE.get(normalized, 25.0)


def _compose_poi_text(item) -> str:
    poi = item.poi
    values = [
        str(getattr(poi, "name", "") or ""),
        str(getattr(poi, "source_category", "") or ""),
        " ".join(str(theme) for theme in getattr(poi, "themes", []) or []),
    ]
    return " ".join(values).lower()


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def _inferred_ticket_price(item, *, city: str, source_type: str) -> float:
    if source_type in {"verified", "curated"}:
        return 0.0

    text = _compose_poi_text(item)
    if _contains_any(text, _LIKELY_FREE_TOKENS):
        return 0.0

    baseline = _city_ticket_baseline(city)
    if _contains_any(text, _LIKELY_PAID_TOKENS):
        return baseline
    return round(baseline * 0.5, 2)


def _resolve_ticket_price(item, *, city: str) -> tuple[float, str]:
    observed = max(item.poi.ticket_price, item.poi.cost, 0.0)
    source_type = _ticket_source_hint(item)
    if observed > 0:
        return observed, source_type

    inferred = _inferred_ticket_price(item, city=city, source_type=source_type)
    if inferred > 0:
        return inferred, "heuristic"
    return 0.0, source_type


def _persist_ticket_source(item, source_type: str) -> None:
    normalized = _normalize_source_type(source_type)
    fact_sources = dict(getattr(item.poi, "fact_sources", {}) or {})
    fact_sources["ticket_price_source_type"] = normalized
    fact_sources.setdefault("ticket_price", normalized)
    item.poi.fact_sources = fact_sources


def _backfill_missing_ticket_price(item, *, ticket_price: float, source_type: str) -> float:
    observed = max(item.poi.ticket_price, item.poi.cost, 0.0)
    if observed > 0:
        _persist_ticket_source(item, source_type)
        return observed
    if ticket_price <= 0:
        _persist_ticket_source(item, source_type)
        return 0.0

    rounded = round(ticket_price, 2)
    item.poi.ticket_price = rounded
    item.poi.cost = rounded
    _persist_ticket_source(item, source_type)
    return rounded


def _weighted_source_summary(ticket_rows: list[tuple[str, float]]) -> tuple[str, float]:
    weighted_by_source: dict[str, float] = {}
    score_sum = 0.0
    weight_sum = 0.0

    for source, weight in ticket_rows:
        if weight <= 0:
            continue
        weighted_by_source[source] = weighted_by_source.get(source, 0.0) + weight
        score_sum += _SOURCE_CONFIDENCE.get(source, _SOURCE_CONFIDENCE["unknown"]) * weight
        weight_sum += weight

    if weight_sum <= 0:
        return "unknown", _SOURCE_CONFIDENCE["unknown"]
    dominant = max(weighted_by_source.items(), key=lambda row: row[1])[0]
    return dominant, (score_sum / weight_sum)


def _weighted_budget_confidence(component_weights: dict[str, float], component_scores: dict[str, float]) -> float:
    total_weight = sum(max(0.0, value) for value in component_weights.values())
    if total_weight <= 0:
        return _SOURCE_CONFIDENCE["heuristic"]

    weighted_sum = 0.0
    for key, weight in component_weights.items():
        weighted_sum += max(0.0, weight) * component_scores.get(key, _SOURCE_CONFIDENCE["unknown"])
    return weighted_sum / total_weight


def apply_realistic_budget(
    itinerary: Itinerary,
    constraints: TripConstraints,
    profile: UserProfile,
) -> None:
    mode = constraints.transport_mode.value
    travelers = resolve_travelers_count(constraints, profile)
    food_per_person = _food_min_per_person_per_day()
    transport_per_segment = _DEFAULT_TRANSPORT_PER_SEGMENT.get(mode, 8.0)

    ticket_total = 0.0
    transport_total = 0.0
    food_total = 0.0
    ticket_rows: list[tuple[str, float]] = []

    for day in itinerary.days:
        main = [item for item in day.schedule if not item.is_backup]
        segments = max(0, len(main) - 1)
        day_ticket_per_person = 0.0
        for item in main:
            ticket_price, source_type = _resolve_ticket_price(item, city=itinerary.city)
            effective_ticket = _backfill_missing_ticket_price(
                item,
                ticket_price=ticket_price,
                source_type=source_type,
            )
            weighted_price = effective_ticket * travelers
            day_ticket_per_person += effective_ticket
            ticket_rows.append((source_type, weighted_price))
        day_ticket = day_ticket_per_person * travelers
        if mode == "public_transit":
            day_transport = segments * transport_per_segment * travelers
        else:
            day_transport = segments * transport_per_segment
        day_food = food_per_person * travelers

        day.estimated_cost = round(day_ticket + day_transport + day_food, 2)
        ticket_total += day_ticket
        transport_total += day_transport
        food_total += day_food

    itinerary.total_cost = round(ticket_total + transport_total + food_total, 2)
    itinerary.minimum_feasible_budget = itinerary.total_cost
    itinerary.budget_breakdown = {
        "tickets": round(ticket_total, 2),
        "local_transport": round(transport_total, 2),
        "food_min": round(food_total, 2),
    }

    ticket_source, ticket_confidence = _weighted_source_summary(ticket_rows)
    source_breakdown = {
        "tickets": ticket_source,
        "local_transport": "heuristic",
        "food_min": "heuristic",
    }
    confidence_breakdown = {
        "tickets": round(ticket_confidence, 4),
        "local_transport": _SOURCE_CONFIDENCE["heuristic"],
        "food_min": _SOURCE_CONFIDENCE["heuristic"],
    }
    itinerary.budget_source_breakdown = source_breakdown
    itinerary.budget_confidence_breakdown = confidence_breakdown
    itinerary.budget_confidence_score = round(
        _weighted_budget_confidence(
            {
                "tickets": ticket_total,
                "local_transport": transport_total,
                "food_min": food_total,
            },
            confidence_breakdown,
        ),
        4,
    )
    itinerary.budget_as_of = datetime.now(timezone.utc).date().isoformat()

    budget_limit = 0.0
    if constraints.total_budget:
        budget_limit = constraints.total_budget
    elif constraints.budget_per_day:
        budget_limit = constraints.budget_per_day * constraints.days

    itinerary.budget_warning = ""
    if budget_limit and budget_limit < itinerary.minimum_feasible_budget:
        gap = round(itinerary.minimum_feasible_budget - budget_limit, 2)
        itinerary.budget_warning = (
            f"输入预算{budget_limit:.0f}元低于最低可行预算{itinerary.minimum_feasible_budget:.0f}元，"
            f"预算缺口约{gap:.0f}元。建议减少收费景点、压缩跨区交通或增加预算。"
        )
