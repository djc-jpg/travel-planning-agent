"""Postprocess and orchestration for deterministic itinerary generation."""

from __future__ import annotations

from datetime import date, timedelta

from app.domain.models import Itinerary, ItineraryDay, POI, ScheduleItem, TimeSlot, TripConstraints, UserProfile
from app.domain.planning.cluster import build_cluster_map, enforce_day_cluster_cap
from app.domain.planning.day_template import DayTemplate, rebalance_day_pois, resolve_day_template
from app.domain.planning.fact_confidence import annotate_pois_fact_confidence
from app.domain.planning.ordering import optimize_daily_order
from app.domain.planning.persona import persona_limits, persona_name
from app.domain.planning.scheduling import DistanceFn, TravelTimeFn, assign_time_slots, pick_backup
from app.domain.planning.selection import cluster_day_plan, is_open_on_date, prepare_candidate_pool, top_up_day_pois
from app.planner.budget import apply_realistic_budget
from app.planner.distance import estimate_distance, estimate_travel_time
from app.planner.routing_provider import RoutingProvider, build_routing_provider


def _build_day_summary(*, weather_info: dict, holiday_name: str, crowd_level: str) -> str:
    parts: list[str] = []
    if holiday_name:
        parts.append(f"节假日:{holiday_name}")
    if crowd_level in {"high", "very_high"}:
        parts.append("人流量较高，已增加缓冲")
    if weather_info.get("condition"):
        parts.append(f"天气:{weather_info['condition']}")
    return " | ".join(parts)


def _fallback_schedule(pois: list[POI], crowd_level: str) -> list[ScheduleItem]:
    if not pois:
        return []
    return [ScheduleItem(poi=pois[0], time_slot=TimeSlot.MORNING, start_time="10:00", end_time="11:30", travel_minutes=0.0, buffer_minutes=20.0, notes=f"fallback_schedule crowd={crowd_level}")]


def _apply_budget_and_summary(
    *,
    constraints: TripConstraints,
    profile: UserProfile,
    city: str,
    days_output: list[ItineraryDay],
    assumptions: list[str],
) -> Itinerary:
    itinerary = Itinerary(city=city, days=days_output, assumptions=list(assumptions))
    apply_realistic_budget(itinerary, constraints, profile)
    routing_confidence = _average_routing_confidence(itinerary)
    itinerary.budget_breakdown["routing_confidence"] = round(routing_confidence, 2)
    itinerary.assumptions.append(f"routing_confidence={routing_confidence:.2f}")
    if itinerary.budget_warning:
        itinerary.assumptions.append(itinerary.budget_warning)
    itinerary.summary = _build_human_summary(city=city, days_output=itinerary.days)
    return itinerary


def _build_human_summary(*, city: str, days_output: list[ItineraryDay]) -> str:
    rows: list[str] = []
    for day in days_output:
        names = [item.poi.name for item in day.schedule if not item.is_backup]
        if not names:
            continue
        rows.append(f"第{day.day_number}天：{'、'.join(names)}")
    prefix = f"{city}{len(days_output)}天可执行行程"
    if not rows:
        return prefix
    return f"{prefix}：" + "；".join(rows)


def _average_routing_confidence(itinerary: Itinerary) -> float:
    rows: list[float] = []
    marker = "routing_confidence="
    for day in itinerary.days:
        for item in day.schedule:
            if item.is_backup:
                continue
            notes = str(item.notes or "")
            if marker not in notes:
                continue
            text = notes.split(marker, 1)[1].split("|", 1)[0].strip()
            try:
                rows.append(float(text))
            except ValueError:
                continue
    if not rows:
        return 0.6
    return sum(rows) / len(rows)


def _build_context_maps(weather_data: dict | None, calendar_data: dict | None) -> tuple[dict[int, dict], dict[int, dict]]:
    weather_map = {idx + 1: row for idx, row in enumerate((weather_data or {}).get("forecasts", []))}
    calendar_map = {idx + 1: row for idx, row in enumerate((calendar_data or {}).get("days", []))}
    return weather_map, calendar_map


