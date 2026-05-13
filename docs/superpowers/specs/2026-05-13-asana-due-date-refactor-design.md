# Asana Task Service — Due-Date Logic Refactor

**Date:** 2026-05-13
**Scope:** `src/asana_task_service/`
**Status:** Approved, ready for implementation planning

## Goal

Replace the current ad-hoc due-date logic with a timezone-aware, business-calendar-aware, intent-sensitive computation. The current implementation uses naive UTC, calendar days (no weekend/holiday awareness), and ignores `intent` entirely.

## Problems being fixed

1. **UTC drift.** `datetime.utcnow()` produces dates that can disagree with Pacific local time by up to a calendar day near midnight.
2. **No business-day awareness.** A `high` urgency task filed Friday is due Saturday.
3. **No holiday awareness.** Tasks land on federal holidays.
4. **`intent` is ignored.** A `password_reset` and an `ai_initiatives` task with the same urgency get the same SLA.
5. **No datetime precision.** `critical` tasks get "due today" with no hour-level deadline.
6. **Past-date acceptance.** Client-supplied `due_date: "2020-01-01"` is sent to Asana unchanged.
7. **Deprecated API.** `datetime.utcnow()` is deprecated as of Python 3.12.

## Configuration

Three new env vars (all optional, defaults shown):

```
BUSINESS_TIMEZONE=America/Los_Angeles
BUSINESS_HOURS_START=09:00
BUSINESS_HOURS_END=17:00
```

Holidays come from the `holidays` Python package, country=`US` (auto-updated yearly via package version). New dependency added to `requirements.txt`.

## SLA matrix

A single module-level constant `SLA_MATRIX: dict[str, dict[str, int | str]]` in `due_date.py`. The string `"4h"` is a sentinel meaning "+4 business hours, datetime precision"; integers are business-day counts.

| Intent | Critical | High | Medium | Low |
|---|---|---|---|---|
| `password_reset` | `"4h"` | 1 | 1 | 1 |
| `software_issue` | `"4h"` | 1 | 3 | 5 |
| `hardware_issue` | `"4h"` | 1 | 3 | 5 |
| `access_request` | `"4h"` | 1 | 2 | 3 |
| `general_support` | `"4h"` | 1 | 3 | 5 |
| `other` | `"4h"` | 2 | 5 | 7 |
| `data_engineering` | `"4h"` | 2 | 5 | 10 |
| `business_reports` | `"4h"` | 2 | 5 | 10 |
| `business_intelligence` | `"4h"` | 3 | 7 | 14 |
| `ai_initiatives` | `"4h"` | 3 | 7 | 14 |
| `general_inquiry` | `"4h"` | 2 | 5 | 7 |

These are starting values, tunable by editing the constant.

## Module structure

```
src/asana_task_service/
├── main.py             # FastAPI endpoints — slimmer, delegates due-date math
├── due_date.py         # NEW — all due-date computation
├── test_due_date.py    # NEW — pytest unit tests
├── requirements.txt    # + holidays
├── .env.example        # + 3 new env vars
└── README.md           # updated "Features" + new "Due-date logic" section
```

## Public API

```python
# due_date.py

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass(frozen=True)
class DueDate:
    """Mutually exclusive: exactly one of due_on/due_at is set."""
    due_on: Optional[str] = None   # YYYY-MM-DD for Asana's `due_on`
    due_at: Optional[str] = None   # ISO8601 with offset for Asana's `due_at`

def resolve_due_date(
    intent: str,
    urgency: str,
    client_supplied: Optional[str],
    now: Optional[datetime] = None,
) -> DueDate:
    """
    Compute the Asana due-date for a task.

    Raises:
        ValueError: if client_supplied is malformed or in the past.
    """
```

`now` is injectable so tests pass deterministic timestamps.

## Algorithm

### Step 1 — Anchor "now" in business timezone

```
now_local = (now or datetime.now(UTC)).astimezone(BUSINESS_TZ)
```

All subsequent date/time math happens in local time. Conversion back to UTC happens only at the boundary when emitting `due_at`.

### Step 2 — Branch on client_supplied

**If client supplied a date string:**

