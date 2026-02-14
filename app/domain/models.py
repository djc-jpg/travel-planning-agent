"""Pydantic domain models."""

from __future__ import annotations

import datetime as dt
from typing import Optional

from pydantic import BaseModel, Field

from app.domain.enums import Pace, Severity, TimeSlot, TransportMode, TravelersType


class TripConstraints(BaseModel):
    city: Optional[str] = None
    days: int = 3
    date_start: Optional[dt.date] = None
    date_end: Optional[dt.date] = None
    budget_per_day: Optional[float] = None
    total_budget: Optional[float] = None
    hotel_location: Optional[str] = None
    transport_mode: TransportMode = TransportMode.PUBLIC_TRANSIT
    pace: Pace = Pace.MODERATE


class UserProfile(BaseModel):
    themes: list[str] = Field(default_factory=list)
    travelers_type: TravelersType = TravelersType.COUPLE
    food_constraints: list[str] = Field(default_factory=list)
    start_time_preference: Optional[dt.time] = None


class POI(BaseModel):
    id: str
    name: str
    city: str
    lat: float = 0.0
    lon: float = 0.0
    themes: list[str] = Field(default_factory=list)
    duration_hours: float = 1.5
    cost: float = 0.0
    indoor: bool = False
    open_time: Optional[str] = None
    description: str = ""


class ScheduleItem(BaseModel):
    poi: POI
    time_slot: TimeSlot = TimeSlot.MORNING
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    travel_minutes: float = 0.0
    notes: str = ""
    is_backup: bool = False


class ItineraryDay(BaseModel):
    day_number: int = 1
    date: Optional[dt.date] = None
    schedule: list[ScheduleItem] = Field(default_factory=list)
    backups: list[ScheduleItem] = Field(default_factory=list)
    day_summary: str = ""
    estimated_cost: float = 0.0
    total_travel_minutes: float = 0.0


class Itinerary(BaseModel):
    city: str = ""
    days: list[ItineraryDay] = Field(default_factory=list)
    total_cost: float = 0.0
    assumptions: list[str] = Field(default_factory=list)
    summary: str = ""


class ValidationIssue(BaseModel):
    code: str
    severity: Severity = Severity.MEDIUM
    message: str = ""
    day: Optional[int] = None
    suggestions: list[str] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    error: bool = True
    code: str = "UNKNOWN"
    message: str = ""
    details: list[str] = Field(default_factory=list)

