"""API 最小测试"""

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_plan_complete():
    """完整需求 → 应返回 done"""
    r = client.post("/plan", json={"message": "我想去北京玩3天，喜欢历史"})
    data = r.json()
    assert r.status_code == 200
    assert data["status"] in ("done", "clarifying")


def test_plan_missing_city():
    """缺参 → 应返回 clarifying 或 done（LLM 可能自动推断城市）"""
    r = client.post("/plan", json={"message": "帮我规划旅行"})
    data = r.json()
    assert r.status_code == 200
    assert data["status"] in ("clarifying", "done")
    assert len(data["message"]) > 5


def test_chat_multi_turn():
    """多轮对话"""
    # 第一轮：缺参
    r1 = client.post("/chat", json={"session_id": "test1", "message": "我想旅行"})
    d1 = r1.json()
    assert d1["status"] == "clarifying"

    # 第二轮：补充信息
    r2 = client.post("/chat", json={"session_id": "test1", "message": "去北京，3天"})
    d2 = r2.json()
    assert d2["status"] in ("done", "clarifying", "planning")
