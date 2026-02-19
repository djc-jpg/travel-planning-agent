"""Intake/Clarify 测试"""

import app.application.graph.nodes.intake as intake_module
from app.agent.nodes.intake import intake_node
from app.agent.nodes.clarify import clarify_node


def test_intake_missing_city():
    """缺少 city 应进入 clarifying"""
    state = {
        "messages": [{"role": "user", "content": "我想玩三天"}],
        "trip_constraints": {},
        "user_profile": {},
    }
    result = intake_node(state)
    assert "city" in result["requirements_missing"]
    assert result["status"] == "clarifying"


def test_intake_complete():
    """完整输入应进入 planning"""
    state = {
        "messages": [{"role": "user", "content": "我想去北京玩3天，预算每天500元，轻松节奏，喜欢历史和美食"}],
        "trip_constraints": {},
        "user_profile": {},
    }
    result = intake_node(state)
    assert result["requirements_missing"] == []
    assert result["status"] == "planning"
    assert result["trip_constraints"]["city"] == "北京"
    assert result["trip_constraints"]["days"] == 3
    assert "历史" in result["user_profile"]["themes"]


def test_clarify_generates_question():
    """有缺参时 clarify 应生成追问"""
    state = {
        "messages": [{"role": "user", "content": "帮我规划行程"}],
        "requirements_missing": ["city", "days"],
    }
    result = clarify_node(state)
    assert result["status"] == "clarifying"
    last_msg = result["messages"][-1]
    # LLM 模式可能生成不同措辞，只需确认有追问内容
    content = last_msg["content"]
    assert len(content) > 5, "clarify 应生成有意义的追问"


def test_intake_text_evidence_overrides_llm_hallucination(monkeypatch):
    """用户文本明确给出城市/天数时，应优先于 LLM 漂移结果。"""

    def _fake_llm_extract(_: str) -> dict:
        return {
            "city": "杭州",
            "days": 4,
            "themes": ["购物"],
            "travelers_type": "family",
        }

    monkeypatch.setattr(intake_module, "_llm_extract", _fake_llm_extract)

    state = {
        "messages": [{"role": "user", "content": "我想去北京玩3天，预算每天500元，喜欢历史和亲子"}],
        "trip_constraints": {},
        "user_profile": {},
    }
    result = intake_node(state)

    assert result["status"] == "planning"
    assert result["trip_constraints"]["city"] == "北京"
    assert result["trip_constraints"]["days"] == 3
    assert "历史" in result["user_profile"]["themes"]
    assert "亲子" in result["user_profile"]["themes"]
