"""Port interfaces for retrieval dependencies."""

from __future__ import annotations

from typing import Protocol

from app.domain.models import POI
from app.tools.interfaces import CalendarInput, CalendarResult, POISearchInput, WeatherInput, WeatherResult


class LoggerPort(Protocol):
    def summary(self, stage: str, message: str) -> None: ...

    def warning(self, stage: str, message: str) -> None: ...

    def error(self, stage: str, message: str) -> None: ...


class POIToolPort(Protocol):
    def search_poi(self, params: POISearchInput) -> list[POI]: ...


class WeatherToolPort(Protocol):
    def get_weather(self, params: WeatherInput) -> WeatherResult: ...


class CalendarToolPort(Protocol):
    def get_calendar(self, params: CalendarInput) -> CalendarResult: ...


__all__ = [
    "CalendarToolPort",
    "LoggerPort",
    "POIToolPort",
    "WeatherToolPort",
]

