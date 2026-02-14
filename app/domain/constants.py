"""Domain constants shared by deterministic logic."""

from app.domain.enums import Pace

PACE_POI_COUNT = {
    Pace.RELAXED: 2,
    Pace.MODERATE: 3,
    Pace.INTENSIVE: 5,
}

PACE_MAX = {
    Pace.RELAXED: 2,
    Pace.MODERATE: 3,
    Pace.INTENSIVE: 5,
}

PACE_MIN = {
    Pace.RELAXED: 1,
    Pace.MODERATE: 2,
    Pace.INTENSIVE: 3,
}

DEFAULT_DAILY_HOURS = 10.0
MAX_DAILY_TRAVEL_MINUTES = 120.0

TRANSPORT_COST_PER_SEGMENT = {
    "walking": 0.0,
    "public_transit": 5.0,
    "taxi": 30.0,
    "driving": 20.0,
}

