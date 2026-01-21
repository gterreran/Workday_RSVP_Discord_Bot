from __future__ import annotations

from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo


def next_saturday(today: date) -> date:
    # Saturday is 5 (Mon=0 ... Sun=6)
    days_ahead = (5 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def default_deadline_for(workday: date) -> datetime:
    # Default: Friday 18:00 local time (the day before Saturday)
    deadline_day = workday - timedelta(days=1)
    return datetime.combine(deadline_day, time(hour=18, minute=0))


def discord_ts(dt: datetime) -> str:
    # Discord timestamp markup: <t:unix:f>
    return f"<t:{int(dt.timestamp())}:f>"
