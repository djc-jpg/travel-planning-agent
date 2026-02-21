"""Preference scoring helpers for POI ranking."""

from __future__ import annotations

from collections.abc import Callable

from app.domain.enums import TransportMode, TravelersType
from app.domain.models import POI, TripConstraints, UserProfile
from app.domain.planning.day_template import infer_poi_activity_bucket

_THEME_ALIASES: dict[str, set[str]] = {
    "history": {"history", "historical", "museum", "古迹", "历史", "博物馆"},
    "museum": {"museum", "gallery", "博物馆", "美术馆", "展览"},
    "food": {"food", "restaurant", "market", "美食", "夜市", "小吃", "餐饮"},
    "night": {"night", "bar", "nightlife", "夜景", "灯光", "不夜"},
    "nature": {"nature", "park", "garden", "lake", "自然", "公园", "园林"},
    "landmark": {"landmark", "tower", "monument", "地标", "广场"},
    "shopping": {"shopping", "mall", "outlet", "购物", "商场", "步行街"},
    "family": {"family", "kids", "亲子", "儿童", "动物园", "乐园"},
}


def _normalized(value: str) -> str:
    return value.strip().lower()


def _poi_text_blob(poi: POI) -> str:
    return " ".join(
        [
            poi.name or "",
            poi.description or "",
            " ".join(poi.themes),
        ]
    ).lower()


def _expanded_terms(theme: str) -> set[str]:
    key = _normalized(theme)
    terms = {key}
    if key in _THEME_ALIASES:
        terms.update(_THEME_ALIASES[key])
    return terms


def _theme_match_score(poi: POI, profile: UserProfile) -> float:
    if not profile.themes:
        return 0.0
    text = _poi_text_blob(poi)
    score = 0.0
    for raw_theme in profile.themes:
        terms = _expanded_terms(str(raw_theme))
        if any(term and term in text for term in terms):
            score += 1.0
    return score


def _traveler_adjustment(poi: POI, profile: UserProfile) -> float:
    if profile.travelers_type == TravelersType.FAMILY:
        text = _poi_text_blob(poi)
        if any(token in text for token in _THEME_ALIASES["family"]):
            return 0.4
    if profile.travelers_type == TravelersType.ELDERLY and poi.duration_hours > 2.5:
        return -0.3
    return 0.0


def _transport_adjustment(poi: POI, constraints: TripConstraints) -> float:
    if constraints.transport_mode == TransportMode.WALKING and poi.duration_hours > 2.5:
        return -0.3
    if constraints.transport_mode == TransportMode.PUBLIC_TRANSIT:
        bucket = infer_poi_activity_bucket(poi)
        if bucket in {"landmark", "museum", "food"}:
            return 0.1
    return 0.0


def compute_poi_preference_score(
    poi: POI,
    *,
    constraints: TripConstraints,
    profile: UserProfile,
) -> float:
    return (
        _theme_match_score(poi, profile)
        + _traveler_adjustment(poi, profile)
        + _transport_adjustment(poi, constraints)
    )


def diversity_adjustment(bucket: str, bucket_counts: dict[str, int]) -> float:
    seen = bucket_counts.get(bucket, 0)
    if seen == 0:
        return 0.5
    return -0.5 * float(seen)


def rerank_candidates_by_preference(
    pois: list[POI],
    *,
    constraints: TripConstraints,
    profile: UserProfile,
    extra_weight_fn: Callable[[POI], float] | None = None,
) -> list[POI]:
    if len(pois) <= 1:
        return list(pois)

    extra = extra_weight_fn or (lambda _poi: 0.0)
    remaining = list(pois)
    ordered: list[POI] = []
    bucket_counts: dict[str, int] = {}

    while remaining:
        best_idx = 0
        best_score = float("-inf")
        for idx, poi in enumerate(remaining):
            bucket = infer_poi_activity_bucket(poi)
            score = (
                compute_poi_preference_score(
                    poi,
                    constraints=constraints,
                    profile=profile,
                )
                + extra(poi)
                + diversity_adjustment(bucket, bucket_counts)
            )
            if score > best_score:
                best_score = score
                best_idx = idx

        chosen = remaining.pop(best_idx)
        ordered.append(chosen)
        chosen_bucket = infer_poi_activity_bucket(chosen)
        bucket_counts[chosen_bucket] = bucket_counts.get(chosen_bucket, 0) + 1
    return ordered


__all__ = [
    "compute_poi_preference_score",
    "diversity_adjustment",
    "rerank_candidates_by_preference",
]
