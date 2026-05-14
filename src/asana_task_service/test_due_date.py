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
