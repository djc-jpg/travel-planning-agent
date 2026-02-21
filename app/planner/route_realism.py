"""Semi-realistic routing adjustments and confidence estimation."""

from __future__ import annotations

from datetime import datetime

from app.domain.models import POI

_CITY_ALIASES = {
    "北京": "beijing",
    "beijing": "beijing",
    "上海": "shanghai",
    "shanghai": "shanghai",
    "杭州": "hangzhou",
    "hangzhou": "hangzhou",
    "成都": "chengdu",
    "chengdu": "chengdu",
}

_CITY_CLUSTER_SPEED = {
    "beijing": {
        "central_axis": {"walking": 0.82, "public_transit": 0.72, "taxi": 0.70, "driving": 0.68},
        "imperial_garden": {"walking": 0.90, "public_transit": 0.82, "taxi": 0.80, "driving": 0.78},
        "old_city": {"walking": 0.84, "public_transit": 0.75, "taxi": 0.72, "driving": 0.70},
    },
    "shanghai": {
        "core": {"walking": 0.80, "public_transit": 0.74, "taxi": 0.71, "driving": 0.69},
    },
    "hangzhou": {
        "west_lake": {"walking": 0.92, "public_transit": 0.86, "taxi": 0.82, "driving": 0.80},
    },
}


def _norm_city(city: str) -> str:
    return _CITY_ALIASES.get(str(city or "").strip().lower(), str(city or "").strip().lower())


def _norm_cluster(cluster: str) -> str:
    return str(cluster or "").strip().lower()


def _cluster_speed(city: str, cluster: str, mode: str) -> float:
    city_key = _norm_city(city)
    cluster_key = _norm_cluster(cluster)
    row = _CITY_CLUSTER_SPEED.get(city_key, {})
    if cluster_key in row:
        return float(row[cluster_key].get(mode, 1.0))
    if row:
        weighted = [float(item.get(mode, 1.0)) for item in row.values()]
        return sum(weighted) / max(len(weighted), 1)
    return 1.0


def _peak_factor(mode: str, departure_time: datetime | None) -> float:
    if departure_time is None:
        return 1.05
    hour = int(departure_time.hour)
    if hour in {7, 8, 9, 17, 18, 19}:
        return {"walking": 1.05, "public_transit": 1.24, "taxi": 1.34, "driving": 1.32}.get(mode, 1.20)
    if hour in {10, 11, 15, 16}:
        return {"walking": 1.02, "public_transit": 1.10, "taxi": 1.16, "driving": 1.14}.get(mode, 1.08)
    return 1.0


def adjust_travel_minutes(
    *,
    base_minutes: float,
    origin: POI,
    destination: POI,
    mode: str,
    departure_time: datetime | None,
) -> float:
    base = max(0.0, float(base_minutes))
    origin_speed = _cluster_speed(origin.city, origin.cluster, mode)
    destination_speed = _cluster_speed(destination.city, destination.cluster, mode)
    speed = max(0.55, (origin_speed + destination_speed) / 2.0)
    cross_zone_factor = 1.08 if origin.cluster and destination.cluster and origin.cluster != destination.cluster else 1.0
    adjusted = base * (1.0 / speed) * _peak_factor(mode, departure_time) * cross_zone_factor
    return round(max(5.0, adjusted), 1)


def estimate_routing_confidence(
    *,
    origin: POI,
    destination: POI,
    mode: str,
    departure_time: datetime | None,
    source: str,
) -> float:
    base = {"real": 0.90, "fixture": 0.72, "heuristic": 0.62}.get(source, 0.60)
    city_key = _norm_city(origin.city or destination.city)
    if city_key in _CITY_CLUSTER_SPEED:
        base += 0.08
    if origin.cluster and destination.cluster:
        base += 0.05
    if _peak_factor(mode, departure_time) > 1.2:
        base -= 0.05
    return round(min(0.98, max(0.30, base)), 2)


__all__ = ["adjust_travel_minutes", "estimate_routing_confidence"]
