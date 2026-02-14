"""Validate 节点 — 运行所有验证器"""

from __future__ import annotations

from typing import Any

from app.domain.models import Itinerary, TripConstraints
from app.validators import run_all_validators


def validate_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Validate 节点：对 itinerary_draft 运行所有验证器，
    将 issues 写入 state.validation_issues。
    """
    draft = state.get("itinerary_draft")
    if draft is None:
        return {"validation_issues": []}

    # 从 dict 还原 Pydantic
    if isinstance(draft, dict):
        itinerary = Itinerary.model_validate(draft)
    else:
        itinerary = draft

    constraints_raw = state.get("trip_constraints", {})
    if isinstance(constraints_raw, dict):
        constraints = TripConstraints.model_validate(constraints_raw)
    else:
        constraints = constraints_raw

    issues = run_all_validators(itinerary, constraints)

    return {
        "validation_issues": [i.model_dump(mode="json") for i in issues],
        # 回写更新后的 itinerary（budget 验证器会更新
        "itinerary_draft": itinerary.model_dump(mode="json"),
    }
