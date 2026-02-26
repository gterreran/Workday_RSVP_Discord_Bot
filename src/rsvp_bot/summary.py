# src/rsvp_bot/summary.py

"""
RSVP summary utilities
======================

Helpers for constructing attendance summaries used by embeds, reports, and
panel refreshes.

This module contains logic for aggregating raw RSVP records into a structured
:class:`~rsvp_bot.models.Summary` object that groups users by attendance status
and identifies directory members who have not responded yet.

Functions
---------

:func:`build_summary`
    Aggregate directory membership and raw RSVP records into a
    :class:`~rsvp_bot.models.Summary` instance.
"""
from __future__ import annotations

from typing import Iterable

from .models import Summary


def build_summary(*, directory: Iterable[int], rsvps: list[tuple[int, str]]) -> Summary:
    """
    Build an RSVP summary for a workday.

    This function combines the channel directory with the list of RSVP records
    and groups users into attendance buckets:

    - attending (in person)
    - attending remotely
    - maybe
    - not attending
    - missing (in directory but no RSVP)

    Parameters
    ----------
    directory : :class:`collections.abc.Iterable` of :class:`int`
        Iterable of Discord user IDs representing the active directory for the
        channel.
    rsvps : :class:`list` of :class:`tuple` [:class:`int`, :class:`str`]
        Raw RSVP records as ``(user_id, status)`` tuples.

    Returns
    -------
    :class:`~rsvp_bot.models.Summary`
        Structured summary containing sorted user ID lists for each attendance
        category, including missing users.

    Notes
    -----
    - Unknown status strings are ignored rather than raising errors.
    - All returned user lists are sorted to ensure deterministic output for
      embeds and reports.
    """
    directory_set = set(int(x) for x in directory)

    buckets: dict[str, list[int]] = {"yes": [], "remote": [], "maybe": [], "no": []}
    responded: set[int] = set()

    for user_id, status in rsvps:
        uid = int(user_id)
        responded.add(uid)
        if status in buckets:
            buckets[status].append(uid)

    missing = sorted(directory_set - responded)

    return Summary(
        yes=sorted(buckets["yes"]),
        remote=sorted(buckets["remote"]),
        maybe=sorted(buckets["maybe"]),
        no=sorted(buckets["no"]),
        missing=missing,
    )
