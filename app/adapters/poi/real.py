"""Real POI adapter for AMap place search/detail APIs."""

from __future__ import annotations

import re

from app.domain.models import POI
from app.security.amap_signer import sign_amap_params
from app.security.http_client import SecureHttpClient
from app.security.key_manager import get_key_manager
from app.tools.interfaces import POISearchInput, ToolError

_BASE_URL = "https://restapi.amap.com/v3/place/text"
_DETAIL_URL = "https://restapi.amap.com/v3/place/detail"

_THEME_KEYWORD_MAP: dict[str, str] = {
    "history": "\u98ce\u666f\u540d\u80dc",
    "\u5386\u53f2": "\u98ce\u666f\u540d\u80dc",
    "museum": "\u535a\u7269\u9986",
    "\u535a\u7269\u9986": "\u535a\u7269\u9986",
    "food": "\u9910\u996e\u670d\u52a1",
    "\u7f8e\u98df": "\u9910\u996e\u670d\u52a1",
    "\u591c\u5e02": "\u9910\u996e\u670d\u52a1",
    "nature": "\u98ce\u666f\u540d\u80dc",
    "\u81ea\u7136": "\u98ce\u666f\u540d\u80dc",
    "night": "\u4f11\u95f2\u5a31\u4e50",
    "\u591c\u666f": "\u4f11\u95f2\u5a31\u4e50",
    "family": "\u98ce\u666f\u540d\u80dc",
    "\u4eb2\u5b50": "\u98ce\u666f\u540d\u80dc",
    "shopping": "\u8d2d\u7269\u670d\u52a1",
    "\u8d2d\u7269": "\u8d2d\u7269\u670d\u52a1",
    "landmark": "\u98ce\u666f\u540d\u80dc",
    "\u5730\u6807": "\u98ce\u666f\u540d\u80dc",
}

_INDOOR_KEYWORDS = (
    "\u535a\u7269\u9986",
    "\u7f8e\u672f\u9986",
    "\u5c55\u89c8",
    "\u5546\u573a",
    "\u8d2d\u7269",
    "\u79d1\u6280\u9986",
    "\u9910\u996e",
)

_THEME_GUESS_RULES: tuple[tuple[str, str], ...] = (
    ("\u535a\u7269\u9986", "\u5386\u53f2\u53e4\u8ff9"),
    ("\u7eaa\u5ff5\u9986", "\u5386\u53f2\u53e4\u8ff9"),
    ("\u53e4\u8ff9", "\u5386\u53f2\u53e4\u8ff9"),
    ("\u9910\u996e", "\u7f8e\u98df\u591c\u5e02"),
    ("\u5c0f\u5403", "\u7f8e\u98df\u591c\u5e02"),
    ("\u5496\u5561", "\u5496\u5561\u6587\u827a"),
    ("\u516c\u56ed", "\u81ea\u7136\u98ce\u5149"),
    ("\u98ce\u666f", "\u81ea\u7136\u98ce\u5149"),
    ("\u6e56", "\u81ea\u7136\u98ce\u5149"),
    ("\u5c71", "\u81ea\u7136\u98ce\u5149"),
    ("\u8d2d\u7269", "\u8d2d\u7269\u4f11\u95f2"),
    ("\u5546\u573a", "\u8d2d\u7269\u4f11\u95f2"),
    ("\u9152\u5427", "\u591c\u666f\u706f\u5149"),
    ("\u591c", "\u591c\u666f\u706f\u5149"),
    ("\u4e3b\u9898\u4e50\u56ed", "\u4eb2\u5b50\u4f53\u9a8c"),
    ("\u52a8\u7269\u56ed", "\u4eb2\u5b50\u4f53\u9a8c"),
    ("\u6c34\u65cf\u9986", "\u4eb2\u5b50\u4f53\u9a8c"),
)

_http = SecureHttpClient(tool_name="real_poi", max_retries=1)
_MAX_THEME_KEYWORDS = 3


def _get_api_key() -> str:
    key = get_key_manager().get_amap_key(required=False)
    if not key:
        raise ToolError("real_poi", "AMAP_API_KEY is missing")
    return key


def _split_theme_tokens(themes: list[str]) -> list[str]:
    tokens: list[str] = []
    for theme in themes:
        for token in re.split(r"[|,，;；、\s]+", str(theme).strip().lower()):
            if token:
                tokens.append(token)
    return tokens


def _map_theme_keyword(token: str) -> str:
    direct = _THEME_KEYWORD_MAP.get(token)
    if direct:
        return direct
    for hint, mapped in _THEME_KEYWORD_MAP.items():
        if hint and hint in token:
            return mapped
    return token


def _themes_to_keywords(themes: list[str]) -> str:
    keywords: list[str] = []
    for token in _split_theme_tokens(themes):
        keywords.append(_map_theme_keyword(token))
    return "|".join(keywords) if keywords else "\u98ce\u666f\u540d\u80dc"


def _theme_keywords(themes: list[str], *, limit: int = _MAX_THEME_KEYWORDS) -> list[str]:
    seen: set[str] = set()
    keywords: list[str] = []
    for token in _split_theme_tokens(themes):
        mapped = _map_theme_keyword(token).strip()
        if not mapped or mapped in seen:
            continue
        seen.add(mapped)
        keywords.append(mapped)
        if len(keywords) >= max(1, limit):
            break
    return keywords or ["\u98ce\u666f\u540d\u80dc"]


