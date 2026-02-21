"""Unit tests for real AMap POI adapter local mapping logic."""

from __future__ import annotations

from app.adapters.poi.real import (
    _guess_duration,
    _guess_indoor,
    _guess_themes,
    _theme_keywords,
    _themes_to_keywords,
    search_poi,
)
from app.tools.interfaces import POISearchInput


def test_themes_to_keywords_maps_cn_and_en_tokens():
    keywords = _themes_to_keywords(["\u7f8e\u98df\u591c\u5e02", "history", "\u81ea\u7136\u98ce\u5149"])
    assert "\u9910\u996e\u670d\u52a1" in keywords
    assert "\u98ce\u666f\u540d\u80dc" in keywords


def test_guess_themes_extracts_multiple_labels_from_amap_type():
    amap_type = "\u98ce\u666f\u540d\u80dc;\u516c\u56ed\u5e7f\u573a|\u9910\u996e\u670d\u52a1|\u591c\u95f4\u5a31\u4e50"
    themes = _guess_themes(amap_type)
    assert "\u81ea\u7136\u98ce\u5149" in themes
    assert "\u7f8e\u98df\u591c\u5e02" in themes
    assert "\u591c\u666f\u706f\u5149" in themes


def test_guess_indoor_and_duration_by_type():
    assert _guess_indoor("\u79d1\u6280\u9986|\u535a\u7269\u9986") is True
    assert _guess_indoor("\u98ce\u666f\u540d\u80dc;\u516c\u56ed") is False
    assert _guess_duration("\u9910\u996e\u670d\u52a1") == 1.0
    assert _guess_duration("\u98ce\u666f\u540d\u80dc;\u516c\u56ed") == 2.0


def test_theme_keywords_deduplicates_and_limits():
    keywords = _theme_keywords(["\u81ea\u7136\u98ce\u5149", "history", "\u7f8e\u98df\u591c\u5e02", "\u57ce\u5e02\u5730\u6807", "night"])
    assert len(keywords) == 3
    assert "\u98ce\u666f\u540d\u80dc" in keywords
    assert "\u9910\u996e\u670d\u52a1" in keywords


def test_search_poi_queries_multiple_keywords_and_dedupes(monkeypatch):
    calls: list[str] = []

    def fake_get(_url: str, *, params: dict):
        keyword = str(params.get("keywords", ""))
        calls.append(keyword)
        if keyword == "\u98ce\u666f\u540d\u80dc":
            pois = [
                {"id": "p1", "name": "\u4e2d\u5fc3\u516c\u56ed", "cityname": "\u5317\u4eac", "location": "116.1,39.9", "type": "\u98ce\u666f\u540d\u80dc;\u516c\u56ed"},
                {"id": "p2", "name": "\u57ce\u697c", "cityname": "\u5317\u4eac", "location": "116.2,39.9", "type": "\u98ce\u666f\u540d\u80dc;\u53e4\u5efa\u7b51"},
            ]
        elif keyword == "\u9910\u996e\u670d\u52a1":
            pois = [
                {"id": "p2", "name": "\u57ce\u697c", "cityname": "\u5317\u4eac", "location": "116.2,39.9", "type": "\u98ce\u666f\u540d\u80dc;\u53e4\u5efa\u7b51"},
                {"id": "p3", "name": "\u591c\u5e02", "cityname": "\u5317\u4eac", "location": "116.3,39.9", "type": "\u9910\u996e\u670d\u52a1;\u7f8e\u98df"},
            ]
        else:
            pois = []
        return {"status": "1", "pois": pois}

    monkeypatch.setattr("app.adapters.poi.real._get_api_key", lambda: "dummy")
    monkeypatch.setattr("app.adapters.poi.real.sign_amap_params", lambda payload: payload)
    monkeypatch.setattr("app.adapters.poi.real._http.get", fake_get)

    result = search_poi(
        POISearchInput(
            city="\u5317\u4eac",
            themes=["\u81ea\u7136\u98ce\u5149", "\u7f8e\u98df\u591c\u5e02"],
            max_results=3,
        )
    )

    assert calls[:2] == ["\u98ce\u666f\u540d\u80dc", "\u9910\u996e\u670d\u52a1"]
    assert [poi.id for poi in result] == ["p1", "p2", "p3"]
