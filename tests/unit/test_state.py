"""AgentState 序列化往返测试"""

from app.agent.state import AgentState
from app.domain.models import TripConstraints, UserProfile, Pace


def test_state_roundtrip():
    state = AgentState(
        messages=[{"role": "user", "content": "我想去北京玩三天"}],
        trip_constraints=TripConstraints(city="北京", days=3, pace=Pace.MODERATE),
        user_profile=UserProfile(themes=["文艺", "美食"]),
        requirements_missing=["budget_per_day"],
        repair_attempts=0,
        max_repair_attempts=3,
    )
    d = state.to_dict()
    restored = AgentState.from_dict(d)
    assert restored.trip_constraints.city == "北京"
    assert restored.trip_constraints.days == 3
    assert restored.user_profile.themes == ["文艺", "美食"]
    assert restored.requirements_missing == ["budget_per_day"]
    assert restored.to_dict() == d
