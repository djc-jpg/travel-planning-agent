"""Tool abstraction protocols and I/O schemas."""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.domain.models import POI
from app.shared.exceptions import ToolError


class POISearchInput(BaseModel):
    city: str
    themes: list[str] = Field(default_factory=list)
    indoor: Optional[bool] = None
    max_results: int = 20


class RouteInput(BaseModel):
    origin_lat: float
    origin_lon: float
    dest_lat: float
    dest_lon: float
    mode: str = "public_transit"


class RouteResult(BaseModel):
    distance_km: float
    duration_minutes: float


class BudgetInput(BaseModel):
    poi_costs: list[float] = Field(default_factory=list)
    transport_segments: int = 0
    transport_mode: str = "public_transit"


class BudgetResult(BaseModel):
    total_cost: float
    breakdown: dict[str, float] = Field(default_factory=dict)


class WeatherInput(BaseModel):
    city: str
    date_start: str = Field(description="Start date in YYYY-MM-DD format")
    days: int = 1


class DayWeather(BaseModel):
    date: str = Field(description="Date in YYYY-MM-DD format")
    condition: str = Field(description="Weather condition")
    temp_high: float = Field(description="High temperature (C)")
    temp_low: float = Field(description="Low temperature (C)")
    is_outdoor_friendly: bool = Field(description="Whether outdoor activities are suitable")


class WeatherResult(BaseModel):
    city: str
    forecasts: list[DayWeather] = Field(default_factory=list)


class CalendarInput(BaseModel):
    date_start: str = Field(description="Start date in YYYY-MM-DD format")
    days: int = 1


class DayCalendarInfo(BaseModel):
    date: str = Field(description="Date in YYYY-MM-DD format")
    is_holiday: bool = Field(description="Whether this is a legal holiday")
    is_weekend: bool = Field(description="Whether this is weekend")
    holiday_name: str = Field(default="", description="Holiday name")
    crowd_level: str = Field(default="normal", description="Crowd level: low/normal/high/very_high")


class CalendarResult(BaseModel):
    days: list[DayCalendarInfo] = Field(default_factory=list)


@runtime_checkable
class POITool(Protocol):
    def search_poi(self, params: POISearchInput) -> list[POI]: ...

    def get_poi_detail(self, poi_id: str) -> POI: ...


@runtime_checkable
class RouteTool(Protocol):
    def estimate_route(self, params: RouteInput) -> RouteResult: ...


@runtime_checkable
class BudgetTool(Protocol):
    def estimate_cost(self, params: BudgetInput) -> BudgetResult: ...


@runtime_checkable
class WeatherTool(Protocol):
    def get_weather(self, params: WeatherInput) -> WeatherResult: ...


@runtime_checkable
class CalendarTool(Protocol):
    def get_calendar(self, params: CalendarInput) -> CalendarResult: ...


__all__ = [
    "POISearchInput",
    "RouteInput",
    "RouteResult",
    "BudgetInput",
    "BudgetResult",
    "WeatherInput",
    "DayWeather",
    "WeatherResult",
    "CalendarInput",
    "DayCalendarInfo",
    "CalendarResult",
    "POITool",
    "RouteTool",
    "BudgetTool",
    "WeatherTool",
    "CalendarTool",
    "ToolError",
]
