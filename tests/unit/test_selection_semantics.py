"""Planning selection semantic guards."""

from __future__ import annotations

from app.domain.models import POI, TripConstraints, UserProfile
from app.domain.planning.selection import prepare_candidate_pool


def _poi(pid: str, name: str, *, source_category: str, themes: list[str] | None = None) -> POI:
    return POI(
        id=pid,
        name=name,
        city="Guiyang",
        source_category=source_category,
        themes=themes or [],
    )


def test_prepare_candidate_pool_drops_infrastructure_candidates():
    constraints = TripConstraints(city="Guiyang", days=2)
    profile = UserProfile(themes=["history"])
    candidates = [
        _poi("infra", "Museum Parking Lot", source_category="交通设施服务;停车场"),
        _poi("exp", "City Museum", source_category="风景名胜;博物馆", themes=["history"]),
        _poi("unknown", "Mystery Spot", source_category=""),
    ]

    unique, _daily_count, assumptions = prepare_candidate_pool(constraints, profile, candidates)

    assert [poi.id for poi in unique] == ["exp", "unknown"]
    assert any(item.startswith("semantic_filtered_infrastructure=") for item in assumptions)
    assert any(item.startswith("semantic_unknown_candidates=") for item in assumptions)