def _pick_day_pois(
    *,
    day_no: int,
    unique: list[POI],
    cursor: int,
    daily_count: int,
    cluster_plan: list[list[POI]] | None,
    used_ids: set[str],
) -> tuple[list[POI], int]:
    if cluster_plan is not None:
        raw = list(cluster_plan[day_no - 1]) if day_no - 1 < len(cluster_plan) else []
        day_pois = [poi for poi in raw if poi.id not in used_ids]
        return day_pois, cursor
    day_pois = unique[cursor : cursor + daily_count]
    if day_pois:
        return day_pois, cursor + daily_count
    return [poi for poi in unique if poi.id not in used_ids][:daily_count], cursor


def _refine_day_pois(
    *,
    day_pois: list[POI],
    unique: list[POI],
    template: DayTemplate,
    must_visit_names: set[str],
    used_ids: set[str],
    plan_date: date,
    daily_count: int,
    cluster_lookup: dict[str, str],
) -> tuple[list[POI], bool, list[str]]:
    assumptions: list[str] = []
    opened = [
        poi
        for poi in day_pois
        if poi.id not in used_ids and is_open_on_date(poi, plan_date)
    ]
    filtered, allowed = enforce_day_cluster_cap(opened, cluster_map=cluster_lookup, max_clusters=2)
    topped = top_up_day_pois(filtered, all_pois=unique, used_ids=used_ids, plan_date=plan_date, daily_count=daily_count, preferred_clusters=allowed, cluster_lookup=cluster_lookup)
    final_pois, _allowed = enforce_day_cluster_cap(topped, cluster_map=cluster_lookup, max_clusters=2)
    final_pois, template_assumptions = rebalance_day_pois(
        final_pois,
        all_pois=[poi for poi in unique if is_open_on_date(poi, plan_date)],
        used_ids=used_ids,
        template=template,
        must_visit_names=must_visit_names,
    )
    assumptions.extend(template_assumptions)
    reduced = len({cluster_lookup.get(poi.id, "geo:0") for poi in topped}) > 2
    return final_pois, reduced, assumptions


def _build_day_output(
    *,
    day_no: int,
    plan_date: date,
    constraints: TripConstraints,
    unique: list[POI],
    day_pois: list[POI],
    weather_info: dict,
    holiday_name: str,
    crowd_level: str,
    mode: str,
    distance_fn: DistanceFn,
    travel_time_fn: TravelTimeFn,
    provider: RoutingProvider,
    cluster_lookup: dict[str, str],
    day_max_minutes: int,
) -> tuple[ItineraryDay, list[str]]:
    assumptions: list[str] = []
    if crowd_level in {"high", "very_high"}:
        assumptions.append(f"第{day_no}天人流量较高，已增加缓冲")
    ordered = optimize_daily_order(day_pois, distance_fn=distance_fn)
    schedule, meal_windows = assign_time_slots(
        ordered,
        plan_date=plan_date,
        transport_mode=mode,
        distance_fn=distance_fn,
        travel_time_fn=travel_time_fn,
        routing_provider=provider,
        crowd_level=crowd_level,
        holiday_hint=constraints.holiday_hint,
        cluster_lookup=cluster_lookup,
        day_max_minutes=day_max_minutes,
    )
    if not schedule:
        schedule = _fallback_schedule(ordered, crowd_level)
    day = ItineraryDay(
        day_number=day_no,
        date=plan_date,
        schedule=schedule,
        backups=pick_backup(unique, day_pois),
        day_summary=_build_day_summary(weather_info=weather_info, holiday_name=holiday_name, crowd_level=crowd_level),
        total_travel_minutes=round(sum(item.travel_minutes for item in schedule), 1),
        estimated_cost=0.0,
        meal_windows=meal_windows or ["12:00-13:00"],
    )
    return day, assumptions


