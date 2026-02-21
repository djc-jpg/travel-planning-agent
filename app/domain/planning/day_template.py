"""Day template helpers to keep itinerary structure human-like."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import Pace
from app.domain.models import POI, TripConstraints, UserProfile

_FOOD_THEME_TOKENS = {
    "food",
    "snack",
    "restaurant",
    "\u7f8e\u98df",
    "\u591c\u5e02",
    "\u5c0f\u5403",
    "\u9910\u996e",
    "\u5403",
}
_NIGHT_THEME_TOKENS = {
    "night",
    "nightlife",
    "\u591c\u666f",
    "\u591c\u6e38",
    "\u706f\u5149",
    "\u4e0d\u591c\u57ce",
}
_BUCKET_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("food", ("food", "restaurant", "market", "snack", "night market", "\u7f8e\u98df", "\u591c\u5e02", "\u5c0f\u5403", "\u9910\u5385", "\u9910\u996e")),
    ("night", ("night", "nightlife", "bar", "night view", "\u591c\u666f", "\u591c\u6e38", "\u9152\u5427", "\u706f\u5149", "\u4e0d\u591c")),
    ("museum", ("museum", "gallery", "exhibition", "history", "\u535a\u7269\u9986", "\u7f8e\u672f\u9986", "\u5c55\u89c8", "\u5386\u53f2\u9986")),
    ("nature", ("park", "garden", "lake", "mountain", "scenic", "\u81ea\u7136", "\u516c\u56ed", "\u56ed\u6797", "\u666f\u533a", "\u6e56", "\u5c71")),
    ("shopping", ("shopping", "mall", "outlet", "\u5546\u573a", "\u8d2d\u7269", "\u6b65\u884c\u8857")),
    ("landmark", ("landmark", "tower", "monument", "square", "\u5730\u6807", "\u5e7f\u573a", "\u53e4\u8ff9", "\u5854")),
)


@dataclass(frozen=True)
class DayTemplate:
    min_unique_buckets: int
    prefer_food: bool
    prefer_night: bool


def _tokens(profile: UserProfile) -> set[str]:
    return {str(theme).strip().lower() for theme in profile.themes if str(theme).strip()}


def _has_theme_signal(themes: set[str], token_set: set[str]) -> bool:
    if not themes:
        return False
    return any(any(token in theme for token in token_set) for theme in themes)


def infer_poi_activity_bucket(poi: POI) -> str:
    text = " ".join([poi.name, poi.description, " ".join(poi.themes)]).lower()
    for bucket, keywords in _BUCKET_KEYWORDS:
        if any(keyword.lower() in text for keyword in keywords):
            return bucket
    return "general"


def resolve_day_template(
    constraints: TripConstraints,
    profile: UserProfile,
    *,
    daily_count: int,
) -> DayTemplate:
    min_unique = 2
    if constraints.pace == Pace.INTENSIVE and daily_count >= 4:
        min_unique = 3
    if constraints.pace == Pace.MODERATE and daily_count >= 3:
        min_unique = 2
    if constraints.pace == Pace.RELAXED:
        min_unique = 2

    themes = _tokens(profile)
    prefer_food = _has_theme_signal(themes, _FOOD_THEME_TOKENS)
    prefer_night = _has_theme_signal(themes, _NIGHT_THEME_TOKENS)
    return DayTemplate(min_unique_buckets=min_unique, prefer_food=prefer_food, prefer_night=prefer_night)


def _bucket_counts(pois: list[POI]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for poi in pois:
        bucket = infer_poi_activity_bucket(poi)
        counts[bucket] = counts.get(bucket, 0) + 1
    return counts


def _pick_replacement_index(selected: list[POI]) -> int:
    counts = _bucket_counts(selected)
    if not counts:
        return 0
    bucket, count = max(counts.items(), key=lambda item: item[1])
    if count <= 1:
        return len(selected) - 1
    for idx, poi in enumerate(selected):
        if infer_poi_activity_bucket(poi) == bucket:
            return idx
    return len(selected) - 1


def _candidate_pool(
    all_pois: list[POI],
    *,
    selected: list[POI],
    used_ids: set[str],
    locked_names: set[str],
) -> list[POI]:
    selected_ids = {poi.id for poi in selected}
    rows: list[POI] = []
    for poi in all_pois:
        if poi.id in selected_ids or poi.id in used_ids:
            continue
        if poi.name in locked_names:
            continue
        rows.append(poi)
    return rows


def _enforce_min_diversity(
    selected: list[POI],
    *,
    pool: list[POI],
    min_unique_buckets: int,
    assumptions: list[str],
) -> None:
    if len(selected) <= 1:
        return
    while len({infer_poi_activity_bucket(poi) for poi in selected}) < min_unique_buckets:
        existing = {infer_poi_activity_bucket(poi) for poi in selected}
        replacement = next((poi for poi in pool if infer_poi_activity_bucket(poi) not in existing), None)
        if replacement is None:
            break
        idx = _pick_replacement_index(selected)
        prev = selected[idx]
        selected[idx] = replacement
        pool.remove(replacement)
        assumptions.append(f"day_template_diversity:{prev.name}->{replacement.name}")


def _enforce_bucket(
    selected: list[POI],
    *,
    pool: list[POI],
    target_bucket: str,
    assumption_key: str,
    assumptions: list[str],
) -> None:
    if any(infer_poi_activity_bucket(poi) == target_bucket for poi in selected):
        return
    replacement = next((poi for poi in pool if infer_poi_activity_bucket(poi) == target_bucket), None)
    if replacement is None:
        return
    idx = _pick_replacement_index(selected)
    prev = selected[idx]
    selected[idx] = replacement
    pool.remove(replacement)
    assumptions.append(f"{assumption_key}:{prev.name}->{replacement.name}")


def rebalance_day_pois(
    day_pois: list[POI],
    *,
    all_pois: list[POI],
    used_ids: set[str],
    template: DayTemplate,
    must_visit_names: set[str] | None = None,
) -> tuple[list[POI], list[str]]:
    if not day_pois:
        return [], []
    assumptions: list[str] = []
    locked = {name for name in (must_visit_names or set()) if name}
    selected = list(day_pois)
    pool = _candidate_pool(all_pois, selected=selected, used_ids=used_ids, locked_names=locked)

    _enforce_min_diversity(
        selected,
        pool=pool,
        min_unique_buckets=min(template.min_unique_buckets, len(selected)),
        assumptions=assumptions,
    )
    if template.prefer_food:
        _enforce_bucket(
            selected,
            pool=pool,
            target_bucket="food",
            assumption_key="day_template_food",
            assumptions=assumptions,
        )
    if template.prefer_night:
        _enforce_bucket(
            selected,
            pool=pool,
            target_bucket="night",
            assumption_key="day_template_night",
            assumptions=assumptions,
        )
    return selected, assumptions


__all__ = ["DayTemplate", "infer_poi_activity_bucket", "rebalance_day_pois", "resolve_day_template"]
