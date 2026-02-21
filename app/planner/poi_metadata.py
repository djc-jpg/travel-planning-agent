"""Curated POI metadata loader with city hotplug support."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.domain.models import POI

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_LEGACY_BEIJING_FILE = _DATA_DIR / "poi_beijing.json"
_CITIES_DIR = _DATA_DIR / "cities"
_DEFAULT_FOOD_NEARBY = 35.0
_CRITICAL_FACT_FIELDS = (
    "ticket_price",
    "reservation_required",
    "open_hours",
    "closed_rules",
)

_CITY_ALIASES = {
    "beijing": "beijing",
    "北京": "beijing",
}


def _city_key(city: str) -> str:
    raw = city.strip()
    if not raw:
        return ""
    return _CITY_ALIASES.get(raw, raw.lower())


def _city_file(city_key: str) -> Path | None:
    if not city_key:
        return None
    if city_key == "beijing" and _LEGACY_BEIJING_FILE.exists():
        return _LEGACY_BEIJING_FILE

    candidate = _CITIES_DIR / city_key / "poi.json"
    if candidate.exists():
        return candidate
    return None


@lru_cache(maxsize=64)
def _load_city_rows(city_key: str) -> list[dict[str, Any]]:
    file_path = _city_file(city_key)
    if file_path is None:
        return []

    with open(file_path, encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict):
            rows.append(dict(item))
    return rows


def has_curated_city(city: str) -> bool:
    return bool(_load_city_rows(_city_key(city)))


def get_city_metadata(city: str) -> list[dict]:
    return list(_load_city_rows(_city_key(city)))


def find_metadata_by_name(name: str) -> dict | None:
    norm = name.strip()
    if not norm:
        return None
    for city_entry in _CITIES_DIR.glob("*/poi.json"):
        city_key = city_entry.parent.name.lower()
        for row in _load_city_rows(city_key):
            if str(row.get("name", "")).strip() == norm:
                return dict(row)
    for row in _load_city_rows("beijing"):
        if str(row.get("name", "")).strip() == norm:
            return dict(row)
    return None


def _themes_score(row: dict, themes: list[str]) -> int:
    if not themes:
        return 0
    row_themes = set(row.get("themes", []))
    return len(row_themes & set(themes))


def _fact_sources_from_row(row: dict) -> dict[str, str]:
    raw = row.get("fact_sources")
    if isinstance(raw, dict):
        src = {str(k): str(v) for k, v in raw.items()}
    else:
        src = {}

    for key in _CRITICAL_FACT_FIELDS:
        src.setdefault(key, "data")
    return src


def _to_poi(row: dict, city_key: str) -> POI:
    ticket_price = float(row.get("ticket_price", row.get("cost", 0.0)) or 0.0)
    requires_reservation = bool(
        row.get(
            "requires_reservation",
            row.get("reservation_required", False),
        )
    )
    open_hours = str(row.get("open_hours", row.get("open_time", "")) or "")
    closed_rules = str(row.get("closed_rules", "") or "")
    default_source = "poi_beijing" if city_key == "beijing" else f"city_{city_key}"
    metadata_source = str(row.get("metadata_source", "")).strip() or default_source

    return POI(
        id=str(row["id"]),
        name=str(row["name"]),
        city=str(row.get("city", city_key)),
        lat=float(row.get("lat", 0.0)),
        lon=float(row.get("lon", 0.0)),
        themes=list(row.get("themes", [])),
        duration_hours=float(row.get("duration_hours", 1.5)),
        cost=float(row.get("cost", ticket_price)),
        indoor=bool(row.get("indoor", False)),
        open_time=open_hours or None,
        open_hours=open_hours or None,
        description=str(row.get("notes", row.get("description", ""))),
        requires_reservation=requires_reservation,
        reservation_required=requires_reservation,
        reservation_days_ahead=int(row.get("reservation_days_ahead", 0)),
        closed_rules=closed_rules,
        closed_weekdays=list(row.get("closed_weekdays", [])),
        metadata_source=metadata_source,
        cluster=str(row.get("cluster", "")),
        ticket_price=ticket_price,
        fact_sources=_fact_sources_from_row(row),
        is_verified=bool(row.get("is_verified", False)),
        food_min_nearby=float(row.get("food_min_nearby", _DEFAULT_FOOD_NEARBY)),
    )


def get_city_pois(city: str, themes: list[str] | None = None, max_results: int = 30) -> list[POI]:
    key = _city_key(city)
    rows = _load_city_rows(key)
    if not rows:
        return []

    selected = rows
    if themes:
        selected = sorted(rows, key=lambda item: _themes_score(item, themes), reverse=True)

    pois: list[POI] = []
    for row in selected:
        try:
            poi = _to_poi(row, key)
        except Exception:
            continue
        pois.append(poi)
        if len(pois) >= max_results:
            break
    return pois


__all__ = [
    "find_metadata_by_name",
    "get_city_metadata",
    "get_city_pois",
    "has_curated_city",
]
