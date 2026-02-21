"""Evaluate Beijing 4-day Spring Festival itinerary quality."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.application.graph.workflow import compile_graph
from app.application.state_factory import make_initial_state
from app.domain.models import Itinerary

_INPUT = (
    "请做一个北京4日春节行程：2位成人，历史文化为主，"
    "住东城区，公共交通，希望可执行且少折返。"
)
_REPORT_PATH = Path("app/eval/reports/eval_report.md")


def _build_itinerary() -> Itinerary:
    state = make_initial_state()
    state["messages"] = [{"role": "user", "content": _INPUT}]
    result = compile_graph().invoke(state)
    if result.get("status") != "done":
        raise RuntimeError(f"unexpected status={result.get('status')}")
    return Itinerary.model_validate(result["final_itinerary"])


def _cluster_switches(itinerary: Itinerary) -> int:
    switches = 0
    for day in itinerary.days:
        clusters = [item.poi.cluster for item in day.schedule if not item.is_backup]
        for idx in range(1, len(clusters)):
            if clusters[idx] != clusters[idx - 1]:
                switches += 1
    return switches


def _calc_metrics(itinerary: Itinerary) -> dict[str, tuple[bool, str]]:
    main_items = [
        item
        for day in itinerary.days
        for item in day.schedule
        if not item.is_backup
    ]
    non_first_segments = []
    for day in itinerary.days:
        main = [item for item in day.schedule if not item.is_backup]
        non_first_segments.extend(main[1:])

    budget_ok = itinerary.total_cost >= 400 and all(
        key in itinerary.budget_breakdown for key in ("tickets", "local_transport", "food_min")
    )
    travel_ok = bool(non_first_segments) and all(0 < item.travel_minutes < 180 for item in non_first_segments)
    facts_ok = all(item.poi.metadata_source == "poi_beijing" for item in main_items)
    buffer_ok = all(item.buffer_minutes >= 30 for item in main_items) and all(day.meal_windows for day in itinerary.days)
    reservation_ok = all(
        ("预约" in item.notes) if item.poi.requires_reservation else True
        for item in main_items
    )
    switches = _cluster_switches(itinerary)
    route_ok = switches <= max(2, len(itinerary.days))
    ids = [item.poi.id for item in main_items]
    dedup_ok = len(ids) == len(set(ids))

    return {
        "budget_realism": (budget_ok, f"total_cost={itinerary.total_cost:.0f}"),
        "travel_feasibility": (travel_ok, f"segments={len(non_first_segments)}"),
        "ticket_fact_coverage": (facts_ok, f"items={len(main_items)}"),
        "cny_buffering": (buffer_ok, f"days={len(itinerary.days)}"),
        "reservation_reminder": (reservation_ok, "requires_reservation covered"),
        "route_compactness": (route_ok, f"cluster_switches={switches}"),
        "no_duplicate_poi": (dedup_ok, f"unique={len(set(ids))}/{len(ids)}"),
    }


def _render_report(itinerary: Itinerary, metrics: dict[str, tuple[bool, str]]) -> str:
    passed = sum(1 for ok, _ in metrics.values() if ok)
    total = len(metrics)
    ratio = passed / total if total else 0.0

    lines: list[str] = []
    lines.append("# Beijing 4-Day CNY Eval Report")
    lines.append("")
    lines.append(f"- Generated at: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"- Input: {_INPUT}")
    lines.append(f"- Constraint pass rate: {passed}/{total} ({ratio:.0%})")
    lines.append("")
    lines.append("## Metrics")
    lines.append("")
    lines.append("| Metric | Pass | Evidence |")
    lines.append("| --- | --- | --- |")
    for name, (ok, detail) in metrics.items():
        lines.append(f"| {name} | {'YES' if ok else 'NO'} | {detail} |")

    lines.append("")
    lines.append("## Budget Breakdown")
    lines.append("")
    lines.append(f"- total_cost: {itinerary.total_cost:.0f}")
    for key, value in itinerary.budget_breakdown.items():
        lines.append(f"- {key}: {value:.0f}")
    if itinerary.budget_warning:
        lines.append(f"- budget_warning: {itinerary.budget_warning}")

    lines.append("")
    lines.append("## Itinerary")
    lines.append("")
    for day in itinerary.days:
        lines.append(f"### Day {day.day_number} ({day.date})")
        lines.append(f"- meal_windows: {', '.join(day.meal_windows)}")
        lines.append(f"- total_travel_minutes: {day.total_travel_minutes}")
        lines.append(f"- estimated_cost: {day.estimated_cost}")
        for item in day.schedule:
            if item.is_backup:
                continue
            lines.append(
                f"  - {item.start_time}-{item.end_time} {item.poi.name} "
                f"(travel={item.travel_minutes}m, buffer={item.buffer_minutes}m, ticket={item.poi.ticket_price})"
            )
        if day.backups:
            lines.append(f"- backup: {day.backups[0].poi.name}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(itinerary.summary)
    return "\n".join(lines) + "\n"


def run() -> Path:
    itinerary = _build_itinerary()
    metrics = _calc_metrics(itinerary)
    markdown = _render_report(itinerary, metrics)
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REPORT_PATH.write_text(markdown, encoding="utf-8")
    print(f"saved: {_REPORT_PATH}")
    for name, (ok, detail) in metrics.items():
        print(f"{name}: {'PASS' if ok else 'FAIL'} ({detail})")
    return _REPORT_PATH


if __name__ == "__main__":
    run()
