# Asana Due-Date Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the asana_task_service's naive UTC + calendar-day + urgency-only due-date logic with a timezone-aware, business-calendar-aware, intent × urgency SLA model.

**Architecture:** Extract due-date computation into a new `due_date.py` module exposing a single `resolve_due_date(intent, urgency, client_supplied, now=None) -> DueDate` function. The function is pure given `now` (injectable for tests). The endpoint in `main.py` delegates to it and converts `ValueError` into HTTP 400. Holidays come from the `holidays` package (US federal); business hours and timezone come from env vars.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, pytest, `holidays`, stdlib `zoneinfo` (+ `tzdata` for Windows), `datetime`.

**Spec:** [docs/superpowers/specs/2026-05-13-asana-due-date-refactor-design.md](../specs/2026-05-13-asana-due-date-refactor-design.md)

---

## File Map

| Path | Action | Responsibility |
|---|---|---|
| `src/asana_task_service/due_date.py` | Create | All due-date computation: config, SLA matrix, helpers, public `resolve_due_date` |
| `src/asana_task_service/test_due_date.py` | Create | Pytest unit tests for `due_date.py`, deterministic via injected `now` |
| `src/asana_task_service/pytest.ini` | Create | Anchors pytest rootdir at the service folder (mirrors `email_task_service/pytest.ini`) |
| `src/asana_task_service/requirements.txt` | Modify | Add `holidays`, `tzdata`, `pytest` (dev) |
| `src/asana_task_service/.env.example` | Modify | Add `BUSINESS_TIMEZONE`, `BUSINESS_HOURS_START`, `BUSINESS_HOURS_END` |
| `src/asana_task_service/main.py` | Modify | Delete `_get_due_date_from_urgency`; call `resolve_due_date`; replace 4× `datetime.utcnow()` with `datetime.now(timezone.utc)` |
| `src/asana_task_service/README.md` | Modify | Replace "urgency-based due date" bullet with accurate description; add "Due-date logic" section |

---

## Task 1: Add dependencies, env vars, and pytest scaffolding

**Files:**
- Modify: `src/asana_task_service/requirements.txt`
- Modify: `src/asana_task_service/.env.example`
- Create: `src/asana_task_service/pytest.ini`

- [ ] **Step 1: Add `holidays`, `tzdata`, and `pytest` to requirements**

Edit `src/asana_task_service/requirements.txt` — append these three lines:

```
holidays>=0.40
tzdata>=2024.1
pytest>=8.0
```

- [ ] **Step 2: Add env vars to `.env.example`**

Append to `src/asana_task_service/.env.example`:

```
# Due-date computation
# IANA timezone driving all date math
BUSINESS_TIMEZONE=America/Los_Angeles

# Business hours window (24h HH:MM) in BUSINESS_TIMEZONE
BUSINESS_HOURS_START=09:00
BUSINESS_HOURS_END=17:00
```

- [ ] **Step 3: Create `pytest.ini` in the service folder**

Create `src/asana_task_service/pytest.ini` with:

```
[pytest]
testpaths = .
python_files = test_*.py
```

This anchors pytest's rootdir at the service folder so tests can use top-level imports (`from due_date import ...`), matching how `uvicorn main:app` runs the service.

- [ ] **Step 4: Install dependencies**

Run from repo root:
```bash
pip install -r src/asana_task_service/requirements.txt
```
Expected: `holidays`, `tzdata`, and `pytest` install successfully.

- [ ] **Step 5: Verify imports**

Run:
```bash
python -c "import holidays; from zoneinfo import ZoneInfo; print(ZoneInfo('America/Los_Angeles'))"
```
Expected: `America/Los_Angeles` printed with no exception.

- [ ] **Step 6: Commit**

```bash
git add src/asana_task_service/requirements.txt src/asana_task_service/.env.example src/asana_task_service/pytest.ini
git commit -m "feat(asana): add holidays/tzdata deps, business-tz env vars, pytest config"
```

---

## Task 2: Create `due_date.py` skeleton with config and matrix

**Files:**
- Create: `src/asana_task_service/due_date.py`

- [ ] **Step 1: Create the file with config, dataclass, and matrix**

