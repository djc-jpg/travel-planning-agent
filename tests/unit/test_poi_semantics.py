"""Semantic tagging tests for POI quality control."""

from __future__ import annotations

from app.domain.enums import PoiSemanticType
from app.domain.models import POI
from app.domain.poi_semantics import classify_poi_semantic, filter_semantic_candidates, tag_poi_semantics


def _poi(
    pid: str,
    name: str,
    *,
    source_category: str = "",
    description: str = "",
    themes: list[str] | None = None,
) -> POI:
    return POI(
        id=pid,
        name=name,
        city="Guiyang",
        source_category=source_category,
        description=description,
        themes=themes or [],
    )


def test_classify_parking_category_as_infrastructure():
    poi = _poi("p1", "Museum Parking Lot", source_category="\u4ea4\u901a\u8bbe\u65bd\u670d\u52a1;\u505c\u8f66\u573a")
    semantic_type, _confidence = classify_poi_semantic(poi)
    assert semantic_type == PoiSemanticType.INFRASTRUCTURE


def test_classify_museum_as_experience():
    poi = _poi("p2", "City Museum", source_category="\u98ce\u666f\u540d\u80dc;\u535a\u7269\u9986", themes=["history"])
    semantic_type, _confidence = classify_poi_semantic(poi)
    assert semantic_type == PoiSemanticType.EXPERIENCE


def test_classify_sparse_payload_as_unknown():
    poi = _poi("p3", "Point-A", source_category="")
    semantic_type, _confidence = classify_poi_semantic(poi)
    assert semantic_type == PoiSemanticType.UNKNOWN


def test_classify_business_service_points_as_infrastructure():
    rows = [
        _poi("b1", "\u4e2d\u56fd\u8054\u901a\u4e0a\u6392\u8857\u8425\u4e1a\u5385"),
        _poi("b2", "\u4e1c\u5c3c\u9020\u578b\u8fde\u9501(X130\u5e97)"),
        _poi("b3", "\u666f\u533a\u552e\u7968\u5904"),
    ]
    for poi in rows:
        semantic_type, _confidence = classify_poi_semantic(poi)
        assert semantic_type == PoiSemanticType.INFRASTRUCTURE


def test_filter_semantic_candidates_blocks_infrastructure_and_uses_unknown_only_when_non_strict():
    infra = _poi("i1", "North Gate Pickup Point", source_category="\u4ea4\u901a\u8bbe\u65bd\u670d\u52a1")
    unknown = _poi("u1", "Unknown Spot")
    exp = _poi("e1", "West Lake Park", source_category="\u98ce\u666f\u540d\u80dc")

    non_strict, stats_non_strict = filter_semantic_candidates(
        [infra, unknown, exp],
        strict_external=False,
        minimum_count=2,
    )
    strict, stats_strict = filter_semantic_candidates(
        [infra, unknown, exp],
        strict_external=True,
        minimum_count=2,
    )

    assert stats_non_strict["infrastructure"] == 1
    assert all(poi.semantic_type != PoiSemanticType.INFRASTRUCTURE for poi in non_strict)
    assert [poi.id for poi in non_strict] == ["e1", "u1"]
    assert [poi.id for poi in strict] == ["e1"]
    assert stats_strict["unknown"] == 1


def test_tag_poi_semantics_writes_semantic_fields():
    poi = _poi("p4", "Downtown Parking")
    tagged = tag_poi_semantics(poi)

    assert tagged.semantic_type == PoiSemanticType.INFRASTRUCTURE
    assert tagged.semantic_confidence > 0


def test_classify_real_world_pickup_and_parking_names_as_infrastructure():
    rows = [
        _poi("g1", "\u8d35\u5dde\u7701\u535a\u7269\u9986\u5730\u4e0b\u505c\u8f66\u573a"),
        _poi("g2", "\u8d35\u5dde\u7701\u535a\u7269\u9986\u5185\u90e8\u505c\u8f66\u573a"),
        _poi("g3", "\u8d35\u5dde\u7701\u535a\u7269\u9986-\u5357\u95e8(\u7f51\u7ea6\u8f66\u4e0a\u8f66\u70b9)"),
        _poi("g4", "\u8d35\u5dde\u5730\u8d28\u535a\u7269\u9986\u505c\u8f66\u573a", source_category="\u98ce\u666f\u540d\u80dc;\u535a\u7269\u9986"),
    ]
    for poi in rows:
        semantic_type, _confidence = classify_poi_semantic(poi)
        assert semantic_type == PoiSemanticType.INFRASTRUCTURE
