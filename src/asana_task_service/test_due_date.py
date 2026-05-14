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
