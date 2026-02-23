"""Tests for fact trust classification."""

from __future__ import annotations

from app.trust.facts.fact_classification import classify_field, compute_verified_fact_ratio


def test_classify_field_missing_value_is_unknown():
    result = classify_field(None, {"source_type": "verified"})
    assert result["source_type"] == "unknown"
    assert result["field_confidence"] == 0.0


def test_classify_field_placeholder_text_is_unknown():
    placeholder = "\u4ee5\u516c\u544a\u4e3a\u51c6"
    result = classify_field(placeholder, {"source_type": "verified"})
    assert result["source_type"] == "unknown"
    assert result["field_confidence"] == 0.0


def test_classify_field_without_fact_sources_is_unknown():
    result = classify_field("09:00-17:00", {})
    assert result["source_type"] == "unknown"
    assert result["field_confidence"] == 0.0


def test_classify_field_fallback_is_explicit():
    result = classify_field(
        "09:00-17:00",
        {"source_type": "data", "tool_status": "fallback"},
    )
    assert result["source_type"] == "fallback"
    assert result["field_confidence"] == 0.25


def test_compute_verified_fact_ratio_counts_only_verified_and_curated():
    itinerary = {
        "days": [
            {
                "schedule": [
                    {
                        "poi": {
                            "ticket_price": 100.0,
                            "reservation_required": True,
                            "open_hours": "09:00-18:00",
                            "closed_rules": "none",
                            "fact_sources": {
                                "ticket_price_source_type": "verified",
                                "reservation_required_source_type": "curated",
                                "open_hours_source_type": "heuristic",
                                "closed_rules_source_type": "unknown",
                            },
                        },
                    },
                    {
                        "poi": {
                            "ticket_price": 0.0,
                            "reservation_required": False,
                            "open_hours": "\u4ee5\u516c\u544a\u4e3a\u51c6",
                            "closed_rules": "",
                            "fact_sources": {
                                "ticket_price": "data",
                                "reservation_required": "data",
                                "open_hours": "data",
                                "closed_rules": "data",
                            },
                        },
                    },
                ]
            }
        ]
    }

    # Missing closed_rules from curated source is treated as "no explicit closure rule".
    assert compute_verified_fact_ratio(itinerary) == 0.625


def test_classify_field_allows_missing_closed_rules_from_curated_source():
    result = classify_field(
        "",
        {
            "source_type": "data",
            "has_fact_sources": True,
            "field_name": "closed_rules",
        },
    )
    assert result["source_type"] == "curated"
    assert result["field_confidence"] > 0.0
