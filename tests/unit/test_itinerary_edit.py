"""Unit tests for diff-based itinerary edit helpers."""

from __future__ import annotations

from app.application.contracts import TripRequest
from app.application.itinerary_edit import (
    apply_edit_patch_to_request,
    build_edit_patch,
    merge_itinerary_by_patch,
)


def _itinerary(day1: str, day2: str) -> dict:
    return {
        "city": "北京",
        "days": [
            {
                "day_number": 1,
                "schedule": [{"is_backup": False, "poi": {"name": day1}}],
                "meal_windows": ["12:00-13:00"],
            },
            {
                "day_number": 2,
                "schedule": [{"is_backup": False, "poi": {"name": day2}}],
                "meal_windows": ["12:00-13:00"],
            },
        ],
        "assumptions": [],
        "summary": "",
    }


def test_build_edit_patch_from_message():
    patch = build_edit_patch(
        message="把第2天故宫换成颐和园，安排午休",
        metadata={},
        previous_itinerary=None,
    )
    assert patch is not None
    assert patch.replace_stop is not None
    assert patch.replace_stop.day_number == 2
    assert patch.replace_stop.new_poi == "颐和园"
    assert patch.lunch_break is not None


def test_build_edit_patch_add_and_remove_from_message():
    add_patch = build_edit_patch(
        message="请在第1天添加景山公园",
        metadata={},
        previous_itinerary=None,
    )
    assert add_patch is not None
    assert add_patch.add_stop is not None
    assert add_patch.add_stop.day_number == 1
    assert add_patch.add_stop.poi == "景山公园"

    remove_patch = build_edit_patch(
        message="第2天删除故宫",
        metadata={},
        previous_itinerary=None,
    )
    assert remove_patch is not None
    assert remove_patch.remove_stop is not None
    assert remove_patch.remove_stop.day_number == 2
    assert remove_patch.remove_stop.poi == "故宫"


def test_apply_edit_patch_to_request_injects_constraints():
    patch = build_edit_patch(
        message="把第2天故宫换成颐和园",
        metadata={},
        previous_itinerary=None,
    )
    assert patch is not None
    req = TripRequest(message="edit", constraints={"city": "北京", "days": 2})
    updated = apply_edit_patch_to_request(req, patch)

    assert "颐和园" in updated.constraints["must_visit"]
    assert "故宫" in updated.constraints["avoid"]
    assert updated.metadata["edit_mode"] == "diff"
    assert "edit_patch" in updated.metadata


def test_merge_itinerary_patch_keeps_non_target_days():
    previous = _itinerary("天安门", "故宫")
    current = _itinerary("新一天", "颐和园")
    patch = build_edit_patch(
        message="把第2天故宫换成颐和园",
        metadata={},
        previous_itinerary=previous,
    )
    merged = merge_itinerary_by_patch(
        current_itinerary=current,
        previous_itinerary=previous,
        patch=patch,
    )
    assert merged is not None
    day1_name = merged["days"][0]["schedule"][0]["poi"]["name"]
    day2_name = merged["days"][1]["schedule"][0]["poi"]["name"]
    assert day1_name == "天安门"
    assert day2_name == "颐和园"
    assert any("edit_patch:replace_stop day=2" in row for row in merged["assumptions"])


def test_merge_itinerary_patch_adds_lunch_break():
    previous = _itinerary("天安门", "故宫")
    current = _itinerary("天安门", "故宫")
    patch = build_edit_patch(
        message="第1天请安排午休",
        metadata={},
        previous_itinerary=previous,
    )
    merged = merge_itinerary_by_patch(
        current_itinerary=current,
        previous_itinerary=previous,
        patch=patch,
    )
    assert merged is not None
    windows = merged["days"][0]["meal_windows"]
    assert "12:00-13:00" in windows
    assert any("edit_patch:lunch_break" in row for row in merged["assumptions"])


def test_apply_edit_patch_supports_add_remove_and_adjust_time():
    patch = build_edit_patch(
        message="ignored",
        metadata={
            "edit_patch": {
                "add_stop": {"day_number": 1, "poi": "景山公园"},
                "remove_stop": {"day_number": 2, "poi": "故宫"},
                "adjust_time": {"day_number": 1, "poi": "天安门", "window": "14:00-16:00"},
            }
        },
        previous_itinerary=None,
    )
    assert patch is not None
    req = TripRequest(message="edit", constraints={"city": "北京", "days": 2})
    updated = apply_edit_patch_to_request(req, patch)

    assert "景山公园" in updated.constraints["must_visit"]
    assert "故宫" in updated.constraints["avoid"]
    assert updated.constraints["poi_time_preferences"] == [
        {"day_number": 1, "window": "14:00-16:00", "poi": "天安门"}
    ]


def test_merge_itinerary_patch_remove_stop():
    previous = _itinerary("天安门", "故宫")
    current = _itinerary("天安门", "故宫")
    patch = build_edit_patch(
        message="ignored",
        metadata={"edit_patch": {"remove_stop": {"day_number": 2, "poi": "故宫"}}},
        previous_itinerary=previous,
    )
    merged = merge_itinerary_by_patch(
        current_itinerary=current,
        previous_itinerary=previous,
        patch=patch,
    )
    assert merged is not None
    assert merged["days"][1]["schedule"] == []
    assert any("edit_patch:remove_stop day=2" in row for row in merged["assumptions"])


def test_merge_itinerary_patch_adjust_time():
    previous = _itinerary("天安门", "故宫")
    current = _itinerary("天安门", "故宫")
    patch = build_edit_patch(
        message="ignored",
        metadata={"edit_patch": {"adjust_time": {"day_number": 1, "poi": "天安门", "window": "14:00-16:00"}}},
        previous_itinerary=previous,
    )
    merged = merge_itinerary_by_patch(
        current_itinerary=current,
        previous_itinerary=previous,
        patch=patch,
    )
    assert merged is not None
    item = merged["days"][0]["schedule"][0]
    assert item["start_time"] == "14:00"
    assert item["end_time"] == "16:00"
    assert any("edit_patch:adjust_time day=1" in row for row in merged["assumptions"])
