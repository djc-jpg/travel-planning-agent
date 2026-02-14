"""Repair 节点 — 基于 validation_issues 执行修复策略"""

from __future__ import annotations

from typing import Any

from app.domain.models import Itinerary, TripConstraints, ValidationIssue
from app.repair.strategies import REPAIR_DISPATCH


def repair_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Repair 节点：
    1. 根据 issues 调用对应修复策略
    2. repair_attempts += 1
    3. 若达到 max 则写 assumptions 准备降级
    """
    draft_raw = state.get("itinerary_draft")
    if draft_raw is None:
        return {}

    itinerary = Itinerary.model_validate(draft_raw) if isinstance(draft_raw, dict) else draft_raw
    constraints_raw = state.get("trip_constraints", {})
    constraints = TripConstraints.model_validate(constraints_raw) if isinstance(constraints_raw, dict) else constraints_raw

    issues_raw = state.get("validation_issues", [])
    issues = [
        ValidationIssue.model_validate(i) if isinstance(i, dict) else i
        for i in issues_raw
    ]

    repair_attempts = state.get("repair_attempts", 0) + 1
    max_attempts = state.get("max_repair_attempts", 3)

    if repair_attempts > max_attempts:
        # 降级：写 assumptions 不再修复
        itinerary.assumptions.append(
            f"经过 {max_attempts} 次修复仍有问题，以下 issues 已知但无法完全解决: "
            + "; ".join(i.message for i in issues)
        )
        return {
            "itinerary_draft": itinerary.model_dump(mode="json"),
            "repair_attempts": repair_attempts,
            "validation_issues": [],  # 清空让流程结束
        }

    # 执行修复
    for issue in issues:
        handler = REPAIR_DISPATCH.get(issue.code)
        if handler:
            itinerary = handler(itinerary, issue.day, constraints)

    return {
        "itinerary_draft": itinerary.model_dump(mode="json"),
        "repair_attempts": repair_attempts,
    }
