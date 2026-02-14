"""天气工具 & 日历工具测试"""

from app.adapters.calendar.mock import get_calendar
from app.adapters.weather.mock import get_weather
from app.tools.interfaces import WeatherInput, CalendarInput
from app.agent.planner_core import generate_itinerary
from app.domain.models import Pace, POI, TripConstraints, UserProfile


# ── 天气工具测试 ──────────────────────────────────────

def test_weather_basic():
    """测试基本天气查询"""
    result = get_weather(WeatherInput(city="北京", date_start="2026-07-15", days=3))
    assert result.city == "北京"
    assert len(result.forecasts) == 3
    for fc in result.forecasts:
        assert fc.date
        assert fc.condition
        assert isinstance(fc.is_outdoor_friendly, bool)
        assert fc.temp_high >= fc.temp_low


def test_weather_unknown_city():
    """未收录城市使用默认气候"""
    result = get_weather(WeatherInput(city="丽江", date_start="2026-05-01", days=2))
    assert result.city == "丽江"
    assert len(result.forecasts) == 2


def test_weather_single_day():
    """单日查询"""
    result = get_weather(WeatherInput(city="上海", date_start="2026-01-15", days=1))
    assert len(result.forecasts) == 1


# ── 日历工具测试 ──────────────────────────────────────

def test_calendar_national_day():
    """国庆节检测"""
    result = get_calendar(CalendarInput(date_start="2026-10-01", days=3))
    assert len(result.days) == 3
    assert result.days[0].is_holiday is True
    assert result.days[0].holiday_name == "国庆节"
    assert result.days[0].crowd_level == "very_high"


def test_calendar_spring_festival():
    """春节检测 (2026年春节: 2月16日除夕)"""
    result = get_calendar(CalendarInput(date_start="2026-02-17", days=2))
    assert len(result.days) == 2
    assert result.days[0].is_holiday is True
    assert result.days[0].holiday_name == "春节"


def test_calendar_normal_weekday():
    """普通工作日"""
    result = get_calendar(CalendarInput(date_start="2026-03-09", days=1))  # 周一
    assert len(result.days) == 1
    assert result.days[0].is_holiday is False
    assert result.days[0].is_weekend is False
    assert result.days[0].crowd_level == "normal"


def test_calendar_weekend():
    """周末检测"""
    result = get_calendar(CalendarInput(date_start="2026-03-14", days=2))  # 周六
    assert result.days[0].is_weekend is True
    assert result.days[0].crowd_level == "high"


# ── 天气+日历 集成到 Planner Core ─────────────────────

def _make_pois(n: int, indoor_ratio: float = 0.3) -> list[POI]:
    """生成测试 POI，部分为室内"""
    pois = []
    indoor_count = int(n * indoor_ratio)
    for i in range(n):
        pois.append(POI(
            id=f"tw{i}",
            name=f"{'室内' if i < indoor_count else '室外'}景点{i}",
            city="北京",
            lat=39.9 + i * 0.01,
            lon=116.4 + i * 0.01,
            themes=["历史"],
            duration_hours=1.5,
            cost=20,
            indoor=i < indoor_count,
        ))
    return pois


def test_planner_with_weather_rainy():
    """雨天应优先安排室内景点"""
    constraints = TripConstraints(city="北京", days=2, pace=Pace.MODERATE)
    profile = UserProfile(themes=["历史"])
    pois = _make_pois(15, indoor_ratio=0.5)

    weather_data = {
        "city": "北京",
        "forecasts": [
            {"date": "2026-07-15", "condition": "中雨", "temp_high": 28, "temp_low": 22, "is_outdoor_friendly": False},
            {"date": "2026-07-16", "condition": "晴", "temp_high": 31, "temp_low": 23, "is_outdoor_friendly": True},
        ],
    }

    itinerary = generate_itinerary(
        constraints, profile, pois, weather_data=weather_data,
    )
    assert len(itinerary.days) == 2

    # 第1天（雨天）day_summary 应包含天气信息
    assert "天气" in itinerary.days[0].day_summary
    assert "雨" in itinerary.days[0].day_summary


def test_planner_with_calendar_holiday():
    """节假日应添加人流量提示"""
    constraints = TripConstraints(city="北京", days=2, pace=Pace.MODERATE)
    profile = UserProfile()
    pois = _make_pois(10)

    calendar_data = {
        "days": [
            {"date": "2026-10-01", "is_holiday": True, "is_weekend": False,
             "holiday_name": "国庆节", "crowd_level": "very_high"},
            {"date": "2026-10-02", "is_holiday": True, "is_weekend": False,
             "holiday_name": "国庆节", "crowd_level": "very_high"},
        ],
    }

    itinerary = generate_itinerary(
        constraints, profile, pois, calendar_data=calendar_data,
    )
    assert len(itinerary.days) == 2
    # 应有人流量相关的 assumption
    assert any("人流量" in a for a in itinerary.assumptions)
    # day_summary 中应有节假日和人流量提示
    assert "国庆节" in itinerary.days[0].day_summary


def test_planner_without_context_data():
    """不传天气/日历数据时仍正常工作"""
    constraints = TripConstraints(city="北京", days=2, pace=Pace.MODERATE)
    profile = UserProfile()
    pois = _make_pois(10)

    itinerary = generate_itinerary(constraints, profile, pois)
    assert len(itinerary.days) == 2
    # 无上下文数据时不崩溃
    for day in itinerary.days:
        assert day.schedule
