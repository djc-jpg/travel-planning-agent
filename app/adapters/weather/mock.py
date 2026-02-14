"""Mock weather adapter with simple city/month climate profiles."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.tools.interfaces import DayWeather, WeatherInput, WeatherResult

CITY_CLIMATE: dict[str, dict[int, tuple[str, float, float, float]]] = {
    "北京": {
        1: ("晴", -1, -10, 0.05),
        2: ("晴", 3, -6, 0.05),
        3: ("多云", 12, 1, 0.10),
        4: ("晴", 21, 8, 0.15),
        5: ("晴", 27, 14, 0.15),
        6: ("多云", 31, 19, 0.30),
        7: ("多云", 31, 22, 0.45),
        8: ("多云", 30, 21, 0.40),
        9: ("晴", 26, 15, 0.15),
        10: ("晴", 19, 7, 0.10),
        11: ("晴", 9, -1, 0.05),
        12: ("晴", 2, -8, 0.05),
    }
}

DEFAULT_CLIMATE: dict[int, tuple[str, float, float, float]] = {
    1: ("阴", 8, 1, 0.15),
    2: ("阴", 10, 3, 0.15),
    3: ("多云", 15, 7, 0.20),
    4: ("多云", 22, 12, 0.25),
    5: ("晴", 27, 17, 0.20),
    6: ("多云", 30, 22, 0.35),
    7: ("多云", 33, 25, 0.35),
    8: ("多云", 32, 25, 0.35),
    9: ("晴", 27, 19, 0.20),
    10: ("晴", 22, 13, 0.15),
    11: ("多云", 14, 6, 0.10),
    12: ("阴", 8, 1, 0.10),
}

BAD_WEATHER = {"小雨", "中雨", "大雨", "暴雨", "雪", "大雪", "雷"}


def _vary_condition(base_condition: str, rain_prob: float, day_index: int) -> str:
    import hashlib

    h = int(hashlib.md5(str(day_index).encode()).hexdigest()[:8], 16)
    threshold = int(rain_prob * 0xFFFFFFFF)
    if h < threshold:
        return "中雨" if rain_prob > 0.4 else "小雨"
    return base_condition


def get_weather(params: WeatherInput) -> WeatherResult:
    city_climate = CITY_CLIMATE.get(params.city, DEFAULT_CLIMATE)
    try:
        start = datetime.strptime(params.date_start, "%Y-%m-%d")
    except ValueError:
        start = datetime.now()

    forecasts: list[DayWeather] = []
    for i in range(params.days):
        day_date = start + timedelta(days=i)
        base_cond, temp_high, temp_low, rain_prob = city_climate.get(
            day_date.month, DEFAULT_CLIMATE[day_date.month]
        )
        condition = _vary_condition(base_cond, rain_prob, i)

        import hashlib

        jitter = int(hashlib.md5(f"temp_{i}".encode()).hexdigest()[:4], 16) % 5 - 2
        high = temp_high + jitter
        low = temp_low + jitter

        forecasts.append(
            DayWeather(
                date=day_date.strftime("%Y-%m-%d"),
                condition=condition,
                temp_high=high,
                temp_low=low,
                is_outdoor_friendly=condition not in BAD_WEATHER,
            )
        )

    return WeatherResult(city=params.city, forecasts=forecasts)

