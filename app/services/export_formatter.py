"""Plan export renderers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.persistence.models import PlanExportRecord
from app.services.itinerary_presenter import present_itinerary


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _inline(value: Any) -> str:
    return _safe_text(value).replace("\n", " ").replace("\r", " ")


def _format_time_range(item: Mapping[str, Any]) -> str:
    start = _safe_text(item.get("start_time"))
    end = _safe_text(item.get("end_time"))
    if start and end:
        return f"{start}-{end}"
    if start:
        return f"{start}-?"
    if end:
        return f"?-{end}"
    slot = _safe_text(item.get("time_slot"))
    return slot or "time_tbd"


def _format_day(day: Mapping[str, Any]) -> list[str]:
    day_number = int(day.get("day_number", 0) or 0)
    day_title = f"## Day {day_number}" if day_number > 0 else "## Day"
    date_text = _safe_text(day.get("date"))
    if date_text:
        day_title = f"{day_title} ({date_text})"

    lines: list[str] = [day_title]
    schedule = day.get("schedule")
    if not isinstance(schedule, list) or not schedule:
        lines.append("- No schedule items")
        lines.append("")
        return lines

    for item in schedule:
        if not isinstance(item, Mapping):
            continue
        poi = item.get("poi")
        poi_name = ""
        if isinstance(poi, Mapping):
            poi_name = _inline(poi.get("name"))
        if not poi_name:
            poi_name = "Unnamed POI"
        travel_minutes = item.get("travel_minutes")
        try:
            travel = int(round(float(travel_minutes)))
        except (TypeError, ValueError):
            travel = 0

        time_range = _format_time_range(item)
        note = _inline(item.get("notes"))
        line = f"- {time_range} {poi_name} (travel {travel}m)"
        if note:
            line = f"{line} - {note}"
        lines.append(line)

    lines.append("")
    return lines


def render_plan_markdown(record: PlanExportRecord) -> str:
    itinerary = present_itinerary(record.itinerary, debug=False)
    city = ""
    day_count = 0
    if isinstance(itinerary, Mapping):
        city = _safe_text(itinerary.get("city"))
        days = itinerary.get("days")
        if isinstance(days, list):
            day_count = len(days)

    title = f"# Trip Plan Export - {city}" if city else "# Trip Plan Export"
    lines: list[str] = [
        title,
        "",
        f"- request_id: `{record.request_id}`",
        f"- session_id: `{record.session_id}`",
        f"- trace_id: `{record.trace_id}`",
        f"- status: `{record.status}`",
        f"- degrade_level: `{record.degrade_level}`",
        f"- created_at: `{record.created_at}`",
    ]

    if day_count > 0:
        lines.append(f"- days: `{day_count}`")
    if record.confidence_score is not None:
        lines.append(f"- confidence_score: `{record.confidence_score:.2f}`")

    summary = ""
    if isinstance(itinerary, Mapping):
        summary = _inline(itinerary.get("summary"))
    if summary:
        lines.extend(["", "## Summary", summary])
    else:
        message = _inline(record.message)
        if message:
            lines.extend(["", "## Message", message])

    if isinstance(itinerary, Mapping):
        days = itinerary.get("days")
        if isinstance(days, list) and days:
            lines.append("")
            lines.append("## Itinerary")
            lines.append("")
            for day in days:
                if not isinstance(day, Mapping):
                    continue
                lines.extend(_format_day(day))

        assumptions = itinerary.get("assumptions")
        if isinstance(assumptions, list):
            visible = [_inline(item) for item in assumptions if _inline(item)]
            if visible:
                lines.append("## Assumptions")
                for item in visible:
                    lines.append(f"- {item}")
                lines.append("")

    if record.issues:
        lines.append("## Issues")
        for issue in record.issues:
            item = _inline(issue)
            if item:
                lines.append(f"- {item}")
        lines.append("")

    if record.next_questions:
        lines.append("## Next Questions")
        for question in record.next_questions:
            item = _inline(question)
            if item:
                lines.append(f"- {item}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


__all__ = ["render_plan_markdown"]
