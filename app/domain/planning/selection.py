"""POI selection helpers for itinerary planning."""

from __future__ import annotations

from datetime import date
from typing import Callable

from app.domain.constants import PACE_POI_COUNT
from app.domain.enums import PoiSemanticType
from app.domain.models import POI, TripConstraints, UserProfile
from app.domain.planning.day_template import infer_poi_activity_bucket
from app.domain.planning.preference_scoring import rerank_candidates_by_preference
from app.domain.poi_semantics import tag_poi_semantics
from app.domain.planning.ordering import nearest_neighbor_order
from app.domain.planning.persona import persona_limits, persona_name, persona_score

DistanceFn = Callable[[float, float, float, float], float]
CLUSTER_PRIORITY = ["central_axis", "imperial_garden", "temple", "old_city"]
_THEME_BUCKET_HINTS: dict[str, tuple[str, ...]] = {
    "food": (
        "food",
        "restaurant",
        "market",
        "\u7f8e\u98df",
        "\u591c\u5e02",
        "\u5c0f\u5403",
        "\u9910",
        "coffee",
        "\u5496\u5561",
    ),
    "night": ("night", "nightlife", "\u591c\u666f", "\u591c\u6e38", "\u706f\u5149"),
    "museum": ("museum", "gallery", "\u535a\u7269\u9986", "\u5c55\u89c8"),
    "nature": ("nature", "park", "garden", "\u81ea\u7136", "\u98ce\u5149", "\u516c\u56ed", "\u5c71", "\u6e56"),
    "landmark": ("landmark", "history", "\u5730\u6807", "\u53e4\u8ff9", "\u5386\u53f2"),
    "shopping": ("shopping", "mall", "\u8d2d\u7269", "\u5546\u573a"),
    "family": ("family", "kids", "\u4eb2\u5b50"),
}


def ticket_cost(poi: POI) -> float:
    return max(poi.ticket_price, poi.cost, 0.0)


def is_open_on_date(poi: POI, plan_date: date) -> bool:
    if not poi.closed_weekdays:
        return True
    return plan_date.weekday() not in set(poi.closed_weekdays)


def nearest_neighbor_sort(
    pois: list[POI],
    *,
    distance_fn: DistanceFn,
    start_lat: float = 0,
    start_lon: float = 0,
) -> list[POI]:
    return nearest_neighbor_order(
        pois,
        distance_fn=distance_fn,
        start_lat=start_lat,
        start_lon=start_lon,
    )