def _plan_single_day(
    *,
    day_no: int,
    start_date: date,
    constraints: TripConstraints,
    unique: list[POI],
    cursor: int,
    daily_count: int,
    cluster_plan: list[list[POI]] | None,
    cluster_lookup: dict[str, str],
    template: DayTemplate,
    must_visit_names: set[str],
    used_ids: set[str],
    weather_map: dict[int, dict],
    calendar_map: dict[int, dict],
    mode: str,
    distance_fn: DistanceFn,
    travel_time_fn: TravelTimeFn,
    provider: RoutingProvider,
    day_max_minutes: int,
) -> tuple[ItineraryDay, int, list[str], set[str]]:
    plan_date = start_date + timedelta(days=day_no - 1)
    day_pois, next_cursor = _pick_day_pois(day_no=day_no, unique=unique, cursor=cursor, daily_count=daily_count, cluster_plan=cluster_plan, used_ids=used_ids)
    day_pois, cluster_reduced, template_assumptions = _refine_day_pois(
        day_pois=day_pois,
        unique=unique,
        template=template,
        must_visit_names=must_visit_names,
        used_ids=used_ids,
        plan_date=plan_date,
        daily_count=daily_count,
        cluster_lookup=cluster_lookup,
    )
    if not day_pois and unique:
        day_pois = [
            poi
            for poi in unique
            if poi.id not in used_ids and is_open_on_date(poi, plan_date)
        ][:1]
    if not day_pois and unique:
        day_pois = [poi for poi in unique if is_open_on_date(poi, plan_date)][:1]
    weather_info = weather_map.get(day_no, {})
    calendar_info = calendar_map.get(day_no, {})
    crowd_level = str(calendar_info.get("crowd_level", "normal"))
    holiday_name = str(calendar_info.get("holiday_name", ""))
    day, assumptions = _build_day_output(
        day_no=day_no,
        plan_date=plan_date,
        constraints=constraints,
        unique=unique,
        day_pois=day_pois,
        weather_info=weather_info,
        holiday_name=holiday_name,
        crowd_level=crowd_level,
        mode=mode,
        distance_fn=distance_fn,
        travel_time_fn=travel_time_fn,
        provider=provider,
        cluster_lookup=cluster_lookup,
        day_max_minutes=day_max_minutes,
    )
    assumptions.extend(template_assumptions)
    if cluster_reduced:
        assumptions.insert(0, f"day{day_no} reduced to <=2 geographic clusters")
    return day, next_cursor, assumptions, {poi.id for poi in day_pois}


def generate_itinerary_impl(
    constraints: TripConstraints,
    profile: UserProfile,
    poi_candidates: list[POI],
    *,
    transport_mode: str | None = None,
    weather_data: dict | None = None,
    calendar_data: dict | None = None,
    distance_fn: DistanceFn = estimate_distance,
    travel_time_fn: TravelTimeFn = estimate_travel_time,
    routing_provider: RoutingProvider | None = None,
) -> Itinerary:
    mode = transport_mode or constraints.transport_mode.value
    start_date = constraints.date_start or date.today()
    provider = routing_provider or build_routing_provider()
    unique, daily_count, assumptions = prepare_candidate_pool(constraints, profile, poi_candidates)
    _persona_max_pois, persona_max_daily_minutes = persona_limits(profile)
    assumptions.append(f"persona_profile={persona_name(profile)}")
    unique = annotate_pois_fact_confidence(unique)
    weather_map, calendar_map = _build_context_maps(weather_data, calendar_data)
    cluster_lookup = build_cluster_map(unique, distance_fn=distance_fn)
    cluster_plan = cluster_day_plan(unique, days=constraints.days, daily_count=daily_count)
    template = resolve_day_template(constraints, profile, daily_count=daily_count)
    must_visit_names = {name.strip() for name in constraints.must_visit if name.strip()}
    days_output: list[ItineraryDay] = []
    used_ids: set[str] = set()
    cursor = 0
    for day_no in range(1, constraints.days + 1):
        day, cursor, day_assumptions, day_used_ids = _plan_single_day(
            day_no=day_no,
            start_date=start_date,
            constraints=constraints,
            unique=unique,
            cursor=cursor,
            daily_count=daily_count,
            cluster_plan=cluster_plan,
            cluster_lookup=cluster_lookup,
            template=template,
            must_visit_names=must_visit_names,
            used_ids=used_ids,
            weather_map=weather_map,
            calendar_map=calendar_map,
            mode=mode,
            distance_fn=distance_fn,
            travel_time_fn=travel_time_fn,
            provider=provider,
            day_max_minutes=persona_max_daily_minutes,
        )
        days_output.append(day)
        assumptions.extend(day_assumptions)
        used_ids.update(day_used_ids)
    city = constraints.city or (poi_candidates[0].city if poi_candidates else "")
    return _apply_budget_and_summary(constraints=constraints, profile=profile, city=city, days_output=days_output, assumptions=assumptions)


__all__ = ["generate_itinerary_impl"]
