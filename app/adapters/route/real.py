"""Real 路线适配器 — 接入高德地图路线规划 API

环境变量: AMAP_API_KEY
高德 API 文档:
  步行: https://lbs.amap.com/api/webservice/guide/api/direction-walking
  公交: https://lbs.amap.com/api/webservice/guide/api/bus
  驾车: https://lbs.amap.com/api/webservice/guide/api/direction-driving
"""

from __future__ import annotations

from app.security.amap_signer import sign_amap_params
from app.security.http_client import SecureHttpClient
from app.security.key_manager import get_key_manager
from app.tools.interfaces import RouteInput, RouteResult, ToolError

# 高德路线规划 API 端点
_ROUTE_URLS = {
    "walking": "https://restapi.amap.com/v3/direction/walking",
    "public_transit": "https://restapi.amap.com/v3/direction/transit/integrated",
    "taxi": "https://restapi.amap.com/v3/direction/driving",
    "driving": "https://restapi.amap.com/v3/direction/driving",
}


def _get_api_key() -> str:
    """通过 KeyManager 获取 Key"""
    km = get_key_manager()
    key = km.get_amap_key(required=False)
    if not key:
        raise ToolError("real_route", "未设置 AMAP_API_KEY 环境变量")
    return key


_http = SecureHttpClient(tool_name="real_route", max_retries=1)


def _format_location(lat: float, lon: float) -> str:
    """高德地图坐标格式: lon,lat（经度在前）"""
    return f"{lon},{lat}"


def _parse_walking_driving(data: dict) -> RouteResult:
    """解析步行/驾车路线结果"""
    route = data.get("route", {})
    paths = route.get("paths", [])
    if not paths:
        raise ToolError("real_route", "高德 API 未返回路线")

    # 取第一条推荐路线
    path = paths[0]
    distance_m = float(path.get("distance", 0))
    duration_s = float(path.get("duration", 0))

    return RouteResult(
        distance_km=round(distance_m / 1000, 2),
        duration_minutes=round(duration_s / 60, 1),
    )


def _parse_transit(data: dict) -> RouteResult:
    """解析公交路线结果"""
    route = data.get("route", {})
    transits = route.get("transits", [])
    if not transits:
        raise ToolError("real_route", "高德公交 API 未返回路线")

    # 取第一条推荐路线
    transit = transits[0]
    distance_m = float(route.get("distance", 0))
    duration_s = float(transit.get("duration", 0))

    return RouteResult(
        distance_km=round(distance_m / 1000, 2),
        duration_minutes=round(duration_s / 60, 1),
    )


# ---------- 兼容 mock_route 的便捷函数（供 distance_validator 直接调用） ----------

_SPEED_MAP_FALLBACK = {
    "walking": 5.0,
    "public_transit": 25.0,
    "taxi": 35.0,
    "driving": 40.0,
}


def estimate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """粗估两点间实际路程 (km)，使用 Haversine × 1.4 系数。

    注：这是离线近似值，真正调用高德 API 走 estimate_route。
    """
    import math
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)) * 1.4


def estimate_travel_time(distance_km: float, mode: str = "public_transit") -> float:
    """估算出行时间 (分钟)，速度表同 mock_route。"""
    speed = _SPEED_MAP_FALLBACK.get(mode, 25.0)
    return (distance_km / speed) * 60


def estimate_route(params: RouteInput) -> RouteResult:
    """
    调用高德地图路线规划 API 获取真实距离和时间。
    带缓存，相同起终点 + 模式 30 分钟内直接返回。
    """
    from app.infrastructure.cache import make_cache_key, route_cache

    cache_key = make_cache_key(
        "route",
        round(params.origin_lat, 4), round(params.origin_lon, 4),
        round(params.dest_lat, 4), round(params.dest_lon, 4),
        params.mode,
    )
    cached = route_cache.get(cache_key)
    if cached is not None:
        return cached
    mode = params.mode if params.mode in _ROUTE_URLS else "public_transit"
    url = _ROUTE_URLS[mode]

    origin = _format_location(params.origin_lat, params.origin_lon)
    destination = _format_location(params.dest_lat, params.dest_lon)

    raw_params: dict[str, str] = {
        "origin": origin,
        "destination": destination,
        "output": "json",
    }

    # 公交需要传 city 参数（必填）
    if mode == "public_transit":
        raw_params["city"] = "全国"

    # 通过签名器注入 key + sig
    request_params = sign_amap_params(raw_params)

    data = _http.get(url, params=request_params)

    if data.get("status") != "1":
        info = data.get("info", "未知错误")
        infocode = data.get("infocode", "")
        raise ToolError("real_route", f"高德路线 API 返回错误: {info} (code={infocode})")

    if mode == "public_transit":
        result = _parse_transit(data)
    else:
        result = _parse_walking_driving(data)

    route_cache.set(cache_key, result)
    return result