Write `src/asana_task_service/due_date.py`:

```python
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
SLA_MATRIX: dict[str, dict[str, "int | str"]] = {
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
```

- [ ] **Step 2: Smoke-import the module**

Run from the service folder:
```bash
cd src/asana_task_service && python -c "from due_date import SLA_MATRIX, DueDate, BUSINESS_TZ; print(len(SLA_MATRIX), BUSINESS_TZ)" && cd ../..
```
Expected: `11 America/Los_Angeles`

- [ ] **Step 3: Commit**

```bash
git add src/asana_task_service/due_date.py
git commit -m "feat(asana): scaffold due_date module with config and SLA matrix"
```

---

## Task 3: TDD `_is_business_day` and `_roll_forward_to_business_day`

**Files:**
- Create: `src/asana_task_service/test_due_date.py`
- Modify: `src/asana_task_service/due_date.py`

- [ ] **Step 1: Write the failing tests**

Create `src/asana_task_service/test_due_date.py`:

```python
"""Unit tests for due_date.py. All tests inject `now`; no clock mocking."""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from due_date import (
    BUSINESS_TZ,
    _is_business_day,
    _roll_forward_to_business_day,
)


# Reference dates (2026):
#   2026-05-20 Wed (business)
#   2026-05-22 Fri (business)
#   2026-05-23 Sat
#   2026-05-24 Sun
#   2026-05-25 Mon — Memorial Day (US federal holiday)
#   2026-05-26 Tue (business)

class TestIsBusinessDay:
    def test_weekday_is_business(self):
        assert _is_business_day(date(2026, 5, 20)) is True

    def test_saturday_is_not_business(self):
        assert _is_business_day(date(2026, 5, 23)) is False

    def test_sunday_is_not_business(self):
        assert _is_business_day(date(2026, 5, 24)) is False

    def test_federal_holiday_is_not_business(self):
        # Memorial Day 2026
        assert _is_business_day(date(2026, 5, 25)) is False


class TestRollForwardToBusinessDay:
    def test_business_day_unchanged(self):
        assert _roll_forward_to_business_day(date(2026, 5, 20)) == date(2026, 5, 20)

    def test_saturday_rolls_to_monday(self):
        # Sat 2026-05-16 -> Mon 2026-05-18 (no holiday that weekend)
        assert _roll_forward_to_business_day(date(2026, 5, 16)) == date(2026, 5, 18)

    def test_holiday_rolls_to_next_business(self):
        # Memorial Day Mon -> Tue
        assert _roll_forward_to_business_day(date(2026, 5, 25)) == date(2026, 5, 26)

    def test_sat_before_holiday_monday_rolls_through(self):
        # Sat 2026-05-23 -> Sun (skip) -> Mon (holiday, skip) -> Tue 2026-05-26
        assert _roll_forward_to_business_day(date(2026, 5, 23)) == date(2026, 5, 26)
```

- [ ] **Step 2: Run tests, verify they fail**

