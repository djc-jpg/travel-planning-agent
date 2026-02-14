"""POI adapters."""

from app.adapters.poi.mock import get_poi_detail as mock_get_poi_detail
from app.adapters.poi.mock import search_poi as mock_search_poi
from app.adapters.poi.real import get_poi_detail as real_get_poi_detail
from app.adapters.poi.real import search_poi as real_search_poi

__all__ = [
    "mock_search_poi",
    "mock_get_poi_detail",
    "real_search_poi",
    "real_get_poi_detail",
]

