"""Curated Beijing POI metadata regression tests."""

from __future__ import annotations

from app.planner.poi_metadata import get_city_metadata

_REQUIRED_POIS = {
    "故宫博物院",
    "天安门广场",
    "天安门城楼",
    "天坛公园",
    "景山公园",
    "北海公园",
    "中山公园",
    "正阳门城楼",
    "老舍故居",
    "明城墙遗址公园",
    "龙潭公园",
}


def test_beijing_required_pois_covered():
    rows = get_city_metadata("北京")
    names = {row.get("name", "") for row in rows}
    assert _REQUIRED_POIS.issubset(names)


def test_required_pois_have_fact_fields():
    rows = {row.get("name", ""): row for row in get_city_metadata("北京")}
    for name in _REQUIRED_POIS:
        row = rows[name]
        assert "ticket_price" in row
        assert "requires_reservation" in row
        assert row.get("open_hours")
        assert row.get("closed_rules")

