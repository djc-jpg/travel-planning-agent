"""Planner Core 测试"""

from app.agent.planner_core import generate_itinerary
from app.domain.models import Pace, POI, TripConstraints, UserProfile


def _make_pois(n: int, city: str = "北京") -> list[POI]:
    return [
        POI(
            id=f"t{i}",
            name=f"景点{i}",
            city=city,
            lat=39.9 + i * 0.01,
            lon=116.4 + i * 0.01,
            themes=["历史"] if i % 2 == 0 else ["美食"],
            duration_hours=1.5,
            cost=20,
        )
        for i in range(n)
    ]


def test_generate_basic():
    constraints = TripConstraints(city="北京", days=3, pace=Pace.MODERATE)
    profile = UserProfile(themes=["历史"])
    pois = _make_pois(15)
    itinerary = generate_itinerary(constraints, profile, pois)

    assert len(itinerary.days) == 3
    for day in itinerary.days:
        # moderate pace: 最多 3 个主景点
        main_count = sum(1 for s in day.schedule if not s.is_backup)
        assert main_count <= 3
        # 每天至少有备选
        assert len(day.backups) >= 1 or any(s.is_backup for s in day.schedule)


def test_relaxed_pace():
    constraints = TripConstraints(city="北京", days=2, pace=Pace.RELAXED)
    profile = UserProfile()
    pois = _make_pois(10)
    itinerary = generate_itinerary(constraints, profile, pois)

    assert len(itinerary.days) == 2
    for day in itinerary.days:
        main_count = sum(1 for s in day.schedule if not s.is_backup)
        assert main_count <= 2


def test_itinerary_serializable():
    """输出能通过 Pydantic 校验"""
    constraints = TripConstraints(city="上海", days=2, pace=Pace.INTENSIVE)
    profile = UserProfile(themes=["亲子"])
    pois = _make_pois(15, city="上海")
    itinerary = generate_itinerary(constraints, profile, pois)
    # Pydantic 序列化不报错
    data = itinerary.model_dump(mode="json")
    assert "days" in data
    assert len(data["days"]) == 2
