"""Pydantic domain models."""

from __future__ import annotations

import datetime as dt
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.domain.enums import Pace, PoiSemanticType, Severity, TimeSlot, TransportMode, TravelersType


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
    holiday_hint: Optional[str] = None
    travelers_count: Optional[int] = None
    must_visit: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    free_only: bool = False


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
    requires_reservation: bool = False
    reservation_days_ahead: int = 0
    closed_rules: str = ""
    closed_weekdays: list[int] = Field(default_factory=list)
    metadata_source: str = ""
    source_category: str = ""
    cluster: str = ""
    ticket_price: float = 0.0
    open_hours: Optional[str] = None
    reservation_required: Optional[bool] = None
    fact_sources: dict[str, str] = Field(default_factory=dict)
    is_verified: bool = False
    food_min_nearby: float = 35.0
    semantic_type: PoiSemanticType = PoiSemanticType.UNKNOWN
    semantic_confidence: float = 0.0

    @model_validator(mode="after")
    def _normalize_fact_fields(self) -> "POI":
        if self.open_hours is None and self.open_time is not None:
            self.open_hours = self.open_time
        if self.open_time is None and self.open_hours is not None:
            self.open_time = self.open_hours

        if self.reservation_required is None:
            self.reservation_required = bool(self.requires_reservation)
        self.requires_reservation = bool(self.reservation_required)

        if self.ticket_price <= 0 and self.cost > 0:
            self.ticket_price = float(self.cost)
        if self.cost <= 0 and self.ticket_price > 0:
            self.cost = float(self.ticket_price)
        return self


class ScheduleItem(BaseModel):
    poi: POI
    time_slot: TimeSlot = TimeSlot.MORNING
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    travel_minutes: float = 0.0
    buffer_minutes: float = 0.0
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
    meal_windows: list[str] = Field(default_factory=list)


class Itinerary(BaseModel):
    city: str = ""
    days: list[ItineraryDay] = Field(default_factory=list)
    total_cost: float = 0.0
    assumptions: list[str] = Field(default_factory=list)
    summary: str = ""
    budget_breakdown: dict[str, float] = Field(default_factory=dict)
    budget_source_breakdown: dict[str, str] = Field(default_factory=dict)
    budget_confidence_breakdown: dict[str, float] = Field(default_factory=dict)
    budget_confidence_score: float = 0.0
    budget_as_of: str = ""
    minimum_feasible_budget: float = 0.0
    budget_warning: str = ""
    unknown_fields: list[str] = Field(default_factory=list)
    confidence_score: float = 1.0
    degrade_level: str = "L0"
    violations: list[str] = Field(default_factory=list)
    repair_actions: list[str] = Field(default_factory=list)
    trace_id: str = ""


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
