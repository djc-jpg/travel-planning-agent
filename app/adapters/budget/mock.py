"""Mock budget estimator."""

from __future__ import annotations

from app.tools.interfaces import BudgetInput, BudgetResult

TRANSPORT_COST = {
    "walking": 0.0,
    "public_transit": 5.0,
    "taxi": 30.0,
    "driving": 20.0,
}


def estimate_cost(params: BudgetInput) -> BudgetResult:
    poi_total = sum(params.poi_costs)
    transport_total = TRANSPORT_COST.get(params.transport_mode, 10.0) * params.transport_segments
    total = poi_total + transport_total
    return BudgetResult(
        total_cost=round(total, 2),
        breakdown={"poi_tickets": poi_total, "transport": transport_total},
    )

