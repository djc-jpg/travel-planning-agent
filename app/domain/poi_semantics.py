"""POI semantic classification and filtering helpers."""

from __future__ import annotations

from app.domain.enums import PoiSemanticType
from app.domain.models import POI

_INFRASTRUCTURE_CATEGORY_KEYWORDS = (
    "\u4ea4\u901a\u8bbe\u65bd",
    "\u5ba4\u5185\u8bbe\u65bd",
    "\u505c\u8f66\u573a",
    "\u516c\u4ea4",
    "\u5730\u94c1",
    "\u9053\u8def\u9644\u5c5e",
    "\u901a\u884c\u8bbe\u65bd",
    "transport",
    "station",
    "terminal",
)
_INFRASTRUCTURE_TEXT_KEYWORDS = (
    "\u505c\u8f66\u573a",
    "\u505c\u8f66",
    "\u4e0a\u8f66\u70b9",
    "\u4e0b\u8f66\u70b9",
    "\u7f51\u7ea6\u8f66",
    "\u516c\u4ea4\u7ad9",
    "\u5730\u94c1\u7ad9",
    "\u670d\u52a1\u533a",
    "\u822a\u7ad9\u697c",
    "\u706b\u8f66\u7ad9",
    "\u9ad8\u94c1\u7ad9",
    "\u5165\u53e3",
    "\u51fa\u53e3",
    "parking",
    "pickup",
    "dropoff",
    "station",
    "terminal",
    "toll",
)
_NON_EXPERIENCE_SERVICE_KEYWORDS = (
    "\u8425\u4e1a\u5385",
    "\u8425\u4e1a\u90e8",
    "\u552e\u7968\u5904",
    "\u552e\u7968\u70b9",
    "\u5ba2\u670d\u4e2d\u5fc3",
    "\u670d\u52a1\u4e2d\u5fc3",
    "\u7406\u53d1",
    "\u9020\u578b",
    "\u8fde\u9501",
    "\u8054\u901a",
    "\u79fb\u52a8",
    "\u7535\u4fe1",
    "\u94f6\u884c",
    "\u4fbf\u5229\u5e97",
    "\u836f\u5e97",
    "\u5feb\u9012",
    "\u7269\u6d41",
    "ticket office",
    "business hall",
    "service center",
    "hair salon",
    "telecom",
    "bank branch",
)
_EXPERIENCE_KEYWORDS = (
    "\u666f\u533a",
    "\u98ce\u666f",
    "\u535a\u7269\u9986",
    "\u7f8e\u672f\u9986",
    "\u5c55\u89c8",
    "\u516c\u56ed",
    "\u53e4\u8ff9",
    "\u5386\u53f2",
    "\u591c\u5e02",
    "\u9910\u996e",
    "\u7f8e\u98df",
    "\u5267\u9662",
    "\u6f14\u827a",
    "\u5546\u5708",
    "\u5546\u573a",
    "\u52a8\u7269\u56ed",
    "\u690d\u7269\u56ed",
    "\u4e50\u56ed",
    "museum",
    "park",
    "scenic",
    "gallery",
    "theater",
    "market",
)
_GENERIC_THEMES = {
    "",
    "unknown",
    "general",
    "landmark",
    "scenic",
    "\u5730\u6807",
    "\u57ce\u5e02\u5730\u6807",
}


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _normalize(text: str) -> str:
    return str(text or "").strip().lower()


def _poi_text_blob(poi: POI) -> str:
    return _normalize(" ".join([poi.name, poi.description, poi.source_category, " ".join(poi.themes)]))


def classify_poi_semantic(poi: POI) -> tuple[PoiSemanticType, float]:
    category = _normalize(poi.source_category)
    text_blob = _poi_text_blob(poi)

    if _contains_any(category, _INFRASTRUCTURE_CATEGORY_KEYWORDS):
        return PoiSemanticType.INFRASTRUCTURE, 0.95
    if _contains_any(text_blob, _INFRASTRUCTURE_TEXT_KEYWORDS):
        return PoiSemanticType.INFRASTRUCTURE, 0.9
    if _contains_any(text_blob, _NON_EXPERIENCE_SERVICE_KEYWORDS):
        return PoiSemanticType.INFRASTRUCTURE, 0.88
    if _contains_any(text_blob, _EXPERIENCE_KEYWORDS):
        return PoiSemanticType.EXPERIENCE, 0.85

    themed = {_normalize(theme) for theme in poi.themes}
    themed.discard("")
    if themed and not themed.issubset(_GENERIC_THEMES):
        return PoiSemanticType.EXPERIENCE, 0.6
    return PoiSemanticType.UNKNOWN, 0.2


def tag_poi_semantics(poi: POI) -> POI:
    semantic_type, semantic_confidence = classify_poi_semantic(poi)
    return poi.model_copy(
        update={
            "semantic_type": semantic_type,
            "semantic_confidence": semantic_confidence,
        },
        deep=True,
    )


def filter_semantic_candidates(
    pois: list[POI],
    *,
    strict_external: bool,
    minimum_count: int,
) -> tuple[list[POI], dict[str, int]]:
    tagged = [tag_poi_semantics(poi) for poi in pois]
    experience = [poi for poi in tagged if poi.semantic_type == PoiSemanticType.EXPERIENCE]
    unknown = [poi for poi in tagged if poi.semantic_type == PoiSemanticType.UNKNOWN]
    infrastructure = [poi for poi in tagged if poi.semantic_type == PoiSemanticType.INFRASTRUCTURE]

    selected = list(experience)
    if not strict_external and len(selected) < minimum_count:
        selected.extend(unknown[: max(minimum_count - len(selected), 0)])

    stats = {
        "selected": len(selected),
        "experience": len(experience),
        "unknown": len(unknown),
        "infrastructure": len(infrastructure),
    }
    return selected, stats


__all__ = [
    "classify_poi_semantic",
    "filter_semantic_candidates",
    "tag_poi_semantics",
]
