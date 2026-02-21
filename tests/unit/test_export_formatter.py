from app.persistence.models import PlanExportRecord
from app.services.export_formatter import render_plan_markdown


def test_render_plan_markdown_contains_core_sections():
    record = PlanExportRecord(
        request_id="req_1",
        session_id="chat_1",
        trace_id="trace_1",
        message="beijing 2 day trip",
        constraints={"city": "beijing", "days": 2},
        user_profile={"themes": ["history"]},
        metadata={},
        status="done",
        degrade_level="L1",
        confidence_score=0.86,
        run_fingerprint={"run_mode": "DEGRADED"},
        itinerary={
            "city": "beijing",
            "summary": "2-day executable plan",
            "days": [
                {
                    "day_number": 1,
                    "date": "2026-03-01",
                    "schedule": [
                        {
                            "start_time": "09:00",
                            "end_time": "11:00",
                            "travel_minutes": 15,
                            "notes": "book in advance",
                            "poi": {"name": "Forbidden City"},
                        }
                    ],
                }
            ],
            "assumptions": ["ticket needs reservation"],
        },
        issues=[],
        next_questions=[],
        field_evidence={},
        metrics={},
        created_at="2026-02-21T01:00:00Z",
        artifacts=[],
    )

    markdown = render_plan_markdown(record)

    assert markdown.startswith("# Trip Plan Export")
    assert "## Summary" in markdown
    assert "## Itinerary" in markdown
    assert "## Day 1 (2026-03-01)" in markdown
    assert "Forbidden City" in markdown
    assert "## Assumptions" in markdown
