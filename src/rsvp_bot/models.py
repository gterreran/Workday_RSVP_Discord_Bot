"""
Data models and callback types
==============================

Lightweight, shared data structures used across the RSVP bot.

This module defines small immutable dataclasses that represent commonly passed
objects (such as RSVP summaries and persisted workday state), along with
callable type aliases used by the Discord UI layer in :mod:`rsvp_bot.views`.

Classes
-------

:class:`~rsvp_bot.models.Summary`
    Grouped RSVP status lists for a single workday cycle.

:class:`~rsvp_bot.models.WorkdayRow`
    Minimal persisted workday state for a configured channel.

Constants
---------

OnChoice : :class:`typing.Callable`
    Callback signature used by :class:`~rsvp_bot.views.RSVPView` for immediate
    RSVP updates.

OnChoiceWithPlan : :class:`typing.Callable`
    Callback signature used by :class:`~rsvp_bot.views.RSVPView` for RSVP flows
    that may request additional plan input.

OnSubmitPlan : :class:`typing.Callable`
    Callback signature used by :class:`~rsvp_bot.views.RSVPPlanModal` when a plan
    modal is submitted.

OnSubmitPartners : :class:`typing.Callable`
    Callback signature used by :class:`~rsvp_bot.views.PartnerSelectView` when a
    partner selection is submitted.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

import discord


@dataclass(frozen=True)
class Summary:
    """
    Aggregated RSVP status for a single workday cycle.

    Instances of this class are typically produced by
    :func:`~rsvp_bot.summary.build_summary` and then consumed by
    :func:`~rsvp_bot.embeds.build_embed` and report commands.

    .. rubric:: Attributes

    yes : :class:`list` [:class:`int`]
        User IDs marked as attending in person.
    remote : :class:`list` [:class:`int`]
        User IDs marked as attending remotely.
    maybe : :class:`list` [:class:`int`]
        User IDs marked as maybe attending.
    no : :class:`list` [:class:`int`]
        User IDs marked as not attending.
    missing : :class:`list` [:class:`int`]
        User IDs in the directory who have not submitted an RSVP.
    """

    yes: list[int]
    remote: list[int]
    maybe: list[int]
    no: list[int]
    missing: list[int]


@dataclass(frozen=True)
class WorkdayRow:
    """
    Persisted workday state for a configured channel.

    This model represents the minimal set of fields used to identify the current
    workday cycle and its associated panel message.

    .. rubric:: Attributes

    guild_id : :class:`int`
        Discord guild ID.
    channel_id : :class:`int`
        Discord text channel ID where the panel is posted.
    workday_date : :class:`str`
        Workday date in ISO format (``YYYY-MM-DD``).
    deadline_ts : :class:`int`
        RSVP deadline as a UTC epoch timestamp (POSIX seconds).
    rsvp_message_id : :class:`int`
        Discord message ID of the persistent RSVP panel.
    """

    guild_id: int
    channel_id: int
    workday_date: str
    deadline_ts: int
    rsvp_message_id: int


# Callbacks used by views
OnChoice = Callable[[discord.Interaction, str, str | None], Awaitable[None]]
OnChoiceWithPlan = Callable[[discord.Interaction, str], Awaitable[None]]
OnSubmitPlan = Callable[[discord.Interaction, str, str | None], Awaitable[None]]
OnSubmitPartners = Callable[[discord.Interaction, list[int]], Awaitable[None]]
