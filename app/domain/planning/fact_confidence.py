"""Annotate fact source_type and field_confidence without changing unknown rules."""

from __future__ import annotations

from app.domain.models import POI

_CRITICAL_FACT_FIELDS = ("ticket_price", "reservation_required", "open_hours", "closed_rules")


def _value_present(poi: POI, field_name: str) -> bool:
    value = getattr(poi, field_name, None)
    if field_name == "ticket_price":
        return float(value or 0.0) > 0.0 or float(poi.cost or 0.0) > 0.0
    if field_name == "reservation_required":
        return bool(poi.requires_reservation or poi.reservation_required)
    return bool(value)


def _field_confidence(poi: POI, field_name: str, source_type: str) -> float:
    if source_type != "data":
        return 0.25
    return 0.90 if _value_present(poi, field_name) else 0.65


def annotate_poi_fact_confidence(poi: POI) -> POI:
    updated = poi.model_copy(deep=True)
    fact_sources = dict(updated.fact_sources)
    for field in _CRITICAL_FACT_FIELDS:
        base_source = str(fact_sources.get(field, "unknown")).strip().lower()
        source_type = "data" if base_source == "data" else "unknown"
        confidence = _field_confidence(updated, field, source_type)
        fact_sources[f"{field}_source_type"] = source_type
        fact_sources[f"{field}_field_confidence"] = f"{confidence:.2f}"
    updated.fact_sources = fact_sources
    return updated


def annotate_pois_fact_confidence(pois: list[POI]) -> list[POI]:
    return [annotate_poi_fact_confidence(poi) for poi in pois]


__all__ = ["annotate_poi_fact_confidence", "annotate_pois_fact_confidence"]
