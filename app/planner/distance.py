"""Deterministic distance and travel-time estimation."""

from __future__ import annotations

import math

from app.shared.exceptions import ToolError

SPEED_MAP = {
    "walking": 5.0,
    "public_transit": 25.0,
    "taxi": 35.0,
    "driving": 40.0,
}


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def estimate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return haversine(lat1, lon1, lat2, lon2) * 1.4


def estimate_travel_time(distance_km: float, mode: str = "public_transit") -> float:
    speed = SPEED_MAP.get(mode)
    if speed is None:
        raise ToolError("distance_estimator", f"Unknown transport mode: {mode}")
    return (distance_km / speed) * 60

