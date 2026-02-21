"""Domain enums."""

from enum import Enum


class Pace(str, Enum):
    RELAXED = "relaxed"
    MODERATE = "moderate"
    INTENSIVE = "intensive"


class TransportMode(str, Enum):
    WALKING = "walking"
    PUBLIC_TRANSIT = "public_transit"
    TAXI = "taxi"
    DRIVING = "driving"


class TravelersType(str, Enum):
    SOLO = "solo"
    COUPLE = "couple"
    FAMILY = "family"
    FRIENDS = "friends"
    ELDERLY = "elderly"


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TimeSlot(str, Enum):
    MORNING = "morning"
    LUNCH = "lunch"
    AFTERNOON = "afternoon"
    DINNER = "dinner"
    EVENING = "evening"


class PoiSemanticType(str, Enum):
    EXPERIENCE = "experience"
    INFRASTRUCTURE = "infrastructure"
    UNKNOWN = "unknown"
