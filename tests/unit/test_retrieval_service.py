"""Unit tests for retrieval service split."""

from __future__ import annotations

from app.application.graph.nodes.retrieval_service import retrieve_trip_context
from app.domain.models import POI
from app.observability.plan_metrics import get_plan_metrics
from app.tools.interfaces import CalendarResult, DayCalendarInfo, DayWeather, WeatherResult


class _Logger:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, str]] = []

    def summary(self, stage: str, message: str) -> None:
        self.events.append(("summary", stage, message))

    def warning(self, stage: str, message: str) -> None:
        self.events.append(("warning", stage, message))

    def error(self, stage: str, message: str) -> None:
        self.events.append(("error", stage, message))


class _POITool:
    def search_poi(self, _params):
        return [
            POI(
                id="poi_1",
                name="西湖",
                city="杭州",
                lat=30.24,
                lon=120.15,
                themes=["自然"],
                duration_hours=2.0,
                cost=0,
            )
        ]


class _MixedPOITool:
    def search_poi(self, _params):
        return [
            POI(
                id="infra_1",
                name="Museum Parking Lot",
                city="Hangzhou",
                source_category="交通设施服务;停车场",
            ),
            POI(
                id="exp_1",
                name="City Museum",
                city="Hangzhou",
                source_category="风景名胜;博物馆",
                themes=["history"],
            ),
        ]


class _WeatherTool:
    def get_weather(self, _params):
        return WeatherResult(
            city="杭州",
            forecasts=[
                DayWeather(
                    date="2026-04-01",
                    condition="晴",
                    temp_high=28,
                    temp_low=18,
                    is_outdoor_friendly=True,
                )
            ],
        )


class _CalendarTool:
    def get_calendar(self, _params):
        return CalendarResult(
            days=[
                DayCalendarInfo(
                    date="2026-04-01",
                    is_holiday=False,
                    is_weekend=False,
                    holiday_name="",
                    crowd_level="normal",
                )
            ]
        )


class _FailPOITool:
    def search_poi(self, _params):
        raise RuntimeError("poi backend down")


class _FailWeatherTool:
    def get_weather(self, _params):
        raise RuntimeError("weather backend down")


def test_retrieval_service_returns_candidates_and_context():
    metrics = get_plan_metrics()
    metrics.reset()
    logger = _Logger()
    result = retrieve_trip_context(
        constraints={"city": "杭州", "days": 2},
        profile={"themes": ["自然"]},
        logger=logger,
        poi_tool=_POITool(),
        weather_tool=_WeatherTool(),
        calendar_tool=_CalendarTool(),
        strict_external=False,
        has_curated_city_fn=lambda _city: False,
        get_city_pois_fn=lambda *_args, **_kwargs: [],
    )

    assert result["validation_issues"] == []
    assert len(result["attraction_candidates"]) == 1
    assert result["weather_data"] is not None
    assert result["calendar_data"] is not None
    tool_calls = metrics.snapshot()["tool_calls"]
    assert tool_calls["poi.search"]["count"] >= 1
    assert tool_calls["weather.get_weather"]["ok"] >= 1
    assert tool_calls["calendar.get_calendar"]["ok"] >= 1


def test_retrieval_service_missing_city_returns_clarifying_error():
    logger = _Logger()
    result = retrieve_trip_context(
        constraints={},
        profile={},
        logger=logger,
        poi_tool=_POITool(),
        weather_tool=_WeatherTool(),
        calendar_tool=_CalendarTool(),
        strict_external=False,
        has_curated_city_fn=lambda _city: False,
        get_city_pois_fn=lambda *_args, **_kwargs: [],
    )

    assert result["error_code"] == "NO_CANDIDATES"
    assert result["attraction_candidates"] == []
    assert result["validation_issues"]


def test_retrieval_service_filters_infrastructure_candidates():
    logger = _Logger()
    result = retrieve_trip_context(
        constraints={"city": "Hangzhou", "days": 1},
        profile={},
        logger=logger,
        poi_tool=_MixedPOITool(),
        weather_tool=_WeatherTool(),
        calendar_tool=_CalendarTool(),
        strict_external=False,
        has_curated_city_fn=lambda _city: False,
        get_city_pois_fn=lambda *_args, **_kwargs: [],
    )

    ids = [item["id"] for item in result["attraction_candidates"]]
    assert ids == ["exp_1"]
    assert all("parking" not in item["name"].lower() for item in result["attraction_candidates"])


def test_retrieval_service_strict_fails_fast_when_poi_unavailable():
    logger = _Logger()
    result = retrieve_trip_context(
        constraints={"city": "Hangzhou", "days": 1},
        profile={},
        logger=logger,
        poi_tool=_FailPOITool(),
        weather_tool=_WeatherTool(),
        calendar_tool=_CalendarTool(),
        strict_external=True,
        has_curated_city_fn=lambda _city: False,
        get_city_pois_fn=lambda *_args, **_kwargs: [],
    )

    assert result["error_code"] == "TOOL_UNAVAILABLE"
    assert result["attraction_candidates"] == []
    assert result["validation_issues"]


def test_retrieval_service_strict_fails_fast_when_weather_unavailable():
    logger = _Logger()
    result = retrieve_trip_context(
        constraints={"city": "Hangzhou", "days": 1},
        profile={},
        logger=logger,
        poi_tool=_POITool(),
        weather_tool=_FailWeatherTool(),
        calendar_tool=_CalendarTool(),
        strict_external=True,
        has_curated_city_fn=lambda _city: False,
        get_city_pois_fn=lambda *_args, **_kwargs: [],
    )

    assert result["error_code"] == "TOOL_UNAVAILABLE"
    assert result["attraction_candidates"] == []
    assert result["validation_issues"]


def test_retrieval_service_non_strict_continues_when_weather_unavailable():
    logger = _Logger()
    result = retrieve_trip_context(
        constraints={"city": "Hangzhou", "days": 1},
        profile={},
        logger=logger,
        poi_tool=_POITool(),
        weather_tool=_FailWeatherTool(),
        calendar_tool=_CalendarTool(),
        strict_external=False,
        has_curated_city_fn=lambda _city: False,
        get_city_pois_fn=lambda *_args, **_kwargs: [],
    )

    assert result["validation_issues"] == []
    assert len(result["attraction_candidates"]) == 1
    assert result.get("weather_data") is None
    assert result.get("calendar_data") is not None