def cluster_day_plan(
    poi_candidates: list[POI],
    *,
    days: int,
    daily_count: int,
) -> list[list[POI]] | None:
    if not poi_candidates or not any(p.cluster for p in poi_candidates):
        return None

    groups: dict[str, list[POI]] = {}
    for poi in poi_candidates:
        key = poi.cluster or "misc"
        groups.setdefault(key, []).append(poi)

    ordered_clusters = [cluster for cluster in CLUSTER_PRIORITY if cluster in groups]
    ordered_clusters += sorted(cluster for cluster in groups if cluster not in ordered_clusters)

    ordered_pois: list[POI] = []
    for cluster in ordered_clusters:
        ordered_pois.extend(groups[cluster])

    buckets: list[list[POI]] = [[] for _ in range(days)]
    cursor = 0
    for day_idx in range(days):
        if cursor >= len(ordered_pois):
            break
        remaining = len(ordered_pois) - cursor
        remaining_days = days - day_idx
        target = min(daily_count, max(1, (remaining + remaining_days - 1) // remaining_days))
        buckets[day_idx] = ordered_pois[cursor : cursor + target]
        cursor += target
    return buckets


def top_up_day_pois(
    day_pois: list[POI],
    *,
    all_pois: list[POI],
    used_ids: set[str],
    plan_date: date,
    daily_count: int,
    preferred_clusters: set[str] | None = None,
    cluster_lookup: dict[str, str] | None = None,
) -> list[POI]:
    if len(day_pois) >= daily_count:
        return day_pois[:daily_count]

    selected = list(day_pois)
    selected_ids = {poi.id for poi in selected}
    candidates = list(all_pois)
    if preferred_clusters and cluster_lookup:
        preferred = [
            poi
            for poi in all_pois
            if cluster_lookup.get(poi.id, "geo:0") in preferred_clusters
        ]
        fallback = [
            poi
            for poi in all_pois
            if cluster_lookup.get(poi.id, "geo:0") not in preferred_clusters
        ]
        candidates = preferred + fallback
    for poi in candidates:
        if poi.id in used_ids or poi.id in selected_ids:
            continue
        if not is_open_on_date(poi, plan_date):
            continue
        selected.append(poi)
        selected_ids.add(poi.id)
        if len(selected) >= daily_count:
            break
    return selected


def _semantic_weight(poi: POI) -> int:
    if poi.semantic_type == PoiSemanticType.EXPERIENCE:
        return 2
    if poi.semantic_type == PoiSemanticType.UNKNOWN:
        return 1
    return 0


def _sanitize_candidates(poi_candidates: list[POI]) -> tuple[list[POI], int]:
    unique: list[POI] = []
    seen_ids: set[str] = set()
    dropped_infrastructure = 0
    for poi in poi_candidates:
        tagged = tag_poi_semantics(poi)
        if tagged.id in seen_ids:
            continue
        seen_ids.add(tagged.id)
        if tagged.semantic_type == PoiSemanticType.INFRASTRUCTURE:
            dropped_infrastructure += 1
            continue
        unique.append(tagged)
    return unique, dropped_infrastructure


def _desired_theme_buckets(profile: UserProfile) -> list[str]:
    buckets: list[str] = []
    for raw in profile.themes:
        text = str(raw).strip().lower()
        if not text:
            continue
        for bucket, hints in _THEME_BUCKET_HINTS.items():
            if any(hint and hint in text for hint in hints):
                if bucket not in buckets:
                    buckets.append(bucket)
                break
    return buckets


def _promote_theme_coverage(
    pois: list[POI],
    *,
    profile: UserProfile,
    daily_count: int,
    locked_names: set[str] | None = None,
) -> tuple[list[POI], list[str]]:
    desired = _desired_theme_buckets(profile)
    if not desired or len(pois) <= 1:
        return pois, []

    locked = locked_names or set()
    window = min(len(pois), max(3, daily_count))
    ordered = list(pois)
    assumptions: list[str] = []

    for bucket in desired:
        if any(infer_poi_activity_bucket(poi) == bucket for poi in ordered[:window]):
            continue
        src_idx = next(
            (
                idx
                for idx in range(window, len(ordered))
                if infer_poi_activity_bucket(ordered[idx]) == bucket
                and ordered[idx].name not in locked
            ),
            None,
        )
        if src_idx is None:
            continue
        dst_idx = next(
            (
                idx
                for idx in range(window - 1, -1, -1)
                if ordered[idx].name not in locked
                and infer_poi_activity_bucket(ordered[idx]) != bucket
            ),
            None,
        )
        if dst_idx is None:
            continue
        ordered[dst_idx], ordered[src_idx] = ordered[src_idx], ordered[dst_idx]
        assumptions.append(f"theme_promoted_{bucket}=true")
    return ordered, assumptions


def prepare_candidate_pool(
    constraints: TripConstraints,
    profile: UserProfile,
    poi_candidates: list[POI],
) -> tuple[list[POI], int, list[str]]:
    daily_count = PACE_POI_COUNT.get(constraints.pace, 3)
    assumptions: list[str] = []

    unique, dropped_infrastructure = _sanitize_candidates(poi_candidates)
    if dropped_infrastructure > 0:
        assumptions.append(f"semantic_filtered_infrastructure={dropped_infrastructure}")

    avoid_terms = [term.strip().lower() for term in constraints.avoid if term.strip()]
    if avoid_terms:
        filtered = [
            poi
            for poi in unique
            if not any(term in poi.name.lower() for term in avoid_terms)
        ]
        removed = len(unique) - len(filtered)
        if filtered:
            unique = filtered
            assumptions.append(f"avoid_filtered={removed}")
        elif removed > 0:
            assumptions.append("avoid_filter_exhausted_keep_original")

    unique = rerank_candidates_by_preference(
        unique,
        constraints=constraints,
        profile=profile,
        extra_weight_fn=lambda poi: (_semantic_weight(poi) + persona_score(poi, profile)),
    )
    unique, promoted = _promote_theme_coverage(
        unique,
        profile=profile,
        daily_count=daily_count,
    )
    assumptions.append("preference_reranked=true")
    assumptions.extend(promoted)

    if constraints.free_only:
        free_only = [poi for poi in unique if ticket_cost(poi) <= 0]
        if free_only:
            unique = free_only
            assumptions.append("已按免费景点约束过滤候选点")
        else:
            assumptions.append("未找到完全免费景点，保留最低门票方案")

    unknown_count = sum(1 for poi in unique if poi.semantic_type == PoiSemanticType.UNKNOWN)
    if unknown_count > 0:
        assumptions.append(f"semantic_unknown_candidates={unknown_count}")

    must_visit_names = [name.strip() for name in constraints.must_visit if name.strip()]
    if must_visit_names:
        must_lookup = set(must_visit_names)
        must = [poi for poi in unique if poi.name in must_lookup]
        others = [poi for poi in unique if poi.name not in must_lookup]
        unique = must + others

        missing = [name for name in must_visit_names if name not in {poi.name for poi in must}]
        if missing:
            assumptions.append("未命中必去景点: " + "、".join(missing))
        if constraints.days <= 2 and must:
            daily_count = min(daily_count, max(3, len(must)))
        unique, promoted_with_lock = _promote_theme_coverage(
            unique,
            profile=profile,
            daily_count=daily_count,
            locked_names={name for name in must_visit_names if name},
        )
        assumptions.extend(promoted_with_lock)

    max_pois, _max_daily_minutes = persona_limits(profile)
    daily_count = max(1, min(daily_count, max_pois))
    assumptions.append(f"persona={persona_name(profile)} max_pois={max_pois}")

    return unique, daily_count, assumptions


__all__ = [
    "DistanceFn",
    "cluster_day_plan",
    "is_open_on_date",
    "nearest_neighbor_sort",
    "prepare_candidate_pool",
    "ticket_cost",
    "top_up_day_pois",
]
