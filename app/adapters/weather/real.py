"""Real 天气适配器 — 接入高德地图天气查询 API

环境变量: AMAP_API_KEY
高德天气 API 文档: https://lbs.amap.com/api/webservice/guide/api/weatherinfo

说明:
  - 高德天气 API 免费，extensions=all 返回 4 天预报
  - 超过 4 天的部分自动用 mock 兜底补充
  - 城市参数使用 adcode（行政区划代码），内置主要城市映射
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.security.amap_signer import sign_amap_params
from app.security.http_client import SecureHttpClient
from app.security.key_manager import get_key_manager
from app.tools.interfaces import DayWeather, WeatherInput, WeatherResult, ToolError

_BASE_URL = "https://restapi.amap.com/v3/weather/weatherInfo"

# 城市名 → 高德 adcode 映射（主要旅游城市）
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
    "桂林": "450300",
    "昆明": "530100",
    "拉萨": "540100",
    "哈尔滨": "230100",
    "天津": "120000",
    "沈阳": "210100",
    "郑州": "410100",
    "济南": "370100",
    "福州": "350100",
    "合肥": "340100",
    "南昌": "360100",
    "贵阳": "520100",
    "海口": "460100",
    "银川": "640100",
    "西宁": "630100",
    "兰州": "620100",
    "呼和浩特": "150100",
    "乌鲁木齐": "650100",
    "太原": "140100",
    "石家庄": "130100",
    "长春": "220100",
    "南宁": "450100",
}

# 高德天气状况 → 是否适合户外
_BAD_WEATHER_KEYWORDS = {"雨", "雪", "雾", "霾", "暴", "冰雹", "沙尘"}


def _get_api_key() -> str:
    """通过 KeyManager 获取 Key"""
    km = get_key_manager()
    key = km.get_amap_key(required=False)
    if not key:
        raise ToolError("real_weather", "未设置 AMAP_API_KEY 环境变量")
    return key


_http = SecureHttpClient(tool_name="real_weather", max_retries=1)


def _is_outdoor_friendly(condition: str) -> bool:
    """判断天气是否适合户外"""
    return not any(kw in condition for kw in _BAD_WEATHER_KEYWORDS)


def _simplify_condition(condition: str) -> str:
    """统一天气描述格式"""
    # 高德返回的天气如 "多云"、"小雨"、"晴" 等，基本可直接使用
    return condition if condition else "未知"


def get_weather(params: WeatherInput) -> WeatherResult:
    """
    调用高德天气 API 获取天气预报。

    - extensions=all: 返回未来 4 天预报（含当天）
    - 超过 4 天的部分用 mock 兜底
    - 找不到 adcode 时回退 mock
    """
    _get_api_key()

    # 查找城市 adcode
    adcode = _CITY_ADCODE.get(params.city)
    if not adcode:
        # 未收录城市，回退 mock
        from app.adapters.weather.mock import get_weather as mock_get_weather
        return mock_get_weather(params)

    try:
        request_params = sign_amap_params({
            "city": adcode,
            "extensions": "all",
            "output": "json",
        })
        data = _http.get(_BASE_URL, params=request_params)
    except Exception:
        # 网络失败，回退 mock
        from app.adapters.weather.mock import get_weather as mock_get_weather
        return mock_get_weather(params)

    if data.get("status") != "1":
        from app.adapters.weather.mock import get_weather as mock_get_weather
        return mock_get_weather(params)

    # 解析预报数据
    forecasts_raw = data.get("forecasts", [])
    if not forecasts_raw:
        from app.adapters.weather.mock import get_weather as mock_get_weather
        return mock_get_weather(params)

    casts = forecasts_raw[0].get("casts", [])  # 最多 4 天

    # 解析用户请求的起始日期
    try:
        start_date = datetime.strptime(params.date_start, "%Y-%m-%d").date()
    except ValueError:
        start_date = datetime.now().date()

    forecasts: list[DayWeather] = []

    for i in range(params.days):
        target_date = start_date + timedelta(days=i)
        # 查找 API 返回中是否有匹配日期
        matched = None
        for cast in casts:
            cast_date_str = cast.get("date", "")
            try:
                cast_date = datetime.strptime(cast_date_str, "%Y-%m-%d").date()
                if cast_date == target_date:
                    matched = cast
                    break
            except ValueError:
                continue

        if matched:
            # 使用白天天气
            condition = _simplify_condition(matched.get("dayweather", ""))
            try:
                temp_high = float(matched.get("daytemp", 0))
            except (ValueError, TypeError):
                temp_high = 0.0
            try:
                temp_low = float(matched.get("nighttemp", 0))
            except (ValueError, TypeError):
                temp_low = 0.0

            forecasts.append(DayWeather(
                date=target_date.strftime("%Y-%m-%d"),
                condition=condition,
                temp_high=temp_high,
                temp_low=temp_low,
                is_outdoor_friendly=_is_outdoor_friendly(condition),
            ))
        else:
            # 超出 API 预报范围，用 mock 补充该天
            from app.adapters.weather.mock import get_weather as mock_get_weather
            mock_result = mock_get_weather(WeatherInput(
                city=params.city,
                date_start=target_date.strftime("%Y-%m-%d"),
                days=1,
            ))
            if mock_result.forecasts:
                forecasts.append(mock_result.forecasts[0])
            else:
                forecasts.append(DayWeather(
                    date=target_date.strftime("%Y-%m-%d"),
                    condition="未知",
                    temp_high=20,
                    temp_low=10,
                    is_outdoor_friendly=True,
                ))

    return WeatherResult(city=params.city, forecasts=forecasts)
