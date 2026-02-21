from __future__ import annotations

from app.application.graph.nodes.finalize import finalize_node


def _draft(summary: str) -> dict:
    return {
        "city": "贵阳",
        "days": [
            {
                "day_number": 1,
                "schedule": [
                    {
                        "poi": {"id": "p1", "name": "甲秀楼", "city": "贵阳"},
                        "is_backup": False,
                    }
                ],
            },
            {
                "day_number": 2,
                "schedule": [
                    {
                        "poi": {"id": "p2", "name": "黔灵山公园", "city": "贵阳"},
                        "is_backup": False,
                    }
                ],
            },
        ],
        "summary": summary,
    }


def test_finalize_rewrites_machine_summary() -> None:
    state = {
        "itinerary_draft": _draft(
            "贵阳 2d executable itinerary | day1:甲秀楼->黔灵山公园 ; day2:青岩古镇->花溪公园"
        ),
        "messages": [],
    }

    result = finalize_node(state)
    assert result["status"] == "done"
    summary = result["final_itinerary"]["summary"]
    assert "executable itinerary" not in summary.lower()
    assert "第1天" in summary
    assert "第2天" in summary
    assert "甲秀楼" in summary


def test_finalize_builds_human_summary_when_missing() -> None:
    state = {"itinerary_draft": _draft(""), "messages": []}

    result = finalize_node(state)
    assert result["status"] == "done"
    summary = result["final_itinerary"]["summary"]
    assert summary.startswith("贵阳2天行程亮点")
    assert "第1天" in summary
    assert "第2天" in summary


def test_finalize_rewrites_formula_summary_prefix() -> None:
    state = {
        "itinerary_draft": _draft("贵阳2天可执行行程：第1天：甲秀楼；第2天：黔灵山公园"),
        "messages": [],
    }

    result = finalize_node(state)
    assert result["status"] == "done"
    summary = result["final_itinerary"]["summary"]
    assert summary.startswith("贵阳2天行程亮点：")
    assert "可执行行程" not in summary
