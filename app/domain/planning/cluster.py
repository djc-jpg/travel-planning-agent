"""Distance-threshold clustering helpers for daily planning."""

from __future__ import annotations

from typing import Callable

from app.domain.models import POI

DistanceFn = Callable[[float, float, float, float], float]
DEFAULT_CLUSTER_DISTANCE_KM = 4.5
DEFAULT_CROSS_CLUSTER_PENALTY = 12.0


def build_cluster_map(
    pois: list[POI],
    *,
    distance_fn: DistanceFn,
    threshold_km: float = DEFAULT_CLUSTER_DISTANCE_KM,
) -> dict[str, str]:
    clusters: dict[str, tuple[float, float, int]] = {}
    mapping: dict[str, str] = {}
    next_geo = 1
    for poi in pois:
        if poi.cluster:
            cluster_id = f"hint:{poi.cluster}"
            mapping[poi.id] = cluster_id
            lat, lon, size = clusters.get(cluster_id, (0.0, 0.0, 0))
            clusters[cluster_id] = (
                ((lat * size) + poi.lat) / (size + 1),
                ((lon * size) + poi.lon) / (size + 1),
                size + 1,
            )
            continue
        best_id = ""
        best_dist = threshold_km + 1.0
        for cluster_id, (center_lat, center_lon, _size) in clusters.items():
            dist = distance_fn(center_lat, center_lon, poi.lat, poi.lon)
            if dist <= threshold_km and dist < best_dist:
                best_id = cluster_id
                best_dist = dist
        if not best_id:
            best_id = f"geo:{next_geo}"
            next_geo += 1
            clusters[best_id] = (poi.lat, poi.lon, 1)
        else:
            center_lat, center_lon, size = clusters[best_id]
            clusters[best_id] = (
                ((center_lat * size) + poi.lat) / (size + 1),
                ((center_lon * size) + poi.lon) / (size + 1),
                size + 1,
            )
        mapping[poi.id] = best_id
    return mapping


def enforce_day_cluster_cap(
    day_pois: list[POI],
    *,
    cluster_map: dict[str, str],
    max_clusters: int = 2,
) -> tuple[list[POI], set[str]]:
    if not day_pois:
        return [], set()
    counts: dict[str, int] = {}
    for poi in day_pois:
        cid = cluster_map.get(poi.id, "geo:0")
        counts[cid] = counts.get(cid, 0) + 1
    sorted_clusters = sorted(counts.items(), key=lambda row: (-row[1], row[0]))
    allowed = {cid for cid, _ in sorted_clusters[: max(1, max_clusters)]}
    filtered = [poi for poi in day_pois if cluster_map.get(poi.id, "geo:0") in allowed]
    if filtered:
        return filtered, allowed
    first = day_pois[0]
    cid = cluster_map.get(first.id, "geo:0")
    return [first], {cid}


def cross_cluster_penalty_minutes(
    prev_poi: POI,
    curr_poi: POI,
    *,
    cluster_map: dict[str, str] | None,
    penalty_minutes: float = DEFAULT_CROSS_CLUSTER_PENALTY,
) -> float:
    if not cluster_map:
        return 0.0
    prev_cluster = cluster_map.get(prev_poi.id)
    curr_cluster = cluster_map.get(curr_poi.id)
    if not prev_cluster or not curr_cluster:
        return 0.0
    if prev_cluster == curr_cluster:
        return 0.0
    return penalty_minutes


__all__ = [
    "DEFAULT_CLUSTER_DISTANCE_KM",
    "DEFAULT_CROSS_CLUSTER_PENALTY",
    "DistanceFn",
    "build_cluster_map",
    "cross_cluster_penalty_minutes",
    "enforce_day_cluster_cap",
]
