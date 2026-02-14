"""Factory for creating initial graph state."""

from __future__ import annotations

from app.application.state import GraphState


def make_initial_state() -> GraphState:
    return {
        "messages": [],
        "trip_constraints": {},
        "user_profile": {},
        "requirements_missing": [],
        "attraction_candidates": [],
        "itinerary_draft": None,
        "validation_issues": [],
        "final_itinerary": None,
        "repair_attempts": 0,
        "max_repair_attempts": 3,
        "status": "init",
        "metrics": {},
    }


__all__ = ["make_initial_state"]
