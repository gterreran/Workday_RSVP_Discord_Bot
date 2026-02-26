# src/rsvp_bot/commands/reports.py

"""
Report commands
===============

This module implements admin-only reporting/inspection commands that summarize
RSVP state for a channel.

The primary report is :func:`summary_cmd`, which generates a human-readable
attendance breakdown (including notes and partner selections) for the upcoming
workday. Long output is split into multiple messages via
:func:`build_summary_chunks`.

Functions
---------
:func:`build_summary_chunks`
    Format a full RSVP summary into Discord-safe message chunks.
:func:`summary_cmd`
    Command handler for ``/summary``.
:func:`register_report_commands`
    Register report/inspection commands on a bot instance.
"""

from __future__ import annotations

import discord

from .checks import in_guild_text_channel, is_admin
from .ctx import get_ctx


def build_summary_chunks(
    *,
    channel_id: int,
    workday_date: str,
    directory: list[int],
    rsvps_with_notes: list[tuple[int, str, str | None]],
    partners_map: dict[int, list[int]],
    limit: int = 1800,
) -> list[str]:
    """
    Build a full RSVP summary and split it into Discord-safe chunks.

    The summary is restricted to users present in ``directory`` and grouped into
    five categories:

    - attending (in person)
    - attending (remote)
    - maybe
    - not attending
    - missing

    Each chunk is capped by ``limit`` to ensure the message stays comfortably
    below Discord's 2000-character hard limit.

    Parameters
    ----------
    channel_id : :class:`int`
        Discord channel ID where the RSVP panel lives.
    workday_date : :class:`str`
        Workday date in ISO format (``YYYY-MM-DD``).
    directory : :class:`list` of :class:`int`
        User IDs considered "expected" for this channel/workday.
    rsvps_with_notes : :class:`list` of :class:`tuple` (:class:`int`, :class:`str`, :class:`str` | :class:`None`)
        RSVP rows of the form ``(user_id, status, note)`` for the given workday.
    partners_map : :class:`dict` of :class:`int` to :class:`list` of :class:`int`
        Mapping ``user_id -> partner_ids`` for the given workday. Partner IDs are
        shown only for attending statuses.
    limit : :class:`int`, optional
        Maximum characters per chunk. Defaults to ``1800`` for safety.

    Returns
    -------
    :class:`list` of :class:`str`
        One or more message chunks containing the formatted summary.

    Notes
    -----
    Notes are normalized to a single line (collapsed whitespace) to keep the
    report compact.
    """
    by_user: dict[int, tuple[str, str | None]] = {
        int(uid): (status, note) for uid, status, note in rsvps_with_notes
    }

    groups: dict[str, list[int]] = {"yes": [], "remote": [], "maybe": [], "no": [], "missing": []}
    for uid in sorted(set(int(x) for x in directory)):
        if uid not in by_user:
            groups["missing"].append(uid)
            continue
        status, _ = by_user[uid]
        groups.get(status, groups["missing"]).append(uid)

    def _one_line(text: str) -> str:
        return " ".join((text or "").split()).strip()

    def fmt_user(uid: int, *, include_note: bool, include_partners: bool) -> str:
        mention = f"<@{uid}>"
        status, note = by_user.get(uid, ("", None))

        parts: list[str] = [f"- {mention}"]
        if include_note and note:
            parts.append(f"— {_one_line(note)}")

        if include_partners and status in ("yes", "remote"):
            p = partners_map.get(uid, [])
            if p:
                parts.append("— partners: " + " ".join(f"<@{pid}>" for pid in p))

        return " ".join(parts)

    blocks: list[str] = []
    blocks.append(f"**RSVP Summary — {workday_date}** (channel <#{channel_id}>)\n")

    def section(title: str, ids: list[int], *, show_notes: bool, show_partners: bool) -> None:
        blocks.append(f"__{title}__ (**{len(ids)}**)")
        if not ids:
            blocks.append("_None_")
            blocks.append("")
            return
        for uid in ids:
            blocks.append(fmt_user(uid, include_note=show_notes, include_partners=show_partners))
        blocks.append("")

    section("✅ Attending (In person)", groups["yes"], show_notes=True, show_partners=True)
    section("🎥 Attending (Remote)", groups["remote"], show_notes=True, show_partners=True)
    section("❔ Maybe", groups["maybe"], show_notes=False, show_partners=False)
    section("❌ Not attending", groups["no"], show_notes=False, show_partners=False)
    section("⌛ Missing", groups["missing"], show_notes=False, show_partners=False)

    text = "\n".join(blocks).strip()

    chunks: list[str] = []
    cur = ""
    for line in text.splitlines(True):
        if len(cur) + len(line) > limit:
            chunks.append(cur)
            cur = ""
        cur += line
    if cur:
        chunks.append(cur)
    return chunks


async def summary_cmd(bot, interaction: discord.Interaction) -> None:
    """
    Generate and send a full RSVP report for the upcoming workday.

    The report is limited to directory members for the channel and includes:

    - RSVP status
    - per-user note/plan (if provided)
    - selected work partners (for attending statuses)
    - missing users

    Output is sent ephemerally and split across multiple messages if needed.

    Parameters
    ----------
    bot : :class:`discord.Client`
        Bot instance providing access to the database layer (``bot.db``).
    interaction : :class:`discord.Interaction`
        The Discord interaction for this slash command invocation.

    Returns
    -------
    :class:`None`

    Raises
    ------
    AssertionError
        If :func:`~rsvp_bot.commands.ctx.get_ctx` is invoked outside a guild text channel.
    :class:`discord.HTTPException`
        If Discord API calls fail when sending follow-up messages.
    """
    ctx = await get_ctx(interaction)

    workday_date = await bot.db.get_workday_date(guild_id=ctx.guild_id, channel_id=ctx.channel_id)

    directory = await bot.db.directory_list_active(guild_id=ctx.guild_id, channel_id=ctx.channel_id)
    if not directory:
        await interaction.followup.send("Directory is empty for this channel.", ephemeral=True)
        return

    rsvps = await bot.db.list_rsvps_with_notes(
        guild_id=ctx.guild_id,
        channel_id=ctx.channel_id,
        workday_date=workday_date,
    )

    partners_map = await bot.db.list_work_partners_map(
        guild_id=ctx.guild_id,
        channel_id=ctx.channel_id,
        workday_date=workday_date,
    )

    chunks = build_summary_chunks(
        channel_id=ctx.channel_id,
        workday_date=workday_date,
        directory=directory,
        rsvps_with_notes=rsvps,
        partners_map=partners_map,
    )

    await interaction.followup.send(chunks[0], ephemeral=True)
    for c in chunks[1:]:
        await interaction.followup.send(c, ephemeral=True)


def register_report_commands(bot) -> None:
    """
    Register report/inspection commands on a bot instance.

    This module currently registers:

    - ``/summary`` (admin-only)

    Parameters
    ----------
    bot : :class:`discord.Client`
        The bot instance that owns the :class:`discord.app_commands.CommandTree`.

    Returns
    -------
    :class:`None`
    """
    bot.tree.command(
        name="summary",
        description="Show RSVP status (notes + partners) for everyone in the directory (admin only).",
    )(
        in_guild_text_channel()(
            is_admin()(
                lambda interaction: summary_cmd(bot, interaction)
            )
        )
    )


__all__ = [
    "build_summary_chunks",
    "summary_cmd",
    "register_report_commands",
]
