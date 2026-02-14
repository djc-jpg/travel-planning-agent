"""LangGraph 行程规划图编排"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from app.application.state import GraphState
from app.application.graph.nodes.clarify import clarify_node
from app.application.graph.nodes.fail_gracefully import fail_gracefully_node
from app.application.graph.nodes.finalize import finalize_node
from app.application.graph.nodes.intake import intake_node
from app.application.graph.nodes.repair import repair_node
from app.application.graph.nodes.retrieve import retrieve_node
from app.application.graph.nodes.validate import validate_node
from app.domain.models import Itinerary, POI, TripConstraints, UserProfile
from app.infrastructure.logging import get_logger
from app.nlg.generator import enrich_itinerary
from app.planner.core import generate_itinerary


# ── Wrapper 节点 ──────────────────────────────────────

def planner_core_node(state: dict[str, Any]) -> dict[str, Any]:
    """Planner Core 节点：生成行程草案"""
    logger = get_logger()
    logger.node_start("planner_core")
    try:
        constraints_raw = state.get("trip_constraints", {})
        constraints = TripConstraints.model_validate(constraints_raw) if isinstance(constraints_raw, dict) else constraints_raw

        profile_raw = state.get("user_profile", {})
        profile = UserProfile.model_validate(profile_raw) if isinstance(profile_raw, dict) else profile_raw

        candidates_raw = state.get("attraction_candidates", [])
        candidates = [
            POI.model_validate(p) if isinstance(p, dict) else p
            for p in candidates_raw
        ]

        if not candidates:
            return {
                "status": "error",
                "error_message": "没有候选景点可用于规划",
                "error_code": "NO_CANDIDATES",
            }

        itinerary = generate_itinerary(
            constraints, profile, candidates,
            weather_data=state.get("weather_data"),
            calendar_data=state.get("calendar_data"),
        )
        logger.node_end("planner_core", candidates_count=len(candidates))
        return {
            "itinerary_draft": itinerary.model_dump(mode="json"),
        }
    except Exception as e:
        logger.error("planner_core", str(e))
        return {
            "status": "error",
            "error_message": str(e),
            "error_code": "PLANNER_ERROR",
        }


def planner_nlg_node(state: dict[str, Any]) -> dict[str, Any]:
    """Planner NLG 节点：为行程补充文案"""
    logger = get_logger()
    try:
        draft_raw = state.get("itinerary_draft")
        if draft_raw is None:
            return {}
        itinerary = Itinerary.model_validate(draft_raw) if isinstance(draft_raw, dict) else draft_raw
        enriched = enrich_itinerary(itinerary)
        return {
            "itinerary_draft": enriched.model_dump(mode="json"),
        }
    except Exception as e:
        logger.warning("planner_nlg", f"NLG 失败，保留原硬行程: {e}")
        return {}  # NLG 失败不阻塞流程


# ── 路由函数 ──────────────────────────────────────────

def route_after_intake(state: dict[str, Any]) -> str:
    if state.get("status") == "error":
        return "fail_gracefully"
    missing = state.get("requirements_missing", [])
    if missing:
        return "clarify"
    return "retrieve"


def route_after_retrieve(state: dict[str, Any]) -> str:
    candidates = state.get("attraction_candidates", [])
    if not candidates:
        return "fail_gracefully"
    return "planner_core"


def route_after_planner_core(state: dict[str, Any]) -> str:
    if state.get("status") == "error":
        return "fail_gracefully"
    return "planner_nlg"


def route_after_validate(state: dict[str, Any]) -> str:
    issues = state.get("validation_issues", [])
    # 只关注 high severity
    high_issues = []
    for i in issues:
        sev = i.get("severity") if isinstance(i, dict) else getattr(i, "severity", "low")
        if sev == "high":
            high_issues.append(i)

    if not high_issues:
        return "finalize"

    attempts = state.get("repair_attempts", 0)
    max_att = state.get("max_repair_attempts", 3)
    if attempts >= max_att:
        return "finalize"  # 降级输出

    return "repair"


# ── 构建 Graph ────────────────────────────────────────

def build_graph() -> StateGraph:
    """构建并编译 LangGraph StateGraph"""
    # 使用 TypedDict 作为 state schema 确保正确合并
    graph = StateGraph(GraphState)

    # 添加节点
    graph.add_node("intake", intake_node)
    graph.add_node("clarify", clarify_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("planner_core", planner_core_node)
    graph.add_node("planner_nlg", planner_nlg_node)
    graph.add_node("validate", validate_node)
    graph.add_node("repair", repair_node)
    graph.add_node("finalize", finalize_node)
    graph.add_node("fail_gracefully", fail_gracefully_node)

    # 入口
    graph.set_entry_point("intake")

    # 条件路由
    graph.add_conditional_edges("intake", route_after_intake, {
        "clarify": "clarify",
        "retrieve": "retrieve",
        "fail_gracefully": "fail_gracefully",
    })

    graph.add_edge("clarify", END)  # clarify 后停下等用户补充

    graph.add_conditional_edges("retrieve", route_after_retrieve, {
        "planner_core": "planner_core",
        "fail_gracefully": "fail_gracefully",
    })

    graph.add_conditional_edges("planner_core", route_after_planner_core, {
        "planner_nlg": "planner_nlg",
        "fail_gracefully": "fail_gracefully",
    })

    graph.add_edge("planner_nlg", "validate")

    graph.add_conditional_edges("validate", route_after_validate, {
        "finalize": "finalize",
        "repair": "repair",
    })

    graph.add_edge("repair", "validate")  # 修复后重新验证

    graph.add_edge("finalize", END)
    graph.add_edge("fail_gracefully", END)

    return graph


def compile_graph():
    """编译并返回可运行的 graph app"""
    graph = build_graph()
    return graph.compile()
