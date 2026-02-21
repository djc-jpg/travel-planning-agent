"""Diff-based itinerary edit helpers."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field

from app.application.contracts import TripRequest

_DAY_PATTERN = re.compile(r"第\s*(\d+)\s*天")
_REPLACE_PATTERN = re.compile(
    r"(?:把|将)?(?P<old>[^\s，。,；;]{1,24})?\s*(?:换成|替换成|改成)\s*(?P<new>[^\s，。,；;]{1,24})"
)
_ADD_PATTERN = re.compile(
    r"(?:在|把)?(?:第\s*(?P<day>\d+)\s*天)?[^。；\n]{0,24}?(?:加入|添加|加上|安排)\s*(?P<poi>[^\s，。,；;]{1,24})"
)
_REMOVE_PATTERN = re.compile(
    r"(?:第\s*(?P<day>\d+)\s*天)?[^。；\n]{0,16}?(?:删除|去掉|移除)\s*(?P<poi>[^\s，。,；;]{1,24})"
)
_TIME_RANGE_PATTERN = re.compile(r"(?P<start>\d{1,2}:\d{2})\s*-\s*(?P<end>\d{1,2}:\d{2})")
_ADJUST_TIME_PATTERN = re.compile(
    r"(?:第\s*(?P<day>\d+)\s*天)?[^。；\n]{0,24}?(?:调整到|改到|安排在)\s*(?P<window>上午|中午|下午|晚上|早上|\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2})"
)
_LUNCH_TOKENS = ("午休", "午餐休息", "中午休息", "午间休息")
_DEFAULT_LUNCH_WINDOW = "12:00-13:00"
_DAY_PREFIX_PATTERN = re.compile(r"^第\s*\d+\s*天")


class ReplaceStopPatch(BaseModel):
    day_number: int = Field(ge=1)
    old_poi: str | None = None
    new_poi: str = Field(min_length=1)


class AddStopPatch(BaseModel):
    day_number: int = Field(ge=1)
    poi: str = Field(min_length=1)


class RemoveStopPatch(BaseModel):
    day_number: int = Field(ge=1)
    poi: str = Field(min_length=1)


class AdjustTimePatch(BaseModel):
    day_number: int = Field(ge=1)
    poi: str | None = None
    window: str = Field(min_length=1)


class LunchBreakPatch(BaseModel):
    day_number: int | None = Field(default=None, ge=1)
    window: str = _DEFAULT_LUNCH_WINDOW


class PlanEditPatch(BaseModel):
    replace_stop: ReplaceStopPatch | None = None
    add_stop: AddStopPatch | None = None
    remove_stop: RemoveStopPatch | None = None
    adjust_time: AdjustTimePatch | None = None
    lunch_break: LunchBreakPatch | None = None
    instruction: str = ""


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        rows.append(text)
    return rows


def _extract_day(text: str) -> int | None:
    match = _DAY_PATTERN.search(text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _extract_replace(text: str) -> tuple[str | None, str] | None:
    match = _REPLACE_PATTERN.search(text)
    if not match:
        return None
    old = _normalize_poi_name((match.group("old") or "").strip()) or None
    new = _normalize_poi_name((match.group("new") or "").strip())
    if not new:
        return None
    return old, new


def _extract_add(text: str, fallback_day: int | None) -> AddStopPatch | None:
    match = _ADD_PATTERN.search(text)
    if not match:
        return None
    poi = _normalize_poi_name(match.group("poi") or "")
    if not poi:
        return None
    day = _coerce_day(match.group("day"), fallback=fallback_day)
    return AddStopPatch(day_number=day, poi=poi)


def _extract_remove(text: str, fallback_day: int | None) -> RemoveStopPatch | None:
    match = _REMOVE_PATTERN.search(text)
    if not match:
        return None
    poi = _normalize_poi_name(match.group("poi") or "")
    if not poi:
        return None
    day = _coerce_day(match.group("day"), fallback=fallback_day)
    return RemoveStopPatch(day_number=day, poi=poi)


def _extract_adjust_time(text: str, fallback_day: int | None) -> AdjustTimePatch | None:
    match = _ADJUST_TIME_PATTERN.search(text)
    if not match:
        return None
    day = _coerce_day(match.group("day"), fallback=fallback_day)
    window = _normalize_window(match.group("window") or "")
    if not window:
        return None
    return AdjustTimePatch(day_number=day, poi=None, window=window)


def _coerce_day(raw: str | None, *, fallback: int | None) -> int:
    if raw:
        try:
            day = int(raw)
            if day > 0:
                return day
        except ValueError:
            pass
    if fallback and fallback > 0:
        return fallback
    return 1


def _normalize_poi_name(name: str) -> str:
    text = _DAY_PREFIX_PATTERN.sub("", str(name or "").strip())
    text = text.strip("，。,；;:： 的")
    return text.strip()


def _normalize_window(window: str) -> str:
    value = str(window or "").strip()
    return value.replace(" ", "")


def _contains_lunch_edit(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    return any(token in lowered for token in _LUNCH_TOKENS)


def build_edit_patch(
    *,
    message: str,
    metadata: Mapping[str, Any] | None,
    previous_itinerary: Mapping[str, Any] | None = None,
) -> PlanEditPatch | None:
    if isinstance(metadata, Mapping):
        raw_patch = metadata.get("edit_patch")
        if isinstance(raw_patch, Mapping):
            try:
                return PlanEditPatch.model_validate(raw_patch)
            except Exception:
                pass

    text = str(message or "")
    day = _extract_day(text)
    replace = _extract_replace(text)
    add = _extract_add(text, day)
    remove = _extract_remove(text, day)
    adjust = _extract_adjust_time(text, day)
    lunch = _contains_lunch_edit(text)
    if replace is None and add is None and remove is None and adjust is None and not lunch:
        return None

    replace_patch = None
    if replace is not None:
        old_poi, new_poi = replace
        inferred_day = day if day is not None else 1
        if inferred_day < 1:
            inferred_day = 1
        replace_patch = ReplaceStopPatch(day_number=inferred_day, old_poi=old_poi, new_poi=new_poi)

    lunch_patch = None
    if lunch:
        lunch_patch = LunchBreakPatch(day_number=day, window=_DEFAULT_LUNCH_WINDOW)

    _ = previous_itinerary
    return PlanEditPatch(
        replace_stop=replace_patch,
        add_stop=add,
        remove_stop=remove,
        adjust_time=adjust,
        lunch_break=lunch_patch,
        instruction=text.strip(),
    )


def _append_time_preference(
    rows: list[dict[str, Any]],
    *,
    day_number: int,
    window: str,
    poi: str | None,
) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {"day_number": day_number, "window": window}
    if poi:
        payload["poi"] = poi

    normalized: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for row in rows + [payload]:
        if not isinstance(row, Mapping):
            continue
        key = (
            int(row.get("day_number", 0) or 0),
            str(row.get("window", "") or "").strip(),
            str(row.get("poi", "") or "").strip(),
        )
        if key in seen or key[0] <= 0 or not key[1]:
            continue
        seen.add(key)
        normalized.append(
            {
                "day_number": key[0],
                "window": key[1],
                **({"poi": key[2]} if key[2] else {}),
            }
        )
    return normalized


def apply_edit_patch_to_request(request: TripRequest, patch: PlanEditPatch) -> TripRequest:
    constraints = dict(request.constraints)
    metadata = dict(request.metadata)

    replace = patch.replace_stop
    if replace is not None:
        must_visit = list(constraints.get("must_visit", []))
        must_visit.append(replace.new_poi)
        constraints["must_visit"] = _dedupe(must_visit)

        if replace.old_poi:
            avoid = list(constraints.get("avoid", []))
            avoid.append(replace.old_poi)
            constraints["avoid"] = _dedupe(avoid)

    if patch.add_stop is not None:
        must_visit = list(constraints.get("must_visit", []))
        must_visit.append(patch.add_stop.poi)
        constraints["must_visit"] = _dedupe(must_visit)

    if patch.remove_stop is not None:
        avoid = list(constraints.get("avoid", []))
        avoid.append(patch.remove_stop.poi)
        constraints["avoid"] = _dedupe(avoid)

    if patch.adjust_time is not None:
        time_prefs = list(constraints.get("poi_time_preferences", []))
        constraints["poi_time_preferences"] = _append_time_preference(
            time_prefs,
            day_number=patch.adjust_time.day_number,
            window=patch.adjust_time.window,
            poi=patch.adjust_time.poi,
        )

    lunch = patch.lunch_break
    if lunch is not None:
        constraints["lunch_break_window"] = lunch.window
        if lunch.day_number is not None:
            constraints["lunch_break_day"] = lunch.day_number

    metadata["edit_patch"] = patch.model_dump(mode="json")
    metadata["edit_mode"] = "diff"
    return request.model_copy(update={"constraints": constraints, "metadata": metadata})


def _day_index(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            day_no = int(row.get("day_number", 0))
        except (TypeError, ValueError):
            continue
        if day_no <= 0:
            continue
        out[day_no] = row
    return out


def _poi_name(item: Mapping[str, Any]) -> str:
    poi = item.get("poi")
    if not isinstance(poi, Mapping):
        return ""
    return str(poi.get("name", "") or "").strip()


def _rebuild_summary(itinerary: dict[str, Any]) -> str:
    city = str(itinerary.get("city", "") or "")
    days = itinerary.get("days", [])
    if not isinstance(days, list):
        return city
    parts: list[str] = []
    for day in days:
        if not isinstance(day, dict):
            continue
        day_no = day.get("day_number")
        schedule = day.get("schedule", [])
        names: list[str] = []
        if isinstance(schedule, list):
            for item in schedule:
                if not isinstance(item, dict) or item.get("is_backup"):
                    continue
                name = _poi_name(item)
                if name:
                    names.append(name)
        if names:
            parts.append(f"第{day_no}天：{'、'.join(names)}")
    prefix = f"{city}{len(days)}天可执行行程"
    return f"{prefix}：" + "；".join(parts) if parts else prefix


def _apply_lunch_patch(itinerary: dict[str, Any], patch: LunchBreakPatch) -> None:
    days = itinerary.get("days", [])
    if not isinstance(days, list):
        return
    for day in days:
        if not isinstance(day, dict):
            continue
        day_no = int(day.get("day_number", 0) or 0)
        if patch.day_number is not None and day_no != patch.day_number:
            continue
        windows = list(day.get("meal_windows", []))
        if patch.window not in windows:
            windows.append(patch.window)
        day["meal_windows"] = windows


def _append_assumption(itinerary: dict[str, Any], text: str) -> None:
    assumptions = list(itinerary.get("assumptions", []))
    assumptions.append(text)
    itinerary["assumptions"] = _dedupe(assumptions)


def _find_day(itinerary: dict[str, Any], day_number: int) -> dict[str, Any] | None:
    days = itinerary.get("days", [])
    if not isinstance(days, list):
        return None
    for day in days:
        if not isinstance(day, dict):
            continue
        if int(day.get("day_number", 0) or 0) == day_number:
            return day
    return None


def _promote_backup_for_add(day: dict[str, Any], poi_name: str) -> bool:
    schedule = day.get("schedule")
    backups = day.get("backups")
    if not isinstance(schedule, list) or not isinstance(backups, list):
        return False

    for item in schedule:
        if isinstance(item, dict) and _poi_name(item) == poi_name:
            return True

    for index, item in enumerate(backups):
        if not isinstance(item, dict):
            continue
        if _poi_name(item) != poi_name:
            continue
        promoted = copy.deepcopy(item)
        promoted["is_backup"] = False
        schedule.append(promoted)
        backups.pop(index)
        day["schedule"] = schedule
        day["backups"] = backups
        return True

    return False


def _remove_poi_from_day(day: dict[str, Any], poi_name: str) -> bool:
    changed = False
    for key in ("schedule", "backups"):
        rows = day.get(key)
        if not isinstance(rows, list):
            continue
        filtered: list[Any] = []
        for item in rows:
            if isinstance(item, Mapping) and _poi_name(item) == poi_name:
                changed = True
                continue
            filtered.append(item)
        day[key] = filtered
    return changed


def _apply_adjust_time_to_day(day: dict[str, Any], patch: AdjustTimePatch) -> bool:
    candidates: list[dict[str, Any]] = []
    for key in ("schedule", "backups"):
        rows = day.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict):
                candidates.append(row)

    if not candidates:
        return False

    target: dict[str, Any] | None = None
    if patch.poi:
        for item in candidates:
            if _poi_name(item) == patch.poi:
                target = item
                break
    else:
        target = candidates[0]

    if target is None:
        return False

    window = patch.window
    time_match = _TIME_RANGE_PATTERN.fullmatch(window)
    if time_match:
        target["start_time"] = time_match.group("start")
        target["end_time"] = time_match.group("end")
    else:
        note = str(target.get("notes", "") or "").strip()
        suffix = f"时间偏好:{window}"
        target["notes"] = f"{note} | {suffix}" if note and suffix not in note else (note or suffix)
    return True


def merge_itinerary_by_patch(
    *,
    current_itinerary: dict[str, Any] | None,
    previous_itinerary: Mapping[str, Any] | None,
    patch: PlanEditPatch | None,
) -> dict[str, Any] | None:
    if patch is None or not isinstance(current_itinerary, dict):
        return current_itinerary

    merged = copy.deepcopy(current_itinerary)
    replace = patch.replace_stop
    if replace is not None and isinstance(previous_itinerary, Mapping):
        prev_days_raw = previous_itinerary.get("days", [])
        curr_days_raw = current_itinerary.get("days", [])
        if isinstance(prev_days_raw, list) and isinstance(curr_days_raw, list):
            prev_days = _day_index(prev_days_raw)
            curr_days = _day_index(curr_days_raw)
            target_day = replace.day_number
            if target_day in prev_days and target_day in curr_days:
                rows: list[dict[str, Any]] = []
                seen: set[int] = set()
                for day in prev_days_raw:
                    if not isinstance(day, dict):
                        continue
                    day_no = int(day.get("day_number", 0) or 0)
                    if day_no <= 0:
                        continue
                    rows.append(copy.deepcopy(curr_days[target_day] if day_no == target_day else day))
                    seen.add(day_no)
                for day in curr_days_raw:
                    if not isinstance(day, dict):
                        continue
                    day_no = int(day.get("day_number", 0) or 0)
                    if day_no <= 0 or day_no in seen:
                        continue
                    rows.append(copy.deepcopy(day))
                rows.sort(key=lambda row: int(row.get("day_number", 0) or 0))
                merged["days"] = rows
                _append_assumption(merged, f"edit_patch:replace_stop day={target_day}")

    if patch.add_stop is not None:
        day = _find_day(merged, patch.add_stop.day_number)
        applied = bool(day and _promote_backup_for_add(day, patch.add_stop.poi))
        if applied:
            _append_assumption(merged, f"edit_patch:add_stop day={patch.add_stop.day_number}")
        else:
            _append_assumption(
                merged,
                f"edit_patch:add_stop pending day={patch.add_stop.day_number} poi={patch.add_stop.poi}",
            )

    if patch.remove_stop is not None:
        day = _find_day(merged, patch.remove_stop.day_number)
        removed = bool(day and _remove_poi_from_day(day, patch.remove_stop.poi))
        if removed:
            _append_assumption(merged, f"edit_patch:remove_stop day={patch.remove_stop.day_number}")
        else:
            _append_assumption(
                merged,
                f"edit_patch:remove_stop pending day={patch.remove_stop.day_number} poi={patch.remove_stop.poi}",
            )

    if patch.adjust_time is not None:
        day = _find_day(merged, patch.adjust_time.day_number)
        adjusted = bool(day and _apply_adjust_time_to_day(day, patch.adjust_time))
        if adjusted:
            _append_assumption(merged, f"edit_patch:adjust_time day={patch.adjust_time.day_number}")
        else:
            _append_assumption(
                merged,
                f"edit_patch:adjust_time pending day={patch.adjust_time.day_number} window={patch.adjust_time.window}",
            )

    if patch.lunch_break is not None:
        _apply_lunch_patch(merged, patch.lunch_break)
        scope = patch.lunch_break.day_number if patch.lunch_break.day_number is not None else "all"
        _append_assumption(merged, f"edit_patch:lunch_break day={scope}")

    merged["summary"] = _rebuild_summary(merged)
    return merged


__all__ = [
    "PlanEditPatch",
    "apply_edit_patch_to_request",
    "build_edit_patch",
    "merge_itinerary_by_patch",
]