Run from repo root:
```bash
cd src/asana_task_service && pytest test_due_date.py -v && cd ../..
```
Expected: ImportError or collection failure (helpers don't exist yet).

- [ ] **Step 3: Implement the helpers in `due_date.py`**

Add to `src/asana_task_service/due_date.py` immediately after the `_US_HOLIDAYS` line:

```python
def _is_business_day(d: date) -> bool:
    return d.weekday() < 5 and d not in _US_HOLIDAYS


def _roll_forward_to_business_day(d: date) -> date:
    cursor = d
    while not _is_business_day(cursor):
        cursor += timedelta(days=1)
    return cursor
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
cd src/asana_task_service && pytest test_due_date.py -v && cd ../..
```
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asana_task_service/due_date.py src/asana_task_service/test_due_date.py
git commit -m "feat(asana): business-day predicate and roll-forward helper"
```

---

## Task 4: TDD `_advance_business_days`

**Files:**
- Modify: `src/asana_task_service/test_due_date.py`
- Modify: `src/asana_task_service/due_date.py`

- [ ] **Step 1: Add failing tests**

Append to `src/asana_task_service/test_due_date.py`:

```python
from due_date import _advance_business_days


class TestAdvanceBusinessDays:
    def test_wed_plus_one_is_thu(self):
        # 2026-05-20 Wed + 1 -> 2026-05-21 Thu
        assert _advance_business_days(date(2026, 5, 20), 1) == date(2026, 5, 21)

    def test_fri_plus_one_skips_weekend_to_mon(self):
        # 2026-05-15 Fri + 1 -> Sat (skip), Sun (skip), Mon 2026-05-18
        assert _advance_business_days(date(2026, 5, 15), 1) == date(2026, 5, 18)

    def test_fri_plus_one_skips_weekend_and_memorial_day(self):
        # 2026-05-22 Fri + 1 -> Sat, Sun, Mon (Memorial Day) -> Tue 2026-05-26
        assert _advance_business_days(date(2026, 5, 22), 1) == date(2026, 5, 26)

    def test_three_business_days_from_wed(self):
        # 2026-05-20 Wed + 3 -> Thu, Fri, Mon 2026-05-25 (Memorial Day, skip) -> Tue
        # Walk: Thu(1), Fri(2), Sat(skip), Sun(skip), Mon-Memorial(skip), Tue(3)
        assert _advance_business_days(date(2026, 5, 20), 3) == date(2026, 5, 26)

    def test_sat_start_plus_one_is_mon(self):
        # 2026-05-16 Sat + 1 -> Sun (skip), Mon 2026-05-18
        assert _advance_business_days(date(2026, 5, 16), 1) == date(2026, 5, 18)
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
cd src/asana_task_service && pytest test_due_date.py::TestAdvanceBusinessDays -v && cd ../..
```
Expected: ImportError on `_advance_business_days`.

- [ ] **Step 3: Implement `_advance_business_days`**

Add to `src/asana_task_service/due_date.py` after `_roll_forward_to_business_day`:

```python
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
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
cd src/asana_task_service && pytest test_due_date.py::TestAdvanceBusinessDays -v && cd ../..
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asana_task_service/due_date.py src/asana_task_service/test_due_date.py
git commit -m "feat(asana): advance_business_days walker"
```

---

## Task 5: TDD `_next_business_moment` and `_add_business_hours`

**Files:**
- Modify: `src/asana_task_service/test_due_date.py`
- Modify: `src/asana_task_service/due_date.py`

- [ ] **Step 1: Add failing tests**

Append to `src/asana_task_service/test_due_date.py`:

```python
from due_date import (
    _add_business_hours,
    _next_business_moment,
)


def _pt(year, month, day, hour=0, minute=0) -> datetime:
    """Build a tz-aware datetime in BUSINESS_TZ."""
    return datetime(year, month, day, hour, minute, tzinfo=BUSINESS_TZ)


class TestNextBusinessMoment:
    def test_inside_hours_unchanged(self):
        dt = _pt(2026, 5, 20, 10, 0)  # Wed 10am
        assert _next_business_moment(dt) == dt

    def test_before_hours_jumps_to_today_start(self):
        dt = _pt(2026, 5, 20, 7, 30)  # Wed 7:30am
        assert _next_business_moment(dt) == _pt(2026, 5, 20, 9, 0)

    def test_after_hours_jumps_to_next_business_start(self):
        dt = _pt(2026, 5, 20, 19, 0)  # Wed 7pm
        assert _next_business_moment(dt) == _pt(2026, 5, 21, 9, 0)

    def test_saturday_jumps_to_monday_start(self):
        dt = _pt(2026, 5, 16, 14, 0)  # Sat 2pm
        assert _next_business_moment(dt) == _pt(2026, 5, 18, 9, 0)

    def test_holiday_jumps_to_next_business_start(self):
        dt = _pt(2026, 5, 25, 10, 0)  # Memorial Day Mon 10am
        assert _next_business_moment(dt) == _pt(2026, 5, 26, 9, 0)

    def test_end_of_hours_is_outside(self):
        # 5pm exactly is NOT inside [9:00, 17:00)
        dt = _pt(2026, 5, 20, 17, 0)
        assert _next_business_moment(dt) == _pt(2026, 5, 21, 9, 0)


class TestAddBusinessHours:
    def test_4h_fits_within_day(self):
        # Wed 10am + 4h = Wed 2pm
        result = _add_business_hours(_pt(2026, 5, 20, 10, 0), 4)
        assert result == _pt(2026, 5, 20, 14, 0)

    def test_4h_crosses_into_next_day(self):
        # Wed 3pm + 4h: 2h today (5pm cap), 2h Thu morning -> Thu 11am
        result = _add_business_hours(_pt(2026, 5, 20, 15, 0), 4)
        assert result == _pt(2026, 5, 21, 11, 0)

    def test_4h_after_hours_starts_next_day(self):
        # Wed 8pm + 4h -> Thu 9am + 4h -> Thu 1pm
        result = _add_business_hours(_pt(2026, 5, 20, 20, 0), 4)
        assert result == _pt(2026, 5, 21, 13, 0)

    def test_4h_friday_afternoon_crosses_weekend(self):
        # Fri 3pm + 4h: 2h Fri (to 5pm), 2h Mon morning -> Mon 11am
        result = _add_business_hours(_pt(2026, 5, 15, 15, 0), 4)
        assert result == _pt(2026, 5, 18, 11, 0)

    def test_4h_friday_before_memorial_day(self):
        # Fri 2026-05-22 3pm + 4h: 2h Fri, skip Sat/Sun/Mon(holiday) -> Tue 11am
        result = _add_business_hours(_pt(2026, 5, 22, 15, 0), 4)
        assert result == _pt(2026, 5, 26, 11, 0)
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
cd src/asana_task_service && pytest test_due_date.py::TestNextBusinessMoment test_due_date.py::TestAddBusinessHours -v && cd ../..
```
Expected: ImportError.

- [ ] **Step 3: Implement helpers**

Add to `src/asana_task_service/due_date.py` after `_advance_business_days`:

```python
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
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
cd src/asana_task_service && pytest test_due_date.py::TestNextBusinessMoment test_due_date.py::TestAddBusinessHours -v && cd ../..
```
Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asana_task_service/due_date.py src/asana_task_service/test_due_date.py
git commit -m "feat(asana): business-hours arithmetic for critical urgency"
```

---

## Task 6: TDD `resolve_due_date` — client-supplied path

**Files:**
- Modify: `src/asana_task_service/test_due_date.py`
- Modify: `src/asana_task_service/due_date.py`

- [ ] **Step 1: Add failing tests**

Append to `src/asana_task_service/test_due_date.py`:

```python
from due_date import resolve_due_date


def _utc(year, month, day, hour=0, minute=0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


class TestResolveDueDateClientSupplied:
    def test_valid_business_day_unchanged(self):
        # client asks for Thu 2026-05-21; today is Wed 2026-05-20
        result = resolve_due_date(
            "software_issue", "high", "2026-05-21", now=_utc(2026, 5, 20, 18, 0)
        )
        assert result.due_on == "2026-05-21"
        assert result.due_at is None

    def test_saturday_rolls_to_monday(self):
        result = resolve_due_date(
            "software_issue", "high", "2026-05-16", now=_utc(2026, 5, 15, 18, 0)
        )
        assert result.due_on == "2026-05-18"

    def test_holiday_rolls_forward(self):
        # Memorial Day Mon 2026-05-25 -> Tue 2026-05-26
        result = resolve_due_date(
            "software_issue", "high", "2026-05-25", now=_utc(2026, 5, 22, 18, 0)
        )
        assert result.due_on == "2026-05-26"

    def test_past_date_rejected(self):
        # now = Wed 2026-05-20 18:00 UTC = Wed 11:00 PT. Client asks for Tue 5-19.
        with pytest.raises(ValueError, match="past"):
            resolve_due_date(
                "software_issue", "high", "2026-05-19", now=_utc(2026, 5, 20, 18, 0)
            )

    def test_malformed_rejected(self):
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            resolve_due_date(
                "software_issue", "high", "not-a-date", now=_utc(2026, 5, 20, 18, 0)
            )
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
cd src/asana_task_service && pytest test_due_date.py::TestResolveDueDateClientSupplied -v && cd ../..
```
Expected: failures with `NotImplementedError`.

- [ ] **Step 3: Implement the client-supplied branch**

Replace the `resolve_due_date` stub in `src/asana_task_service/due_date.py` with:

```python
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

    raise NotImplementedError("matrix path not yet implemented")
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
cd src/asana_task_service && pytest test_due_date.py::TestResolveDueDateClientSupplied -v && cd ../..
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/asana_task_service/due_date.py src/asana_task_service/test_due_date.py
git commit -m "feat(asana): resolve_due_date handles client-supplied dates with rollforward"
```

---

## Task 7: TDD `resolve_due_date` — SLA matrix fallback

**Files:**
- Modify: `src/asana_task_service/test_due_date.py`
- Modify: `src/asana_task_service/due_date.py`

- [ ] **Step 1: Add failing tests**

Append to `src/asana_task_service/test_due_date.py`:

```python
class TestResolveDueDateFallback:
    def test_business_day_count_due_on(self):
        # software_issue/high = 1 business day. Wed 2026-05-20 10am PT -> Thu 5-21
        # Wed 17:00 UTC = Wed 10:00 PT
        result = resolve_due_date(
            "software_issue", "high", None, now=_utc(2026, 5, 20, 17, 0)
        )
        assert result.due_on == "2026-05-21"
        assert result.due_at is None

    def test_business_day_count_skips_weekend(self):
        # software_issue/high = 1 BD. Fri 2026-05-15 10am PT -> Mon 5-18
        result = resolve_due_date(
            "software_issue", "high", None, now=_utc(2026, 5, 15, 17, 0)
        )
        assert result.due_on == "2026-05-18"

    def test_business_day_count_skips_holiday(self):
        # software_issue/high = 1 BD. Fri 2026-05-22 10am PT -> Tue 5-26
        # (Sat, Sun, Mon=Memorial Day skipped)
        result = resolve_due_date(
            "software_issue", "high", None, now=_utc(2026, 5, 22, 17, 0)
        )
        assert result.due_on == "2026-05-26"

    def test_critical_emits_due_at(self):
        # critical = 4 business hours. Wed 2026-05-20 10am PT -> Wed 2pm PT
        # Wed 10am PT = Wed 17:00 UTC. Wed 2pm PT = Wed 21:00 UTC.
        result = resolve_due_date(
            "software_issue", "critical", None, now=_utc(2026, 5, 20, 17, 0)
        )
        assert result.due_on is None
        # ISO8601 UTC, ends in +00:00 or Z
        assert result.due_at is not None
        assert result.due_at.startswith("2026-05-20T21:00:00")

    def test_critical_after_hours_rolls_to_next_business(self):
        # Wed 2026-05-20 9pm PT = Thu 2026-05-21 04:00 UTC.
        # Outside hours -> Thu 9am PT + 4h = Thu 1pm PT = Thu 20:00 UTC.
        result = resolve_due_date(
            "software_issue", "critical", None, now=_utc(2026, 5, 21, 4, 0)
        )
        assert result.due_at is not None
        assert result.due_at.startswith("2026-05-21T20:00:00")

    def test_late_friday_pt_critical_lands_monday(self):
        # Fri 2026-05-15 11pm PT = Sat 2026-05-16 06:00 UTC.
        # Outside hours, Sat is weekend -> Mon 9am PT + 4h = Mon 1pm PT = Mon 20:00 UTC.
        result = resolve_due_date(
            "software_issue", "critical", None, now=_utc(2026, 5, 16, 6, 0)
        )
        assert result.due_at is not None
        assert result.due_at.startswith("2026-05-18T20:00:00")

    def test_timezone_anchoring_late_pt_does_not_advance_date(self):
        # Wed 2026-05-20 11pm PT = Thu 2026-05-21 06:00 UTC.
        # Filed late Wed PT; software_issue/high (1 BD) -> Thu 5-21 (next BD from Wed),
        # NOT Fri 5-22 (which would be the answer if naively using UTC date Thu).
        result = resolve_due_date(
            "software_issue", "high", None, now=_utc(2026, 5, 21, 6, 0)
        )
        assert result.due_on == "2026-05-21"
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
cd src/asana_task_service && pytest test_due_date.py::TestResolveDueDateFallback -v && cd ../..
```
Expected: failures with `NotImplementedError`.

- [ ] **Step 3: Implement the matrix branch**

In `src/asana_task_service/due_date.py`, replace the trailing `raise NotImplementedError("matrix path not yet implemented")` line at the end of `resolve_due_date` with:

```python
    sla = SLA_MATRIX[intent][urgency]
    if sla == "4h":
        deadline_local = _add_business_hours(now_local, 4)
        deadline_utc = deadline_local.astimezone(timezone.utc)
        return DueDate(due_at=deadline_utc.strftime("%Y-%m-%dT%H:%M:%S+00:00"))
    assert isinstance(sla, int)
    target = _advance_business_days(now_local.date(), sla)
    return DueDate(due_on=target.isoformat())
```

- [ ] **Step 4: Run tests, verify they pass**

```bash
cd src/asana_task_service && pytest test_due_date.py::TestResolveDueDateFallback -v && cd ../..
```
Expected: 7 passed.

- [ ] **Step 5: Run the full module suite**

```bash
cd src/asana_task_service && pytest test_due_date.py -v && cd ../..
```
Expected: all tests pass (36 total so far: 8 + 5 + 11 + 5 + 7).

- [ ] **Step 6: Commit**

```bash
git add src/asana_task_service/due_date.py src/asana_task_service/test_due_date.py
git commit -m "feat(asana): SLA-matrix fallback path emits due_on or due_at"
```

---

## Task 8: TDD matrix coverage (parametrized)

**Files:**
- Modify: `src/asana_task_service/test_due_date.py`

- [ ] **Step 1: Add parametrized matrix-coverage test**

Append to `src/asana_task_service/test_due_date.py`:

```python
from due_date import SLA_MATRIX


@pytest.mark.parametrize("intent", list(SLA_MATRIX.keys()))
@pytest.mark.parametrize("urgency", ["critical", "high", "medium", "low"])
def test_matrix_emits_correct_field_type(intent, urgency):
    """Critical → due_at; everything else → due_on. Every cell."""
    result = resolve_due_date(intent, urgency, None, now=_utc(2026, 5, 20, 17, 0))
    if urgency == "critical":
        assert result.due_at is not None, f"{intent}/{urgency} expected due_at"
        assert result.due_on is None
    else:
        assert result.due_on is not None, f"{intent}/{urgency} expected due_on"
        assert result.due_at is None
```

- [ ] **Step 2: Run, verify all 44 cells pass**

```bash
cd src/asana_task_service && pytest test_due_date.py::test_matrix_emits_correct_field_type -v && cd ../..
```
Expected: 44 passed (11 intents × 4 urgencies).

- [ ] **Step 3: Commit**

```bash
git add src/asana_task_service/test_due_date.py
git commit -m "test(asana): parametrized coverage over all 44 SLA-matrix cells"
```

---

## Task 9: Wire `resolve_due_date` into `main.py`

**Files:**
- Modify: `src/asana_task_service/main.py`

- [ ] **Step 1: Import the new module**

Edit `src/asana_task_service/main.py`. At the top of the file, after the existing `from datetime import datetime, timedelta` line near line 11, change it to:

```python
from datetime import datetime, timedelta, timezone
```

Then, immediately after the existing `from pydantic import ...` line near line 28, add:

```python
from due_date import resolve_due_date
```

(Top-level import, matching how the service is launched: `uvicorn main:app` from the `src/asana_task_service/` working directory.)

- [ ] **Step 2: Delete the obsolete helper**

Remove the entire `_get_due_date_from_urgency` function from `src/asana_task_service/main.py` (currently lines 241-252):

```python
def _get_due_date_from_urgency(urgency: str) -> Optional[str]:
    urgency_days = {
        "critical": 0,
        "high": 1,
        "medium": 3,
        "low": 7,
    }
    days = urgency_days.get(urgency.lower())
    if days is not None:
        due = datetime.utcnow() + timedelta(days=days)
        return due.strftime("%Y-%m-%d")
    return None
```

- [ ] **Step 3: Replace the due-date block in `create_task`**

In `src/asana_task_service/main.py`, find the block at lines 302-304:

```python
    due_date = task.due_date or _get_due_date_from_urgency(task.urgency)
    if due_date:
        asana_task["data"]["due_on"] = due_date
```

Replace it with:

```python
    try:
        resolved = resolve_due_date(task.intent, task.urgency, task.due_date)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    if resolved.due_on:
        asana_task["data"]["due_on"] = resolved.due_on
    elif resolved.due_at:
        asana_task["data"]["due_at"] = resolved.due_at
```

- [ ] **Step 4: Remove the now-unused `timedelta` import if not used elsewhere**

Search `src/asana_task_service/main.py` for `timedelta`. If it appears only in the import line, edit:

```python
from datetime import datetime, timedelta, timezone
```

to:

```python
from datetime import datetime, timezone
```

(If `timedelta` is referenced elsewhere, leave it.)

- [ ] **Step 5: Smoke-import the service**

Run:
```bash
python -c "import sys; sys.path.insert(0, 'src/asana_task_service'); import main; print('ok')"
```
Expected: `ok`.

- [ ] **Step 6: Commit**

```bash
git add src/asana_task_service/main.py
git commit -m "feat(asana): wire resolve_due_date into create_task endpoint"
```

---

## Task 10: Replace `datetime.utcnow()` with `datetime.now(timezone.utc)`

**Files:**
- Modify: `src/asana_task_service/main.py`

- [ ] **Step 1: Find all utcnow() calls**

Run:
```bash
grep -n "utcnow" src/asana_task_service/main.py
```
Expected: 3 lines matching (in `_format_task_notes`, `health_check`, and `create_task` response).

- [ ] **Step 2: Replace each occurrence**

In `src/asana_task_service/main.py`, change every `datetime.utcnow()` to `datetime.now(timezone.utc)`.

The output format `.isoformat() + "Z"` should become `.isoformat().replace("+00:00", "Z")` — `datetime.now(timezone.utc).isoformat()` produces `2026-05-13T18:00:00+00:00`, not the previous unsuffixed format. Replace each pattern:

| Old | New |
|---|---|
| `datetime.utcnow().isoformat() + "Z"` | `datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")` |
| `datetime.utcnow().isoformat()` (no Z) | `datetime.now(timezone.utc).isoformat().replace("+00:00", "")` if a bare ISO string is needed, otherwise keep the `+00:00`. Inspect the call site to decide. |

The `Created:` line in `_format_task_notes` uses `f"- **Created:** {datetime.utcnow().isoformat()}Z"` — change to `f"- **Created:** {datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}"`.

- [ ] **Step 3: Verify no `utcnow` remains**

Run:
```bash
grep -n "utcnow" src/asana_task_service/main.py
```
Expected: no matches.

- [ ] **Step 4: Smoke-import**

```bash
python -c "import sys; sys.path.insert(0, 'src/asana_task_service'); import main; print('ok')"
```
Expected: `ok`.

- [ ] **Step 5: Commit**

```bash
git add src/asana_task_service/main.py
git commit -m "fix(asana): replace deprecated datetime.utcnow() with datetime.now(timezone.utc)"
```

---

## Task 11: Manual end-to-end smoke (local, no real Asana call)

**Files:** none modified

This task verifies the wiring is correct without hitting the real Asana API. We exercise the FastAPI app via TestClient and intercept the outbound httpx call.

- [ ] **Step 1: Create a one-off smoke script**

Create a scratch file `scratch_smoke.py` at the repo root:

```python
import sys
sys.path.insert(0, "src/asana_task_service")
import os
os.environ.setdefault("ASANA_TOKEN", "fake")
os.environ.setdefault("ASANA_PROJECT_ID", "999")
os.environ.setdefault("SERVICE_API_KEY", "test-key")
os.environ.setdefault("APP_ENV", "development")

import httpx
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

import main

captured = {}

class FakeResponse:
    status_code = 201
    text = ""
    def raise_for_status(self): pass
    def json(self): return {"data": {"gid": "12345"}}

async def fake_post(self, url, **kwargs):
    captured["payload"] = kwargs.get("json")
    return FakeResponse()

async def fake_get(self, url, **kwargs):
    return FakeResponse()

with patch.object(httpx.AsyncClient, "post", new=fake_post), \
     patch.object(httpx.AsyncClient, "get", new=fake_get):
    client = TestClient(main.app)
    r = client.post(
        "/tasks",
        headers={"X-API-Key": "test-key"},
        json={
            "title": "Smoke test critical",
            "intent": "software_issue",
            "urgency": "critical",
        },
    )
    print("Status:", r.status_code)
    print("Payload sent to Asana:", captured["payload"])
```

- [ ] **Step 2: Run the smoke**

```bash
python scratch_smoke.py
```
Expected: prints `Status: 201` and a payload containing a `"due_at"` key (no `"due_on"`), formatted as ISO8601 UTC.

- [ ] **Step 3: Re-run with urgency=medium**

Edit the JSON body in `scratch_smoke.py` to use `"urgency": "medium"`. Re-run:
```bash
python scratch_smoke.py
```
Expected: payload contains `"due_on"` (date string), no `"due_at"`.

- [ ] **Step 4: Delete the scratch file**

```bash
rm scratch_smoke.py
```

- [ ] **Step 5: No commit** — the scratch file should not be committed.

---

## Task 12: Update README

**Files:**
- Modify: `src/asana_task_service/README.md`

- [ ] **Step 1: Replace the Features bullet**

In `src/asana_task_service/README.md` find this bullet around line 159:

```
- ✅ Urgency-based due date calculation (critical=same day, high=next day, etc.)
```

Replace with:

```
- ✅ Intent × urgency SLA model with business-day + US holiday awareness (critical → +4 business hours via `due_at`; lower urgencies → N business days via `due_on`)
```

- [ ] **Step 2: Add a "Due-date logic" section**

In the same README, immediately after the "Features" section and before "Docker Deployment", insert:

```markdown
## Due-date logic

Due dates are computed by [`due_date.py`](due_date.py).

- All math runs in `BUSINESS_TIMEZONE` (default `America/Los_Angeles`).
- Business days skip Saturday, Sunday, and US federal holidays (via the `holidays` package).
- `critical` urgency emits Asana's `due_at` field with a deadline `+4 business hours` from the request, clipped to `[BUSINESS_HOURS_START, BUSINESS_HOURS_END)`.
- All other urgencies emit Asana's `due_on` with a date computed from the per-intent SLA matrix (see `SLA_MATRIX` in [`due_date.py`](due_date.py)).
- If the client supplies an explicit `due_date`, past dates return HTTP 400, and weekends/holidays are rolled forward to the next business day.

To tune SLAs, edit the `SLA_MATRIX` constant. To change the business calendar window, edit the env vars in `.env`.
```

- [ ] **Step 3: Commit**

```bash
git add src/asana_task_service/README.md
git commit -m "docs(asana): document new due-date logic and SLA matrix"
```

---

## Task 13: Final test sweep

**Files:** none modified

- [ ] **Step 1: Run the full test suite**

```bash
cd src/asana_task_service && pytest test_due_date.py -v && cd ../..
```
Expected: all tests pass (~80 total: 8 + 5 + 11 + 5 + 7 + 44 — adjust if your count differs).

- [ ] **Step 2: Confirm no deprecated calls remain**

```bash
grep -rn "utcnow" src/asana_task_service/
```
Expected: no matches.

- [ ] **Step 3: Confirm no `_get_due_date_from_urgency` references remain**

```bash
grep -rn "_get_due_date_from_urgency" src/asana_task_service/
```
Expected: no matches.

- [ ] **Step 4: Final commit if anything dangling**

If `git status` shows clean, you're done. If not, address whatever's left, then commit.

---

## Done criteria

- All 13 tasks committed.
- `cd src/asana_task_service && pytest test_due_date.py` is green.
- `grep utcnow src/asana_task_service/` is empty.
- Service still starts: `uvicorn main:app` from `src/asana_task_service/`.
- Smoke script in Task 11 produced correct `due_at` (critical) and `due_on` (medium) payloads.
