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


def resolve_due_date(
    intent: str,
    urgency: str,
    client_supplied: Optional[str],
    now: Optional[datetime] = None,
) -> DueDate:
    raise NotImplementedError