def _guess_themes(amap_type: str) -> list[str]:
    amap_type = str(amap_type or "")
    guessed: list[str] = []
    for keyword, theme in _THEME_GUESS_RULES:
        if keyword in amap_type and theme not in guessed:
            guessed.append(theme)
    return guessed or ["\u57ce\u5e02\u5730\u6807"]


def _guess_indoor(amap_type: str) -> bool:
    amap_type = str(amap_type or "")
    return any(keyword in amap_type for keyword in _INDOOR_KEYWORDS)


def _guess_duration(amap_type: str) -> float:
    amap_type = str(amap_type or "")
    if "\u535a\u7269\u9986" in amap_type or "\u5c55\u89c8" in amap_type:
        return 2.5
    if "\u516c\u56ed" in amap_type or "\u98ce\u666f" in amap_type:
        return 2.0
    if "\u9910\u996e" in amap_type:
        return 1.0
    if "\u8d2d\u7269" in amap_type or "\u5546\u573a" in amap_type:
        return 1.5
    return 1.5


def _parse_location(location: str) -> tuple[float, float]:
    parts = str(location or "").split(",")
    if len(parts) != 2:
        return 0.0, 0.0
    try:
        return float(parts[1]), float(parts[0])  # amap uses lon,lat
    except ValueError:
        return 0.0, 0.0


def _safe_str(value: object, default: str = "") -> str:
    if isinstance(value, str):
        return value
    if value is None or (isinstance(value, list) and len(value) == 0):
        return default
    return str(value)


def _amap_poi_to_model(raw: dict, idx: int) -> POI:
    location = _safe_str(raw.get("location"), "0,0")
    lat, lon = _parse_location(location)
    amap_type = _safe_str(raw.get("type"))

    biz_ext = raw.get("biz_ext")
    open_time = None
    if isinstance(biz_ext, dict):
        open_time = _safe_str(biz_ext.get("open_time")) or None

    return POI(
        id=_safe_str(raw.get("id"), f"amap_{idx}"),
        name=_safe_str(raw.get("name"), "unknown"),
        city=_safe_str(raw.get("cityname")),
        lat=lat,
        lon=lon,
        themes=_guess_themes(amap_type),
        duration_hours=_guess_duration(amap_type),
        cost=0.0,
        indoor=_guess_indoor(amap_type),
        open_time=open_time,
        description=_safe_str(raw.get("address")),
        source_category=amap_type,
    )


def _query_poi_page(params: POISearchInput, *, keyword: str, offset: int) -> list[POI]:
    data = _http.get(
        _BASE_URL,
        params=sign_amap_params(
            {
                "keywords": keyword,
                "city": params.city,
                "citylimit": "true",
                "offset": str(min(max(1, offset), 25)),
                "page": "1",
                "output": "json",
                "extensions": "all",
            }
        ),
    )
    if data.get("status") != "1":
        raise ToolError("real_poi", f"amap error: {data.get('info', 'unknown')} code={data.get('infocode', '')}")

    rows: list[POI] = []
    for idx, raw in enumerate(data.get("pois", [])):
        poi = _amap_poi_to_model(raw, idx)
        if params.indoor is not None and poi.indoor != params.indoor:
            continue
        rows.append(poi)
    return rows


def _merge_unique_pois(existing: list[POI], incoming: list[POI], *, limit: int) -> list[POI]:
    rows = list(existing)
    seen = {poi.id for poi in rows}
    for poi in incoming:
        if poi.id in seen:
            continue
        rows.append(poi)
        seen.add(poi.id)
        if len(rows) >= max(1, limit):
            break
    return rows


def search_poi(params: POISearchInput) -> list[POI]:
    from app.infrastructure.cache import make_cache_key, poi_cache

    _get_api_key()
    cache_key = make_cache_key("poi_search", params.city, params.themes, params.indoor, params.max_results)
    cached = poi_cache.get(cache_key)
    if cached is not None:
        return cached

    results: list[POI] = []
    keywords = _theme_keywords(params.themes)
    query_count = min(len(keywords), _MAX_THEME_KEYWORDS)
    query_keywords = keywords[:query_count]
    per_query_limit = max(6, min(25, (params.max_results + query_count - 1) // query_count + 2))

    for keyword in query_keywords:
        rows = _query_poi_page(params, keyword=keyword, offset=per_query_limit)
        results = _merge_unique_pois(results, rows, limit=params.max_results)
        if len(results) >= params.max_results:
            break

    if len(results) < params.max_results and "\u98ce\u666f\u540d\u80dc" not in query_keywords:
        fallback_rows = _query_poi_page(params, keyword="\u98ce\u666f\u540d\u80dc", offset=per_query_limit)
        results = _merge_unique_pois(results, fallback_rows, limit=params.max_results)

    poi_cache.set(cache_key, results)
    return results


def get_poi_detail(poi_id: str) -> POI:
    _get_api_key()
    data = _http.get(_DETAIL_URL, params=sign_amap_params({"id": poi_id, "output": "json"}))
    if data.get("status") != "1":
        raise ToolError("real_poi", f"amap detail error: {data.get('info', 'unknown')}")
    pois_raw = data.get("pois", [])
    if not pois_raw:
        raise ToolError("real_poi", f"POI not found: {poi_id}")
    return _amap_poi_to_model(pois_raw[0], 0)
