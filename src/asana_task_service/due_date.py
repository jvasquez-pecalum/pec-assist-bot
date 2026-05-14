"""Due-date computation for Asana tasks.

Pure module — `resolve_due_date` is deterministic given an injected `now`.
"""

import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import holidays

BUSINESS_TZ = ZoneInfo(os.getenv("BUSINESS_TIMEZONE", "America/Los_Angeles"))


def _parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


BUSINESS_HOURS_START: time = _parse_hhmm(os.getenv("BUSINESS_HOURS_START", "09:00"))
BUSINESS_HOURS_END: time = _parse_hhmm(os.getenv("BUSINESS_HOURS_END", "17:00"))

_US_HOLIDAYS = holidays.UnitedStates()


def _is_business_day(d: date) -> bool:
    return d.weekday() < 5 and d not in _US_HOLIDAYS


def _roll_forward_to_business_day(d: date) -> date:
    cursor = d
    while not _is_business_day(cursor):
        cursor += timedelta(days=1)
    return cursor


def _advance_business_days(start: date, n: int) -> date:
    """Walk forward day-by-day from `start`; only business days count toward `n`.

    `n` must be >= 1. The result is always strictly after `start`.
    """
    cursor = start
    remaining = n
    while remaining > 0:
        cursor += timedelta(days=1)
        if _is_business_day(cursor):
            remaining -= 1
    return cursor


def _next_business_moment(dt: datetime) -> datetime:
    """Return `dt` if it sits inside business hours on a business day; otherwise
    fast-forward to the next business day's BUSINESS_HOURS_START.

    Business hours interval is half-open: [START, END).
    """
    d = dt.date()
    t = dt.time()
    if _is_business_day(d) and BUSINESS_HOURS_START <= t < BUSINESS_HOURS_END:
        return dt
    if _is_business_day(d) and t < BUSINESS_HOURS_START:
        return datetime.combine(d, BUSINESS_HOURS_START, tzinfo=dt.tzinfo)
    next_day = d + timedelta(days=1)
    while not _is_business_day(next_day):
        next_day += timedelta(days=1)
    return datetime.combine(next_day, BUSINESS_HOURS_START, tzinfo=dt.tzinfo)


def _add_business_hours(start: datetime, hours: float) -> datetime:
    """Add `hours` of business time to a tz-aware datetime.

    Consumes time only inside the [START, END) window on business days.
    """
    cursor = _next_business_moment(start)
    remaining = timedelta(hours=hours)
    while remaining > timedelta(0):
        end_of_day = datetime.combine(
            cursor.date(), BUSINESS_HOURS_END, tzinfo=cursor.tzinfo
        )
        available_today = end_of_day - cursor
        if remaining <= available_today:
            return cursor + remaining
        remaining -= available_today
        cursor = _next_business_moment(end_of_day)
    return cursor


# "4h" sentinel = "+4 business hours" (datetime precision via due_at).
# int N = N business days (date precision via due_on).
SLA_MATRIX: dict[str, dict[str, int | str]] = {
    "password_reset":        {"critical": "4h", "high": 1, "medium": 1, "low": 1},
    "software_issue":        {"critical": "4h", "high": 1, "medium": 3, "low": 5},
    "hardware_issue":        {"critical": "4h", "high": 1, "medium": 3, "low": 5},
    "access_request":        {"critical": "4h", "high": 1, "medium": 2, "low": 3},
    "general_support":       {"critical": "4h", "high": 1, "medium": 3, "low": 5},
    "other":                 {"critical": "4h", "high": 2, "medium": 5, "low": 7},
    "data_engineering":      {"critical": "4h", "high": 2, "medium": 5, "low": 10},
    "business_reports":      {"critical": "4h", "high": 2, "medium": 5, "low": 10},
    "business_intelligence": {"critical": "4h", "high": 3, "medium": 7, "low": 14},
    "ai_initiatives":        {"critical": "4h", "high": 3, "medium": 7, "low": 14},
    "general_inquiry":       {"critical": "4h", "high": 2, "medium": 5, "low": 7},
}


@dataclass(frozen=True)
class DueDate:
    """Exactly one of due_on / due_at is set."""
    due_on: Optional[str] = None
    due_at: Optional[str] = None

    def __post_init__(self):
        if (self.due_on is None) == (self.due_at is None):
            raise ValueError("Exactly one of due_on/due_at must be set")


def resolve_due_date(
    intent: str,
    urgency: str,
    client_supplied: Optional[str],
    now: Optional[datetime] = None,
) -> DueDate:
    """Compute the Asana due-date for a task.

    Returns a DueDate with exactly one of due_on / due_at set.

    Raises:
        ValueError: if client_supplied is malformed or in the past.
    """
    now = now if now is not None else datetime.now(timezone.utc)
    now_local = now.astimezone(BUSINESS_TZ)

    if client_supplied:
        try:
            parsed = datetime.strptime(client_supplied, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError("due_date must be YYYY-MM-DD")
        if parsed < now_local.date():
            raise ValueError("due_date is in the past")
        rolled = _roll_forward_to_business_day(parsed)
        return DueDate(due_on=rolled.isoformat())

    sla = SLA_MATRIX[intent][urgency]
    if sla == "4h":
        deadline_local = _add_business_hours(now_local, 4)
        deadline_utc = deadline_local.astimezone(timezone.utc)
        return DueDate(due_at=deadline_utc.strftime("%Y-%m-%dT%H:%M:%S+00:00"))
    assert isinstance(sla, int)
    target = _advance_business_days(now_local.date(), sla)
    return DueDate(due_on=target.isoformat())
