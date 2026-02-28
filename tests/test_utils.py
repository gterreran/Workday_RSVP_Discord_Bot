# tests/test_utils.py

"""
Tests for pure utility functions (date/time helpers).
"""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

from rsvp_bot.config import DEFAULT_WORKDAY_WEEKDAY, DEFAULT_WORKDAY_WEEKDAY_DEADLINE
from rsvp_bot.utils import default_deadline_for, next_workday


def test_next_workday_is_strictly_after_today():
    # DEFAULT_WORKDAY_WEEKDAY is Saturday (5). 2026-02-28 is a Saturday.
    today = date(2026, 2, 28)
    nxt = next_workday(today)
    assert nxt.weekday() == DEFAULT_WORKDAY_WEEKDAY
    assert (nxt - today).days == 7


def test_next_workday_from_other_day():
    # Friday -> next Saturday is +1 day
    today = date(2026, 2, 27)
    nxt = next_workday(today)
    assert nxt.weekday() == DEFAULT_WORKDAY_WEEKDAY
    assert (nxt - today).days == 1


def test_default_deadline_for_matches_config_hours_offset():
    tz = ZoneInfo("America/Chicago")
    wd = date(2026, 2, 28)

    ts = default_deadline_for(wd, tz=tz)

    # Convert back to local time for a simple hour check
    from datetime import datetime, timezone

    dt_local = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(tz)

    # Deadline is relative to workday midnight: DEFAULT_WORKDAY_WEEKDAY_DEADLINE hours.
    # With default -6, that's previous day at 18:00 local.
    assert dt_local.hour == (24 + DEFAULT_WORKDAY_WEEKDAY_DEADLINE) % 24
