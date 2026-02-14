"""Real POI 适配器 — 接入高德地图 POI 搜索 API

环境变量: AMAP_API_KEY
高德 API 文档: https://lbs.amap.com/api/webservice/guide/api/search
"""

from __future__ import annotations

from app.domain.models import POI
from app.security.amap_signer import sign_amap_params
from app.security.http_client import SecureHttpClient
from app.security.key_manager import get_key_manager
from app.tools.interfaces import POISearchInput, ToolError

_BASE_URL = "https://restapi.amap.com/v3/place/text"

# 主题 → 高德 POI 类型关键词映射
_THEME_TYPE_MAP: dict[str, str] = {
    "历史": "风景名胜|博物馆|纪念馆|古迹",
    "美食": "餐饮服务",
    "自然": "风景名胜|公园广场",
    "文艺": "博物馆|展览馆|美术馆|剧院",
    "网红": "风景名胜|购物服务",
    "亲子": "游乐园|动物园|水族馆",
    "购物": "购物服务|商场",
    "夜景": "风景名胜|休闲娱乐",
    "艺术": "美术馆|展览馆|画廊",
    "博物馆": "博物馆",
    "园林": "公园广场|风景名胜",
    "地标": "风景名胜|地标建筑",
    "科技": "科技馆|展览馆",
}

# 高德 POI 类型中可推断 indoor 的关键词
_INDOOR_KEYWORDS = {"博物馆", "展览馆", "美术馆", "商场", "购物", "科技馆", "餐饮"}


def _get_api_key() -> str:
    """通过 KeyManager 获取 Key（集中管理 + 审计）"""
    km = get_key_manager()
    key = km.get_amap_key(required=False)
    if not key:
        raise ToolError("real_poi", "未设置 AMAP_API_KEY 环境变量")
    return key


_http = SecureHttpClient(tool_name="real_poi", max_retries=1)


def _themes_to_keywords(themes: list[str]) -> str:
    """将用户主题转为高德搜索关键词"""
    keywords: list[str] = []
    for t in themes:
        if t in _THEME_TYPE_MAP:
            keywords.append(_THEME_TYPE_MAP[t].split("|")[0])  # 取第一个
        else:
            keywords.append(t)
    return "|".join(keywords) if keywords else "风景名胜"


def _guess_themes(amap_type: str) -> list[str]:
    """从高德 type 字段反推主题标签"""
    themes: list[str] = []
    type_lower = amap_type.lower() if amap_type else ""
    mapping = {
        "博物馆": "历史",
        "纪念馆": "历史",
        "古迹": "历史",
        "餐饮": "美食",
        "小吃": "美食",
        "公园": "自然",
        "风景": "自然",
        "美术馆": "艺术",
        "展览": "文艺",
        "购物": "购物",
        "商场": "购物",
        "游乐": "亲子",
        "动物园": "亲子",
    }
    for kw, theme in mapping.items():
        if kw in type_lower and theme not in themes:
            themes.append(theme)
    return themes or ["地标"]


def _guess_indoor(amap_type: str) -> bool:
    """从高德 type 推断是否室内"""
    if not amap_type:
        return False
    return any(kw in amap_type for kw in _INDOOR_KEYWORDS)


def _guess_duration(amap_type: str) -> float:
    """按 POI 类型估算游玩时长（小时）"""
    if not amap_type:
        return 1.5
    if "博物馆" in amap_type or "展览" in amap_type:
        return 2.5
    if "公园" in amap_type or "风景" in amap_type:
        return 2.0
    if "餐饮" in amap_type:
        return 1.0
    if "购物" in amap_type or "商场" in amap_type:
        return 1.5
    return 1.5


def _parse_location(location: str) -> tuple[float, float]:
    """解析 '116.397428,39.90923' → (lon, lat) → 返回 (lat, lon)"""
    parts = location.split(",")
    if len(parts) == 2:
        return float(parts[1]), float(parts[0])  # 高德返回 lon,lat
    return 0.0, 0.0


def _safe_str(val: object, default: str = "") -> str:
    """高德 API 部分字段在无数据时返回 [] 而非空字符串，统一转为 str。"""
    if isinstance(val, str):
        return val
    if val is None or (isinstance(val, list) and len(val) == 0):
        return default
    return str(val)


def _amap_poi_to_model(raw: dict, idx: int) -> POI:
    """将高德 API 返回的单条 POI 转换为 domain POI"""
    location = _safe_str(raw.get("location"), "0,0")
    lat, lon = _parse_location(location)
    amap_type = _safe_str(raw.get("type"))

    # 处理 biz_ext 中的 open_time（可能是 [] / dict / str）
    biz_ext = raw.get("biz_ext")
    open_time = None
    if isinstance(biz_ext, dict):
        ot = biz_ext.get("open_time")
        open_time = _safe_str(ot) or None

    return POI(
        id=_safe_str(raw.get("id"), f"amap_{idx}"),
        name=_safe_str(raw.get("name"), "未知"),
        city=_safe_str(raw.get("cityname")),
        lat=lat,
        lon=lon,
        themes=_guess_themes(amap_type),
        duration_hours=_guess_duration(amap_type),
        cost=0.0,
        indoor=_guess_indoor(amap_type),
        open_time=open_time,
        description=_safe_str(raw.get("address")),
    )


def search_poi(params: POISearchInput) -> list[POI]:
    """
    调用高德地图 POI 搜索 API。
    使用关键词搜索 + 城市过滤。带缓存，相同查询 10 分钟内直接返回。
    """
    from app.infrastructure.cache import make_cache_key, poi_cache

    cache_key = make_cache_key("poi_search", params.city, params.themes, params.indoor, params.max_results)
    cached = poi_cache.get(cache_key)
    if cached is not None:
        return cached

    keywords = _themes_to_keywords(params.themes)

    raw_params = {
        "keywords": keywords,
        "city": params.city,
        "citylimit": "true",
        "offset": str(min(params.max_results, 25)),  # 高德单页最多 25
        "page": "1",
        "output": "json",
        "extensions": "all",
    }
    # 通过签名器注入 key + sig（如果配置了 AMAP_SECRET）
    request_params = sign_amap_params(raw_params)

    data = _http.get(_BASE_URL, params=request_params)

    if data.get("status") != "1":
        info = data.get("info", "未知错误")
        infocode = data.get("infocode", "")
        raise ToolError("real_poi", f"高德 API 返回错误: {info} (code={infocode})")

    pois_raw = data.get("pois", [])
    results: list[POI] = []

    for idx, raw in enumerate(pois_raw):
        poi = _amap_poi_to_model(raw, idx)
        # 如果用户指定了 indoor 过滤
        if params.indoor is not None and poi.indoor != params.indoor:
            continue
        results.append(poi)
        if len(results) >= params.max_results:
            break

    # 写入缓存
    poi_cache.set(cache_key, results)
    return results


def get_poi_detail(poi_id: str) -> POI:
    """
    按 ID 查询 POI 详情（使用高德 POI 详情 API）。
    """
    detail_url = "https://restapi.amap.com/v3/place/detail"
    request_params = sign_amap_params({"id": poi_id, "output": "json"})

    data = _http.get(detail_url, params=request_params)

    if data.get("status") != "1":
        raise ToolError("real_poi", f"高德 POI 详情失败: {data.get('info', '未知')}")

    pois_raw = data.get("pois", [])
    if not pois_raw:
        raise ToolError("real_poi", f"POI 未找到: {poi_id}")

    return _amap_poi_to_model(pois_raw[0], 0)