1. Parse `YYYY-MM-DD`. Malformed → `ValueError("due_date must be YYYY-MM-DD")`.
2. If parsed date `< now_local.date()` → `ValueError("due_date is in the past")`.
3. While the date is Saturday, Sunday, or in the US holiday calendar: advance one day.
4. Return `DueDate(due_on=rolled.isoformat())`.

**If client did NOT supply:**

1. Look up `SLA_MATRIX[intent][urgency]`. (KeyError is impossible — Pydantic Literal types already validate both fields at the request boundary.)
2. If value is `"4h"`: compute "+4 business hours" (Step 3), return `DueDate(due_at=...)`.
3. If value is an int `N`: start from `now_local.date()`, advance `N` business days (skip Sat/Sun + US holidays), return `DueDate(due_on=...)`.

### Step 3 — "+4 business hours" math

Business hours are the half-open interval `[BUSINESS_HOURS_START, BUSINESS_HOURS_END)` on business days (Mon–Fri, non-holiday).

Algorithm:
1. If `now_local` is outside business hours OR on a non-business day, fast-forward to the next business day's `BUSINESS_HOURS_START`.
2. Loop: consume `min(4_remaining_hours, hours_left_in_today's_window)`. If hours remain, jump to next business day at `START`.
3. When 4 hours have been consumed, the cursor's local datetime is the deadline.
4. Convert to UTC, format as ISO8601 with `+00:00` offset for Asana's `due_at`.

### Step 4 — Endpoint wiring (`main.py`)

Replace the existing block:

```python
due_date = task.due_date or _get_due_date_from_urgency(task.urgency)
if due_date:
    asana_task["data"]["due_on"] = due_date
```

With:

```python
try:
    resolved = resolve_due_date(task.intent, task.urgency, task.due_date)
except ValueError as e:
    raise HTTPException(status_code=400, detail=str(e))

if resolved.due_on:
    asana_task["data"]["due_on"] = resolved.due_on
elif resolved.due_at:
    asana_task["data"]["due_at"] = resolved.due_at
```

The Pydantic `validate_due_date` validator on `TaskRequest` stays (cheap format check at the boundary). The past-date check moves into `resolve_due_date` because it needs the timezone-aware `now`. The old `_get_due_date_from_urgency` helper is deleted.

### Step 5 — `datetime.utcnow()` sweep

Replace all 4 call sites in `main.py` with `datetime.now(timezone.utc)`:
- `_format_task_notes` — `Created:` line
- `health_check` — `timestamp`
- `create_task` — `created_at` in response

## Testing

`test_due_date.py` (pytest). All tests inject `now`; no clock mocking.

1. **Timezone correctness**
   - Friday 11pm Pacific, critical → Monday morning, not Saturday.
2. **Business-day counting**
   - `software_issue` / `high` (1 day) filed Friday → Monday.
   - Same intent/urgency filed Wednesday → Thursday.
3. **Holiday skipping**
   - `high` filed Wednesday before Thanksgiving → skips Thursday + Friday → Monday.
4. **4-hour math**
   - 10am → 2pm same day.
   - 3pm → 11am next business day (1h today + 3h tomorrow).
   - 8pm → 1pm next business day.
   - Friday 3pm → Monday 11am.
5. **Client-supplied dates**
   - Past date → `ValueError`.
   - Saturday → rolled to Monday.
   - Federal holiday → rolled to next business day.
   - Valid future business day → unchanged.
6. **Matrix coverage**
   - Parametrized over all 11 intents × 4 urgencies; asserts `due_at` set for critical, `due_on` set otherwise.

## Out of scope

- Per-request timezone override (`timezone` field in payload). Single business timezone is enough today.
- Custom (non-US-federal) holiday calendar. Add later if PEC observes different holidays.
- Configurable matrix via env or file. Constant-in-code is fine for now.
- Backfilling existing Asana tasks with new due dates.

## Dependencies added

```
holidays>=0.40
tzdata>=2024.1   # Windows-only at runtime, but cheap on Linux — keep it pinned
```

`zoneinfo` itself is stdlib in Python 3.9+. On Windows, `zoneinfo.ZoneInfo("America/Los_Angeles")` raises unless `tzdata` is installed (Windows has no system tzdata database). The service runs in Linux containers in production, but the dev shell here is Windows — adding `tzdata` keeps local dev working without a `try/except ZoneInfoNotFoundError` fallback.
