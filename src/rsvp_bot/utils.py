# src/rsvp_bot/utils.py

"""
Utilities
=========

Small, side-effect-free helpers used throughout the RSVP bot.

This module currently focuses on computing dates and timestamps for the bot's
weekly scheduling model (workday selection and RSVP deadlines). These functions
are deliberately kept independent of Discord and database logic so they can be
used consistently by both commands and services.

Functions
---------

:func:`next_workday`
    Compute the next workday date after a reference date using the configured
    workday weekday.

:func:`default_deadline_for`
    Compute the default RSVP deadline timestamp (UTC epoch seconds) for a given
    workday date in a specific timezone.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .config import DEFAULT_WORKDAY_WEEKDAY, DEFAULT_WORKDAY_WEEKDAY_DEADLINE


def next_workday(today: date) -> date:
    """
    Compute the next workday date after a reference date.

    The workday weekday is configured by
    :data:`~rsvp_bot.config.DEFAULT_WORKDAY_WEEKDAY` where ``0`` is Monday and
    ``6`` is Sunday.

    Parameters
    ----------
    today : :class:`datetime.date`
        Reference date used to compute the upcoming workday.

    Returns
    -------
    :class:`datetime.date`
        The next workday date strictly after ``today``.

    Notes
    -----
    If ``today`` already falls on the configured weekday, the returned date is
    **one week later** (i.e., "next Saturday" rather than "this Saturday").
    """
    days_ahead = (int(DEFAULT_WORKDAY_WEEKDAY) - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def default_deadline_for(workday: date, tz: ZoneInfo) -> int:
    """
    Compute the default RSVP deadline timestamp for a workday.

    The deadline is defined as an offset in hours relative to **midnight of the
    workday** in the local timezone:

    - A negative offset means "before the workday midnight" (i.e. on the previous day).
    - A non-negative offset means "after the workday midnight" (i.e. on the workday).

    The offset value is configured by
    :data:`~rsvp_bot.config.DEFAULT_WORKDAY_WEEKDAY_DEADLINE`.

    Parameters
    ----------
    workday : :class:`datetime.date`
        Workday date for the current RSVP cycle.
    tz : :class:`zoneinfo.ZoneInfo`
        Timezone used to interpret the local deadline.

    Returns
    -------
    :class:`int`
        Deadline timestamp as UTC epoch seconds (POSIX timestamp).

    Raises
    ------
    ValueError
        If ``tz`` is :class:`None`.

    Notes
    -----
    The returned value is a UTC timestamp, but it represents a specific *local*
    time in ``tz``. Discord timestamp rendering (``<t:...:f>``) will display it
    in each user's local timezone.
    """
    if tz is None:
        raise ValueError("tz must not be None.")

    offset_hours = int(DEFAULT_WORKDAY_WEEKDAY_DEADLINE)

    # Convert "hours relative to workday midnight" into an absolute local datetime.
    # Example: -6 => 18:00 on the previous day.
    if offset_hours < 0:
        deadline_day = workday - timedelta(days=1)
        deadline_hour = 24 + offset_hours  # offset_hours is negative
    else:
        deadline_day = workday
        deadline_hour = offset_hours

    deadline_local = datetime.combine(
        deadline_day,
        time(hour=int(deadline_hour), minute=0, tzinfo=tz),
    )
    return int(deadline_local.timestamp())
