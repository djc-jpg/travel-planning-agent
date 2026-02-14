"""Domain package exports."""

from app.domain.constants import (
    DEFAULT_DAILY_HOURS,
    MAX_DAILY_TRAVEL_MINUTES,
    PACE_MAX,
    PACE_MIN,
    PACE_POI_COUNT,
    TRANSPORT_COST_PER_SEGMENT,
)
from app.domain.enums import Pace, Severity, TimeSlot, TransportMode, TravelersType
from app.domain.exceptions import DomainError, InvalidConstraints
from app.domain.models import (
    ErrorResponse,
    Itinerary,
    ItineraryDay,
    POI,
    ScheduleItem,
    TripConstraints,
    UserProfile,
    ValidationIssue,
)

__all__ = [
    "ErrorResponse",
    "DomainError",
    "InvalidConstraints",
    "Itinerary",
    "ItineraryDay",
    "POI",
    "ScheduleItem",
    "TripConstraints",
    "UserProfile",
    "ValidationIssue",
    "Pace",
    "Severity",
    "TimeSlot",
    "TransportMode",
    "TravelersType",
    "DEFAULT_DAILY_HOURS",
    "MAX_DAILY_TRAVEL_MINUTES",
    "PACE_POI_COUNT",
    "PACE_MAX",
    "PACE_MIN",
    "TRANSPORT_COST_PER_SEGMENT",
]

