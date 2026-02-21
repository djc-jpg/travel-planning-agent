"""Budget provenance and confidence tests."""

from __future__ import annotations

import re

from app.domain.models import Itinerary, ItineraryDay, POI, ScheduleItem, TripConstraints, UserProfile
from app.planner.budget import apply_realistic_budget


def _make_item(
    poi_id: str,
    *,
    ticket_price: float,
    source_type: str | None,
    metadata_source: str = "tool_data",
    name: str | None = None,
    themes: list[str] | None = None,
) -> ScheduleItem:
    fact_sources = {}
    if source_type is not None:
        fact_sources["ticket_price_source_type"] = source_type
    poi = POI(
        id=poi_id,
        name=name or f"poi-{poi_id}",
        city="成都",
        ticket_price=ticket_price,
        cost=ticket_price,
        metadata_source=metadata_source,
        fact_sources=fact_sources,
        themes=themes or [],
    )
    return ScheduleItem(poi=poi, is_backup=False)


def _base_constraints(*, budget_per_day: float) -> TripConstraints:
    return TripConstraints(
        city="成都",
        days=1,
        budget_per_day=budget_per_day,
        transport_mode="public_transit",
    )


def _profile() -> UserProfile:
    return UserProfile(travelers_type="couple")


def test_budget_metadata_prefers_verified_ticket_sources():
    itinerary = Itinerary(
        city="成都",
        days=[
            ItineraryDay(
                day_number=1,
                schedule=[
                    _make_item("a", ticket_price=120.0, source_type="verified"),
                    _make_item("b", ticket_price=80.0, source_type="verified"),
                ],
            )
        ],
    )

    apply_realistic_budget(itinerary, _base_constraints(budget_per_day=1000), _profile())

    assert itinerary.budget_source_breakdown["tickets"] == "verified"
    assert itinerary.budget_confidence_breakdown["tickets"] >= 0.9
    assert itinerary.budget_confidence_score > 0.7
    assert re.match(r"^20\d{2}-\d{2}-\d{2}$", itinerary.budget_as_of)


def test_budget_metadata_marks_missing_ticket_sources_as_unknown():
    itinerary = Itinerary(
        city="成都",
        days=[
            ItineraryDay(
                day_number=1,
                schedule=[
                    _make_item("a", ticket_price=120.0, source_type=None, metadata_source=""),
                    _make_item("b", ticket_price=80.0, source_type=None, metadata_source=""),
                ],
            )
        ],
    )

    apply_realistic_budget(itinerary, _base_constraints(budget_per_day=1000), _profile())

    assert itinerary.budget_source_breakdown["tickets"] == "unknown"
    assert itinerary.budget_confidence_breakdown["tickets"] <= 0.35
    assert itinerary.budget_confidence_score < 0.6


def test_budget_warning_kept_when_budget_below_minimum_feasible():
    itinerary = Itinerary(
        city="成都",
        days=[
            ItineraryDay(
                day_number=1,
                schedule=[
                    _make_item("a", ticket_price=200.0, source_type="verified"),
                    _make_item("b", ticket_price=180.0, source_type="verified"),
                ],
            )
        ],
    )

    apply_realistic_budget(itinerary, _base_constraints(budget_per_day=100), _profile())

    assert itinerary.minimum_feasible_budget > 0
    assert "预算缺口" in itinerary.budget_warning


def test_budget_estimates_unknown_ticket_for_paid_like_poi():
    itinerary = Itinerary(
        city="杭州",
        days=[
            ItineraryDay(
                day_number=1,
                schedule=[
                    _make_item(
                        "a",
                        ticket_price=0.0,
                        source_type=None,
                        metadata_source="",
                        name="杭州博物馆",
                        themes=["历史", "博物馆"],
                    ),
                ],
            )
        ],
    )

    apply_realistic_budget(itinerary, _base_constraints(budget_per_day=1000), _profile())

    assert itinerary.budget_breakdown["tickets"] >= 60.0
    assert itinerary.budget_source_breakdown["tickets"] == "heuristic"
    assert itinerary.budget_confidence_breakdown["tickets"] >= 0.5


def test_budget_backfills_missing_poi_ticket_price_when_inferred():
    itinerary = Itinerary(
        city="hangzhou",
        days=[
            ItineraryDay(
                day_number=1,
                schedule=[
                    _make_item(
                        "a",
                        ticket_price=0.0,
                        source_type=None,
                        metadata_source="",
                        name="hangzhou museum",
                        themes=["history", "museum"],
                    ),
                ],
            )
        ],
    )

    apply_realistic_budget(itinerary, _base_constraints(budget_per_day=1000), _profile())

    poi = itinerary.days[0].schedule[0].poi
    assert poi.ticket_price > 0
    assert poi.cost == poi.ticket_price
    assert poi.fact_sources.get("ticket_price_source_type") == "heuristic"


def test_budget_keeps_unknown_free_nature_poi_zero_ticket():
    itinerary = Itinerary(
        city="杭州",
        days=[
            ItineraryDay(
                day_number=1,
                schedule=[
                    _make_item(
                        "a",
                        ticket_price=0.0,
                        source_type=None,
                        metadata_source="",
                        name="西湖公园",
                        themes=["自然"],
                    ),
                ],
            )
        ],
    )

    apply_realistic_budget(itinerary, _base_constraints(budget_per_day=1000), _profile())

    assert itinerary.budget_breakdown["tickets"] == 0.0
    assert itinerary.budget_source_breakdown["tickets"] == "unknown"
