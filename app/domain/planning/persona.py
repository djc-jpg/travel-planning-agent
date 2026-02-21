"""Persona profile loading and lightweight scoring helpers."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.domain.models import POI, UserProfile

_PROFILE_FILE = Path(__file__).with_name("persona_profiles.json")
_DEFAULT = "default"
_TRAVELER_TO_PERSONA = {
    "elderly": "elderly",
    "family": "family",
    "friends": "young_friends",
    "couple": _DEFAULT,
    "solo": _DEFAULT,
}


@lru_cache(maxsize=1)
def _profiles() -> dict[str, dict]:
    with open(_PROFILE_FILE, encoding="utf-8") as fh:
        payload = json.load(fh)
    return {str(key): dict(value) for key, value in payload.items()}


def persona_name(profile: UserProfile) -> str:
    key = str(profile.travelers_type.value)
    return _TRAVELER_TO_PERSONA.get(key, _DEFAULT)


def persona_config(profile: UserProfile) -> dict:
    rows = _profiles()
    return dict(rows.get(persona_name(profile), rows[_DEFAULT]))


def persona_limits(profile: UserProfile) -> tuple[int, int]:
    cfg = persona_config(profile)
    return int(cfg.get("max_pois", 5)), int(cfg.get("max_daily_minutes", 600))


def persona_score(poi: POI, profile: UserProfile) -> float:
    cfg = persona_config(profile)
    themes = {str(item).lower() for item in poi.themes}
    text = f"{poi.name} {' '.join(poi.themes)}".lower()
    score = 0.0
    if cfg.get("rest_required"):
        if poi.indoor:
            score += 0.4
        if "park" in themes:
            score += 0.2
    walk_penalty = str(cfg.get("walk_penalty_weight", "medium"))
    if walk_penalty == "high" and poi.duration_hours >= 2.5:
        score -= 0.3
    if bool(cfg.get("night_bonus")) and any(token in text for token in ("night", "bar", "view", "夜")):
        score += 0.4
    return score


__all__ = ["persona_config", "persona_limits", "persona_name", "persona_score"]
