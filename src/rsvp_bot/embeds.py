"""
Discord embed builders
======================

Utilities for constructing Discord embeds used by the RSVP panel.

This module converts structured attendance data into visual
:class:`discord.Embed` objects rendered in Discord messages.

Functions
---------

:func:`build_embed`
    Build the main RSVP panel embed for a workday.

Constants
---------

STATUS_EMOJI : :class:`dict` [:class:`str`, :class:`str`]
    Mapping of RSVP status keys to emoji used in panel field titles.
"""
from __future__ import annotations

import discord

from .models import Summary

STATUS_EMOJI = {"yes": "✅", "remote": "🎥", "maybe": "❔", "no": "❌"}


def _fmt_users(ids: list[int]) -> str:
    """
    Format a list of user IDs into a Discord mention string.

    Parameters
    ----------
    ids : :class:`list` [:class:`int`]
        User IDs to render as mentions.

    Returns
    -------
    :class:`str`
        A space-separated string of ``<@id>`` mentions, or an em dash if empty.
    """
    return "—" if not ids else " ".join(f"<@{i}>" for i in ids)


def build_embed(*, workday_date: str, deadline_ts: int, summary: Summary) -> discord.Embed:
    """
    Build the RSVP panel embed.

    This embed is used as the persistent panel displayed in RSVP channels.
    It shows grouped attendance counts and mentions for all directory members.

    Parameters
    ----------
    workday_date : :class:`str`
        Workday date in ISO format (``YYYY-MM-DD``).
    deadline_ts : :class:`int`
        RSVP deadline as a UTC epoch timestamp.
    summary : :class:`~rsvp_bot.models.Summary`
        Aggregated attendance summary.

    Returns
    -------
    :class:`discord.Embed`
        Fully constructed embed ready to be sent or edited into a panel message.
    """
    e = discord.Embed(
        title=f"Workday RSVP — {workday_date}",
        description=f"Deadline: <t:{int(deadline_ts)}:f>",
    )
    e.add_field(name=f"{STATUS_EMOJI['yes']} Attending ({len(summary.yes)})", value=_fmt_users(summary.yes), inline=False)
    e.add_field(
        name=f"{STATUS_EMOJI['remote']} Attending (Remote) ({len(summary.remote)})",
        value=_fmt_users(summary.remote),
        inline=False,
    )
    e.add_field(name=f"{STATUS_EMOJI['maybe']} Maybe ({len(summary.maybe)})", value=_fmt_users(summary.maybe), inline=False)
    e.add_field(name=f"{STATUS_EMOJI['no']} Not attending ({len(summary.no)})", value=_fmt_users(summary.no), inline=False)
    e.add_field(name=f"⏳ Missing ({len(summary.missing)})", value=_fmt_users(summary.missing), inline=False)
    e.set_footer(text="Click a button below to set/update your RSVP.")
    return e
