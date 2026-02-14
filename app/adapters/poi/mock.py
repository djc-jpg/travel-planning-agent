"""Mock POI adapter loading local JSON data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from app.domain.models import POI
from app.shared.exceptions import ToolError
from app.tools.interfaces import POISearchInput

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "poi_v1.json"
_cache: Optional[list[dict]] = None


def _load_data() -> list[dict]:
    global _cache
    if _cache is not None:
        return _cache
    if not DATA_FILE.exists():
        raise ToolError("mock_poi", f"Data file not found: {DATA_FILE}")
    with open(DATA_FILE, encoding="utf-8") as f:
        _cache = json.load(f)
    return _cache


def search_poi(params: POISearchInput) -> list[POI]:
    results: list[POI] = []
    for raw in _load_data():
        if raw["city"] != params.city:
            continue
        if params.indoor is not None and raw.get("indoor") != params.indoor:
            continue
        if params.themes and not (set(params.themes) & set(raw.get("themes", []))):
            continue
        results.append(POI(**raw))
        if len(results) >= params.max_results:
            break
    return results


def get_poi_detail(poi_id: str) -> POI:
    for raw in _load_data():
        if raw["id"] == poi_id:
            return POI(**raw)
    raise ToolError("mock_poi", f"POI not found: {poi_id}")

