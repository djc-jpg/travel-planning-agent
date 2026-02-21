"""Trust confidence scoring tests."""

from __future__ import annotations

from app.trust.confidence import compute_confidence, infer_fallback_count, infer_routing_source


def test_confidence_cap_when_verified_ratio_below_half():
    result = compute_confidence(
        {
            "verified_fact_ratio": 0.49,
            "routing_source": "real",
            "fallback_count": 0,
            "repair_count": 0,
            "constraint_satisfaction": 1.0,
        }
    )

    assert result["confidence_score"] <= 0.6
    assert result["confidence_breakdown"]["caps"]["applied_cap"] <= 0.6


def test_confidence_cap_when_routing_is_fixture():
    result = compute_confidence(
        {
            "verified_fact_ratio": 1.0,
            "routing_source": "fixture",
            "fallback_count": 0,
            "repair_count": 0,
            "constraint_satisfaction": 1.0,
        }
    )

    assert result["confidence_score"] <= 0.7
    assert result["confidence_breakdown"]["caps"]["applied_cap"] <= 0.7


def test_confidence_penalizes_fallback_and_repair():
    base = compute_confidence(
        {
            "verified_fact_ratio": 1.0,
            "routing_source": "real",
            "fallback_count": 0,
            "repair_count": 0,
            "constraint_satisfaction": 1.0,
        }
    )
    penalized = compute_confidence(
        {
            "verified_fact_ratio": 1.0,
            "routing_source": "real",
            "fallback_count": 2,
            "repair_count": 3,
            "constraint_satisfaction": 1.0,
        }
    )

    assert penalized["confidence_score"] < base["confidence_score"]
    penalties = penalized["confidence_breakdown"]["penalties"]
    assert penalties["fallback_penalty"] > 0.0
    assert penalties["repair_penalty"] > 0.0


def test_infer_fallback_from_low_routing_confidence_notes():
    itinerary = {
        "days": [
            {
                "schedule": [
                    {
                        "is_backup": False,
                        "notes": "cluster=c1 | routing_confidence=0.40 | buffer=20m",
                    }
                ]
            }
        ]
    }

    source = infer_routing_source(itinerary, default_source="real")
    fallback_count = infer_fallback_count(itinerary, routing_source=source)

    assert source == "fallback_fixture"
    assert fallback_count == 1
