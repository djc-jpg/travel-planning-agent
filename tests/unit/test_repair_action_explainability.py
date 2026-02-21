from app.planner.core import _repair_action_to_user_note


def test_repair_action_to_user_note_for_budget_trim():
    note = _repair_action_to_user_note("day2:remove_poi:景点A:budget_trim")
    assert note == "预算优化：第2天移除了「景点A」，以尽量满足预算上限。"


def test_repair_action_to_user_note_ignores_non_budget_actions():
    assert _repair_action_to_user_note("day1:reorder_day") is None
    assert _repair_action_to_user_note("day1:remove_poi:景点A") is None
