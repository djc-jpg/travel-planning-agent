"""Merge user update node tests."""

import app.application.graph.nodes.merge_user_update as merge_module

from app.application.graph.nodes.merge_user_update import merge_user_update_node


def test_merge_user_update_text_evidence_overrides_llm_hallucination(monkeypatch):
    """Explicit user update should win over hallucinated LLM fields."""

    def _fake_llm_extract(_: str) -> dict:
        return {
            "city": "三亚",
            "days": 6,
            "themes": ["购物"],
            "travelers_type": "friends",
        }

    monkeypatch.setattr(merge_module, "_llm_extract", _fake_llm_extract)

    state = {
        "messages": [{"role": "user", "content": "改成北京3天，亲子历史路线，预算每天1200元"}],
        "trip_constraints": {"city": "杭州", "days": 4},
        "user_profile": {"themes": ["自然"]},
    }

    result = merge_user_update_node(state)

    assert result["status"] == "planning"
    assert result["trip_constraints"]["city"] == "北京"
    assert result["trip_constraints"]["days"] == 3
    assert result["trip_constraints"]["budget_per_day"] == 1200.0
    assert "历史" in result["user_profile"]["themes"]
    assert "亲子" in result["user_profile"]["themes"]
