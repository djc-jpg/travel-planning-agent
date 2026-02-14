"""Mock calendar adapter with holiday and crowd estimation."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.tools.interfaces import CalendarInput, CalendarResult, DayCalendarInfo

FIXED_HOLIDAYS: dict[tuple[int, int], str] = {
    (1, 1): "元旦",
    (5, 1): "劳动节",
    (5, 2): "劳动节",
    (5, 3): "劳动节",
    (5, 4): "劳动节",
    (5, 5): "劳动节",
    (10, 1): "国庆节",
    (10, 2): "国庆节",
    (10, 3): "国庆节",
    (10, 4): "国庆节",
    (10, 5): "国庆节",
    (10, 6): "国庆节",
    (10, 7): "国庆节",
}

SPRING_FESTIVAL_EVE = {
    2024: (2, 9),
    2025: (1, 28),
    2026: (2, 16),
    2027: (2, 5),
    2028: (1, 25),
    2029: (2, 12),
    2030: (2, 2),
}

MID_AUTUMN = {
    2024: (9, 17),
    2025: (10, 6),
    2026: (9, 25),
    2027: (9, 15),
    2028: (10, 3),
    2029: (9, 22),
    2030: (9, 12),
}

QINGMING = {
    2024: (4, 4),
    2025: (4, 4),
    2026: (4, 5),
    2027: (4, 5),
    2028: (4, 4),
    2029: (4, 4),
    2030: (4, 5),
}

DRAGON_BOAT = {
    2024: (6, 10),
    2025: (5, 31),
    2026: (6, 19),
    2027: (6, 9),
    2028: (5, 28),
    2029: (6, 16),
    2030: (6, 5),
}


def _get_holidays_for_year(year: int) -> dict[tuple[int, int], str]:
    holidays = dict(FIXED_HOLIDAYS)

    sf = SPRING_FESTIVAL_EVE.get(year)
    if sf:
        sf_date = datetime(year, sf[0], sf[1])
        for i in range(8):
            d = sf_date + timedelta(days=i)
            holidays[(d.month, d.day)] = "春节"

    qm = QINGMING.get(year)
    if qm:
        qm_date = datetime(year, qm[0], qm[1])
        for i in range(-1, 2):
            d = qm_date + timedelta(days=i)
            holidays[(d.month, d.day)] = "清明节"

    db = DRAGON_BOAT.get(year)
    if db:
        db_date = datetime(year, db[0], db[1])
        for i in range(-1, 2):
            d = db_date + timedelta(days=i)
            holidays[(d.month, d.day)] = "端午节"

    ma = MID_AUTUMN.get(year)
    if ma:
        ma_date = datetime(year, ma[0], ma[1])
        for i in range(-1, 2):
            d = ma_date + timedelta(days=i)
            holidays[(d.month, d.day)] = "中秋节"

    return holidays


def _estimate_crowd_level(is_holiday: bool, is_weekend: bool, holiday_name: str) -> str:
    if holiday_name in ("国庆节", "春节"):
        return "very_high"
    if is_holiday or is_weekend:
        return "high"
    return "normal"


def get_calendar(params: CalendarInput) -> CalendarResult:
    try:
        start = datetime.strptime(params.date_start, "%Y-%m-%d")
    except ValueError:
        start = datetime.now()

    days_info: list[DayCalendarInfo] = []
    for i in range(params.days):
        day_date = start + timedelta(days=i)
        holidays = _get_holidays_for_year(day_date.year)
        is_weekend = day_date.weekday() >= 5
        holiday_name = holidays.get((day_date.month, day_date.day), "")
        is_holiday = bool(holiday_name)
        crowd_level = _estimate_crowd_level(is_holiday, is_weekend, holiday_name)

        days_info.append(
            DayCalendarInfo(
                date=day_date.strftime("%Y-%m-%d"),
                is_holiday=is_holiday,
                is_weekend=is_weekend,
                holiday_name=holiday_name,
                crowd_level=crowd_level,
            )
        )

    return CalendarResult(days=days_info)

