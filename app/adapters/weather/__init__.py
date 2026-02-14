"""Weather adapters."""

from app.adapters.weather.mock import get_weather as mock_get_weather
from app.adapters.weather.real import get_weather as real_get_weather

__all__ = ["mock_get_weather", "real_get_weather"]

