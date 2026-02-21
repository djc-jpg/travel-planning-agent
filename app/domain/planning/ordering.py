"""Lightweight ordering helpers: nearest-neighbor + bounded 2-opt."""

from __future__ import annotations

from typing import Callable

from app.domain.models import POI

DistanceFn = Callable[[float, float, float, float], float]


def route_distance_km(
    pois: list[POI],
    *,
    distance_fn: DistanceFn,
    start_lat: float = 0.0,
    start_lon: float = 0.0,
) -> float:
    if not pois:
        return 0.0
    cur_lat = start_lat or pois[0].lat
    cur_lon = start_lon or pois[0].lon
    total = 0.0
    for poi in pois:
        total += distance_fn(cur_lat, cur_lon, poi.lat, poi.lon)
        cur_lat, cur_lon = poi.lat, poi.lon
    return total


def nearest_neighbor_order(
    pois: list[POI],
    *,
    distance_fn: DistanceFn,
    start_lat: float = 0.0,
    start_lon: float = 0.0,
) -> list[POI]:
    if len(pois) <= 1:
        return list(pois)
    remaining = list(pois)
    ordered: list[POI] = []
    cur_lat = start_lat or remaining[0].lat
    cur_lon = start_lon or remaining[0].lon
    while remaining:
        nxt = min(remaining, key=lambda poi: distance_fn(cur_lat, cur_lon, poi.lat, poi.lon))
        remaining.remove(nxt)
        ordered.append(nxt)
        cur_lat, cur_lon = nxt.lat, nxt.lon
    return ordered


def _swap_segment(route: list[POI], left: int, right: int) -> list[POI]:
    return route[:left] + list(reversed(route[left : right + 1])) + route[right + 1 :]


def two_opt_order(
    pois: list[POI],
    *,
    distance_fn: DistanceFn,
    start_lat: float = 0.0,
    start_lon: float = 0.0,
    max_passes: int = 6,
) -> list[POI]:
    if len(pois) < 4:
        return list(pois)
    best = list(pois)
    best_dist = route_distance_km(best, distance_fn=distance_fn, start_lat=start_lat, start_lon=start_lon)
    passes = 0
    improved = True
    while improved and passes < max_passes:
        passes += 1
        improved = False
        for left in range(1, len(best) - 2):
            for right in range(left + 1, len(best) - 1):
                candidate = _swap_segment(best, left, right)
                distance = route_distance_km(
                    candidate,
                    distance_fn=distance_fn,
                    start_lat=start_lat,
                    start_lon=start_lon,
                )
                if distance + 1e-6 < best_dist:
                    best = candidate
                    best_dist = distance
                    improved = True
                    break
            if improved:
                break
    return best


def optimize_daily_order(
    pois: list[POI],
    *,
    distance_fn: DistanceFn,
    start_lat: float = 0.0,
    start_lon: float = 0.0,
) -> list[POI]:
    seeded = nearest_neighbor_order(
        pois,
        distance_fn=distance_fn,
        start_lat=start_lat,
        start_lon=start_lon,
    )
    return two_opt_order(
        seeded,
        distance_fn=distance_fn,
        start_lat=start_lat,
        start_lon=start_lon,
    )


__all__ = [
    "DistanceFn",
    "nearest_neighbor_order",
    "optimize_daily_order",
    "route_distance_km",
    "two_opt_order",
]
