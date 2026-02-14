"""预算验证器：检查总费用是否超预算（只读，不修改 itinerary）"""

from __future__ import annotations

from app.domain.models import Itinerary, Severity, TripConstraints, ValidationIssue


def validate_budget(
    itinerary: Itinerary,
    constraints: TripConstraints,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    # 先确定预算上限
    if constraints.total_budget:
        budget_limit = constraints.total_budget
    elif constraints.budget_per_day:
        budget_limit = constraints.budget_per_day * constraints.days
    else:
        return issues  # 没有预算约束

    # 使用 planner_core 已计算好的费用（只读）
    total = itinerary.total_cost

    if total > budget_limit:
        issues.append(
            ValidationIssue(
                code="OVER_BUDGET",
                severity=Severity.HIGH,
                message=f"总费用 {total:.0f}元 超过预算 {budget_limit:.0f}元",
                suggestions=[
                    "选择免费景点替换收费景点",
                    "减少高消费景点",
                    "增加预算",
                ],
            )
        )
    return issues
