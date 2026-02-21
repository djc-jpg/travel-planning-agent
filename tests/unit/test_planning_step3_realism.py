"""Step3 realism tests: routing model, persona parameters, fact confidence."""

from __future__ import annotations

from datetime import date, datetime

from app.domain.enums import Pace, TravelersType
from app.domain.models import POI, TripConstraints, UserProfile
from app.domain.planning.constraints import ConstraintEngine
from app.domain.planning.fact_confidence import annotate_poi_fact_confidence
from app.domain.planning.postprocess import generate_itinerary_impl
from app.domain.planning.selection import prepare_candidate_pool
from app.planner.routing_provider import FixtureRoutingProvider


def _poi(
    pid: str,
    *,
    city: str = "北京",
    cluster: str = "central_axis",
    duration_hours: float = 1.5,
) -> POI:
    return POI(
        id=pid,
        name=f"poi-{pid}",
        city=city,
        lat=39.90 + int(pid[-1]) * 0.01 if pid[-1].isdigit() else 39.90,
        lon=116.40 + int(pid[-1]) * 0.01 if pid[-1].isdigit() else 116.40,
        cluster=cluster,
        duration_hours=duration_hours,
        cost=30.0,
        ticket_price=30.0,
        open_time="09:00-20:00",
        open_hours="09:00-20:00",
        fact_sources={
            "ticket_price": "data",
            "reservation_required": "unknown",
            "open_hours": "data",
            "closed_rules": "unknown",
        },
    )


def test_fixture_routing_peak_factor_and_confidence():
    provider = FixtureRoutingProvider()
    origin = _poi("p1")
    destination = _poi("p2")
    peak = provider.get_travel_time(origin, destination, "public_transit", departure_time=datetime(2026, 5, 1, 8, 0))
    offpeak = provider.get_travel_time(origin, destination, "public_transit", departure_time=datetime(2026, 5, 1, 13, 0))
    confidence = provider.get_confidence(origin, destination, "public_transit", departure_time=datetime(2026, 5, 1, 8, 0))
    assert peak >= offpeak
    assert 0.3 <= confidence <= 0.98


def test_persona_limits_and_constraints_override():
    constraints = TripConstraints(city="北京", days=2, pace=Pace.INTENSIVE)
    profile = UserProfile(travelers_type=TravelersType.ELDERLY)
    candidates = [_poi(f"p{i}") for i in range(8)]
    _unique, daily_count, assumptions = prepare_candidate_pool(constraints, profile, candidates)
    assert daily_count <= 4
    assert any("persona=elderly" in row for row in assumptions)

    itinerary = generate_itinerary_impl(constraints, profile, candidates)
    violations = ConstraintEngine.default(profile=profile).evaluate(itinerary, constraints)
    codes = {row.code for row in violations}
    assert "INTENSITY_OVERLOAD" not in codes


def test_fact_confidence_annotations_are_present():
    poi = _poi("p1")
    annotated = annotate_poi_fact_confidence(poi)
    facts = annotated.fact_sources
    assert facts["ticket_price_source_type"] == "data"
    assert facts["reservation_required_source_type"] == "unknown"
    assert "ticket_price_field_confidence" in facts
    assert "open_hours_field_confidence" in facts


def test_generate_impl_emits_routing_confidence_signal():
    constraints = TripConstraints(city="北京", days=2, pace=Pace.MODERATE)
    profile = UserProfile(travelers_type=TravelersType.FRIENDS)
    itinerary = generate_itinerary_impl(constraints, profile, [_poi(f"p{i}") for i in range(7)])
    assert "routing_confidence" in itinerary.budget_breakdown
    assert any("routing_confidence=" in row for row in itinerary.assumptions)
    notes = [item.notes for day in itinerary.days for item in day.schedule if not item.is_backup]
    assert any("routing_confidence=" in str(note) for note in notes)


def test_generate_impl_avoids_cross_day_duplicates_when_pool_sufficient():
    constraints = TripConstraints(
        city="beijing",
        days=2,
        pace=Pace.MODERATE,
        date_start=date(2026, 4, 6),  # Monday
    )
    profile = UserProfile(travelers_type=TravelersType.COUPLE)
    candidates = [_poi(f"p{i}") for i in range(1, 8)]
    for poi in candidates[:3]:
        poi.closed_weekdays = [0]

    itinerary = generate_itinerary_impl(
        constraints,
        profile,
        candidates,
        routing_provider=FixtureRoutingProvider(),
    )
    names = [
        item.poi.name
        for day in itinerary.days
        for item in day.schedule
        if not item.is_backup
    ]
    assert len(names) >= 4
    assert len(names) == len(set(names))
