"""Planner NLG 测试（离线模板模式）"""

from app.agent.planner_core import generate_itinerary
from app.agent.planner_nlg import enrich_itinerary
from app.domain.models import POI, Pace, TripConstraints, UserProfile


def _make_pois(n: int) -> list[POI]:
    return [
        POI(
            id=f"t{i}", name=f"景点{i}", city="北京",
            lat=39.9 + i * 0.01, lon=116.4 + i * 0.01,
            themes=["历史"], duration_hours=1.5, cost=20,
            description=f"景点{i}的描述",
        )
        for i in range(n)
    ]


def test_enrich_template_mode():
    """LLM 关闭时，模板生成 notes"""
    constraints = TripConstraints(city="北京", days=2, pace=Pace.MODERATE)
    profile = UserProfile(themes=["历史"])
    pois = _make_pois(10)
    itinerary = generate_itinerary(constraints, profile, pois)
    enriched = enrich_itinerary(itinerary)

    for day in enriched.days:
        for item in day.schedule:
            assert item.notes, f"景点 {item.poi.name} 的 notes 为空"
        assert day.day_summary

    assert enriched.summary
