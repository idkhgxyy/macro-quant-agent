from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, Tuple


def _parse_hhmm(s: str) -> time:
    parts = (s or "").split(":")
    if len(parts) != 2:
        return time(0, 0)
    h = int(parts[0])
    m = int(parts[1])
    return time(hour=h, minute=m)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    days = (weekday - d.weekday()) % 7
    d = d + timedelta(days=days)
    return d + timedelta(weeks=max(n - 1, 0))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        d = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        d = date(year, month + 1, 1) - timedelta(days=1)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d


def _observed_fixed_holiday(year: int, month: int, day: int) -> date:
    d = date(year, month, day)
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def _easter_sunday(year: int) -> date:
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _good_friday(year: int) -> date:
    return _easter_sunday(year) - timedelta(days=2)


def _us_market_holidays(year: int) -> Dict[date, str]:
    holidays = {
        _observed_fixed_holiday(year, 1, 1): "new_years_day",
        _nth_weekday(year, 1, 0, 3): "martin_luther_king_jr_day",
        _nth_weekday(year, 2, 0, 3): "presidents_day",
        _good_friday(year): "good_friday",
        _last_weekday(year, 5, 0): "memorial_day",
        _observed_fixed_holiday(year, 7, 4): "independence_day",
        _nth_weekday(year, 9, 0, 1): "labor_day",
        _nth_weekday(year, 11, 3, 4): "thanksgiving_day",
        _observed_fixed_holiday(year, 12, 25): "christmas_day",
    }
    if year >= 2022:
        holidays[_observed_fixed_holiday(year, 6, 19)] = "juneteenth"
    return holidays


def _us_market_early_closes(year: int) -> Dict[date, str]:
    early = {}

    thanksgiving = _nth_weekday(year, 11, 3, 4)
    day_after = thanksgiving + timedelta(days=1)
    if day_after.weekday() < 5:
        early[day_after] = "day_after_thanksgiving"

    christmas_eve = date(year, 12, 24)
    if christmas_eve.weekday() < 5 and christmas_eve not in _us_market_holidays(year):
        early[christmas_eve] = "christmas_eve"

    july4 = date(year, 7, 4)
    if july4.weekday() in {1, 2, 3, 4}:
        early_close = date(year, 7, 3)
    elif july4.weekday() == 6:
        early_close = date(year, 7, 2)
    elif july4.weekday() == 0:
        early_close = date(year, 7, 1)
    else:
        early_close = None
    if early_close and early_close.weekday() < 5 and early_close not in _us_market_holidays(year):
        early[early_close] = "independence_day_eve"

    return early


def get_market_session(
    now: datetime,
    tz: str,
    start_hhmm: str,
    end_hhmm: str,
    half_day_end_hhmm: str = "13:00",
) -> Dict[str, object]:
    local = now.astimezone(ZoneInfo(tz))
    local_date = local.date()
    current_time = local.time().replace(second=0, microsecond=0)

    holidays = {}
    for y in (local_date.year - 1, local_date.year, local_date.year + 1):
        holidays.update(_us_market_holidays(y))
    early_closes = _us_market_early_closes(local_date.year)

    holiday_name = holidays.get(local_date)
    early_close_name = early_closes.get(local_date)
    is_weekend = local.weekday() >= 5

    start_t = _parse_hhmm(start_hhmm)
    regular_end_t = _parse_hhmm(end_hhmm)
    half_day_end_t = _parse_hhmm(half_day_end_hhmm)
    effective_end_t = half_day_end_t if early_close_name else regular_end_t

    market_state = "open"
    session_reason = "in_window"

    if is_weekend:
        market_state = "closed"
        session_reason = "weekend"
    elif holiday_name:
        market_state = "closed"
        session_reason = "holiday"
    elif current_time < start_t:
        market_state = "planning_only"
        session_reason = "pre_market"
    elif current_time > effective_end_t:
        market_state = "planning_only"
        session_reason = "after_early_close" if early_close_name else "after_hours"

    return {
        "market_state": market_state,
        "session_reason": session_reason,
        "market_date": local_date.isoformat(),
        "local_time": current_time.isoformat(),
        "timezone": tz,
        "is_trading_day": (not is_weekend) and (holiday_name is None),
        "can_generate_plan": market_state != "closed",
        "can_place_orders": market_state == "open",
        "holiday_name": holiday_name,
        "early_close_name": early_close_name,
        "is_half_day": bool(early_close_name),
        "rth_start": start_t.strftime("%H:%M"),
        "rth_end": regular_end_t.strftime("%H:%M"),
        "effective_rth_end": effective_end_t.strftime("%H:%M"),
    }


def in_time_window(now: datetime, tz: str, start_hhmm: str, end_hhmm: str) -> Tuple[bool, str]:
    session = get_market_session(now, tz, start_hhmm, end_hhmm)
    return bool(session["can_place_orders"]), str(session["session_reason"])
