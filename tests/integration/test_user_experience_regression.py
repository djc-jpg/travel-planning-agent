"""User-facing quality regression tests."""

from __future__ import annotations

from app.application.context import make_app_context
from app.services.plan_service import execute_plan


def _run_plan(*, city: str, days: int, date_start: str, date_end: str, themes: list[str]):
    ctx = make_app_context()
    return execute_plan(
        ctx=ctx,
        message=f"{city}{days}天旅行规划",
        constraints={
            "city": city,
            "days": days,
            "date_start": date_start,
            "date_end": date_end,
            "budget_per_day": 500,
        },
        user_profile={
            "themes": themes,
            "travelers_type": "couple",
        },
        metadata={
            "source": "integration_regression",
            "field_sources": {
                "city": "user_form",
                "days": "user_form",
                "date_start": "user_form",
                "date_end": "user_form",
            },
        },
        debug=False,
    )


def test_date_start_slash_format_is_reflected_in_output_dates(monkeypatch):
    monkeypatch.setenv("ENGINE_VERSION", "v2")
    monkeypatch.setenv("STRICT_REQUIRED_FIELDS", "false")

    result = _run_plan(
        city="北京",
        days=2,
        date_start="2026/03/12",
        date_end="2026/03/16",
        themes=["历史古迹"],
    )

    assert result.status.value == "done"
    assert result.itinerary is not None
    rows = result.itinerary.get("days", [])
    assert rows[0].get("date") == "2026-03-12"
    assert rows[1].get("date") == "2026-03-13"


def test_food_night_preference_hits_at_least_one_food_or_night_stop(monkeypatch):
    monkeypatch.setenv("ENGINE_VERSION", "v2")
    monkeypatch.setenv("STRICT_REQUIRED_FIELDS", "false")

    result = _run_plan(
        city="成都",
        days=3,
        date_start="2026-03-12",
        date_end="2026-03-16",
        themes=["美食夜市"],
    )

    assert result.status.value == "done"
    assert result.itinerary is not None
    rows = result.itinerary.get("days", [])
    assert rows

    keywords = ("美食", "夜", "night", "food", "餐")
    hit = False
    for day in rows:
        for item in day.get("schedule", []):
            if item.get("is_backup"):
                continue
            poi = item.get("poi", {})
            text = " ".join(
                [
                    str(poi.get("name", "")),
                    " ".join(str(theme) for theme in poi.get("themes", []) if str(theme)),
                    str(poi.get("description", "")),
                ]
            ).lower()
            if any(token.lower() in text for token in keywords):
                hit = True
                break
        if hit:
            break

    assert hit
