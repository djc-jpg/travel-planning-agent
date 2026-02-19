"""Real weather adapter backed by AMap weather API."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

from app.security.amap_signer import sign_amap_params
from app.security.http_client import SecureHttpClient
from app.security.key_manager import get_key_manager
from app.security.redact import redact_sensitive
from app.tools.interfaces import DayWeather, WeatherInput, WeatherResult, ToolError

_BASE_URL = "https://restapi.amap.com/v3/weather/weatherInfo"
_logger = logging.getLogger("trip-agent.weather")

_CITY_ADCODE: dict[str, str] = {
    "北京": "110000",
    "上海": "310000",
    "杭州": "330100",
    "成都": "510100",
    "西安": "610100",
    "广州": "440100",
    "南京": "320100",
    "重庆": "500000",
    "长沙": "430100",
    "厦门": "350200",
    "深圳": "440300",
    "武汉": "420100",
    "苏州": "320500",
    "丽江": "530700",
    "三亚": "460200",
    "大理": "532900",
    "青岛": "370200",
    "昆明": "530100",
    "拉萨": "540100",
    "天津": "120000",
}

_BAD_WEATHER_KEYWORDS = {"雨", "雪", "雷", "暴", "冰雹", "沙尘"}


def _strict_external_enabled() -> bool:
    value = os.getenv("STRICT_EXTERNAL_DATA", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_api_key() -> str:
    km = get_key_manager()
    key = km.get_amap_key(required=False)
    if not key:
        raise ToolError("real_weather", "AMAP_API_KEY is not configured")
    return key


def _mock_weather(params: WeatherInput) -> WeatherResult:
    from app.adapters.weather.mock import get_weather as mock_get_weather

    return mock_get_weather(params)


_http = SecureHttpClient(tool_name="real_weather", max_retries=1)


def _is_outdoor_friendly(condition: str) -> bool:
    return not any(keyword in condition for keyword in _BAD_WEATHER_KEYWORDS)


def _simplify_condition(condition: str) -> str:
    return condition if condition else "未知"


def get_weather(params: WeatherInput) -> WeatherResult:
    _get_api_key()
    strict_external = _strict_external_enabled()

    adcode = _CITY_ADCODE.get(params.city)
    if not adcode:
        if strict_external:
            raise ToolError("real_weather", f"city is not mapped to AMap adcode: {params.city}")
        _logger.warning("City not mapped in weather adapter, fallback to mock: %s", params.city)
        return _mock_weather(params)

    try:
        request_params = sign_amap_params(
            {
                "city": adcode,
                "extensions": "all",
                "output": "json",
            }
        )
        data = _http.get(_BASE_URL, params=request_params)
    except Exception as exc:
        if strict_external:
            raise ToolError("real_weather", f"amap request failed: {redact_sensitive(str(exc))}") from None
        _logger.warning("Weather request failed, fallback to mock: %s", redact_sensitive(str(exc)))
        return _mock_weather(params)

    if data.get("status") != "1":
        info = data.get("info", "unknown")
        code = data.get("infocode", "")
        if strict_external:
            raise ToolError("real_weather", f"amap returned failure: {info} ({code})")
        _logger.warning("AMap weather status!=1, fallback to mock: %s (%s)", info, code)
        return _mock_weather(params)

    forecasts_raw = data.get("forecasts", [])
    if not forecasts_raw:
        if strict_external:
            raise ToolError("real_weather", "amap response has no forecast data")
        _logger.warning("AMap weather returned empty forecast, fallback to mock")
        return _mock_weather(params)

    casts = forecasts_raw[0].get("casts", [])
    if not casts:
        if strict_external:
            raise ToolError("real_weather", "amap response has empty casts")
        _logger.warning("AMap weather returned empty casts, fallback to mock")
        return _mock_weather(params)

    try:
        start_date = datetime.strptime(params.date_start, "%Y-%m-%d").date()
    except ValueError:
        start_date = datetime.now().date()

    forecasts: list[DayWeather] = []
    for index in range(params.days):
        target_date = start_date + timedelta(days=index)
        matched = None

        for cast in casts:
            cast_date_str = cast.get("date", "")
            try:
                cast_date = datetime.strptime(cast_date_str, "%Y-%m-%d").date()
            except ValueError:
                continue
            if cast_date == target_date:
                matched = cast
                break

        if matched:
            condition = _simplify_condition(matched.get("dayweather", ""))
            try:
                temp_high = float(matched.get("daytemp", 0))
            except (TypeError, ValueError):
                temp_high = 0.0
            try:
                temp_low = float(matched.get("nighttemp", 0))
            except (TypeError, ValueError):
                temp_low = 0.0

            forecasts.append(
                DayWeather(
                    date=target_date.strftime("%Y-%m-%d"),
                    condition=condition,
                    temp_high=temp_high,
                    temp_low=temp_low,
                    is_outdoor_friendly=_is_outdoor_friendly(condition),
                )
            )
            continue

        if strict_external:
            raise ToolError(
                "real_weather",
                f"forecast horizon exceeded for {params.days} days from {params.date_start}",
            )

        mock_result = _mock_weather(
            WeatherInput(
                city=params.city,
                date_start=target_date.strftime("%Y-%m-%d"),
                days=1,
            )
        )
        if mock_result.forecasts:
            forecasts.append(mock_result.forecasts[0])
        else:
            forecasts.append(
                DayWeather(
                    date=target_date.strftime("%Y-%m-%d"),
                    condition="未知",
                    temp_high=20,
                    temp_low=10,
                    is_outdoor_friendly=True,
                )
            )

    return WeatherResult(city=params.city, forecasts=forecasts)

