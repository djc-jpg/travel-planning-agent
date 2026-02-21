"""Preference-driven ranking regression tests."""

from __future__ import annotations

from app.domain.models import POI, TripConstraints, UserProfile
from app.domain.planning.day_template import infer_poi_activity_bucket
from app.domain.planning.selection import prepare_candidate_pool


def _poi(
    pid: str,
    name: str,
    *,
    themes: list[str],
) -> POI:
    return POI(
        id=pid,
        name=name,
        city="demo",
        themes=themes,
        duration_hours=1.5,
        source_category="scenic",
        open_time="09:00-20:00",
    )


def test_preference_change_reorders_top_candidates():
    constraints = TripConstraints(city="demo", days=1)
    candidates = [
        _poi("m1", "city history museum", themes=["history", "museum"]),
        _poi("f1", "old street food market", themes=["food"]),
        _poi("n1", "riverside park", themes=["nature"]),
    ]

    history_profile = UserProfile(themes=["history"])
    food_profile = UserProfile(themes=["food"])

    history_ranked, _daily_count, _assumptions = prepare_candidate_pool(
        constraints,
        history_profile,
        candidates,
    )
    food_ranked, _daily_count2, _assumptions2 = prepare_candidate_pool(
        constraints,
        food_profile,
        candidates,
    )

    assert history_ranked[0].id == "m1"
    assert food_ranked[0].id == "f1"
    assert history_ranked[0].id != food_ranked[0].id


def test_preference_ranking_adds_diversity_in_front_slice():
    constraints = TripConstraints(city="demo", days=1)
    profile = UserProfile(themes=["history"])
    candidates = [
        _poi("m1", "history museum a", themes=["history", "museum"]),
        _poi("m2", "history museum b", themes=["history", "museum"]),
        _poi("m3", "history museum c", themes=["history", "museum"]),
        _poi("p1", "central park", themes=["nature"]),
    ]

    ranked, _daily_count, assumptions = prepare_candidate_pool(constraints, profile, candidates)
    top3 = [poi.id for poi in ranked[:3]]

    assert "p1" in top3
    assert "preference_reranked=true" in assumptions


def test_theme_coverage_promotes_food_when_user_requests_food_and_night():
    constraints = TripConstraints(city="demo", days=2)
    profile = UserProfile(
        themes=[
            "\u81ea\u7136\u98ce\u5149",
            "\u7f8e\u98df\u591c\u5e02",
        ]
    )
    candidates = [
        _poi("n1", "mountain park", themes=["nature"]),
        _poi("n2", "lake park", themes=["nature"]),
        _poi("n3", "city garden", themes=["nature"]),
        _poi("f1", "night food market", themes=["food", "night"]),
    ]

    ranked, daily_count, assumptions = prepare_candidate_pool(constraints, profile, candidates)
    front_slice = ranked[: max(3, daily_count)]
    front_buckets = {infer_poi_activity_bucket(poi) for poi in front_slice}

    assert "food" in front_buckets or "night" in front_buckets
    assert "preference_reranked=true" in assumptions
