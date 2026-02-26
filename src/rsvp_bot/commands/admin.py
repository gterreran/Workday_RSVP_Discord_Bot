# src/rsvp_bot/commands/admin.py

"""
Admin commands
==============

This module defines the core admin-only slash commands used to initialize and
maintain an RSVP panel in a channel.

These commands are the primary operational interface for moderators/admins:

- :func:`setup_cmd` creates (or resets) the persistent RSVP panel and registers
  the channel in the database with default scheduling values from
  :mod:`rsvp_bot.config`.
- :func:`attendance_reset_cmd` clears attendance state for the active workday
  (RSVPs, partner links, and sent reminder history) and refreshes the panel.
- :func:`rsvp_commands_cmd` prints a live command list as seen by Discord in the
  current guild.

Functions
---------
:func:`setup_cmd`
    Command handler for ``/setup``.
:func:`attendance_reset_cmd`
    Command handler for ``/attendance_reset``.
:func:`rsvp_commands_cmd`
    Command handler for ``/rsvp_commands``.
:func:`register_admin_commands`
    Register admin commands on a bot instance.
"""

from __future__ import annotations

import time
from datetime import datetime

import discord

from ..config import DEFAULT_OFFSETS_MIN, DEFAULT_ROLLOVER_TIME, DEFAULT_ROLLOVER_WEEKDAY
from ..utils import default_deadline_for, next_workday
from .checks import in_guild_text_channel, is_admin
from .ctx import get_ctx


async def setup_cmd(bot, interaction: discord.Interaction) -> None:
    """
    Create or reset the persistent RSVP panel in the current channel.

    This is the standard first-time setup action for a new channel. It:

    - computes the next workday date via :func:`~rsvp_bot.utils.next_workday`
    - computes a default deadline via :func:`~rsvp_bot.utils.default_deadline_for`
    - ensures the directory is non-empty (adds the invoking admin if needed)
    - creates a new panel message if none exists, otherwise refreshes it
    - registers the channel in the database via ``channels`` with default
      scheduling fields (reminders + rollover)
    - clears any sent reminder history for the (new) workday

    Parameters
    ----------
    bot : :class:`discord.Client`
        Bot instance providing services and database access (``bot.db``,
        ``bot.panel``, ``bot.rsvp``, ``bot.tz``).
    interaction : :class:`discord.Interaction`
        The Discord interaction for this command invocation.

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

    workday = next_workday(datetime.now(bot.tz).date())
    deadline_ts = default_deadline_for(workday, bot.tz)
    workday_date = workday.isoformat()

    directory = await bot.db.directory_list_active(guild_id=ctx.guild_id, channel_id=ctx.channel_id)
    if not directory:
        await bot.db.directory_add(
            guild_id=ctx.guild_id,
            channel_id=ctx.channel_id,
            user_id=interaction.user.id,
            added_by=interaction.user.id,
            added_at_ts=int(time.time()),
        )

    rsvp_message_id = await bot.db.get_rsvp_message_id(guild_id=ctx.guild_id, channel_id=ctx.channel_id)
    if rsvp_message_id is None:
        action = "created"
        rsvp_message_id = await bot.panel.create_new_panel(
            ctx=ctx,
            workday_date=workday_date,
            deadline_ts=deadline_ts,
            on_choice=bot.rsvp.on_choice,
            on_choice_with_plan=bot.rsvp.on_choice_with_plan,
        )
    else:
        action = "reset"
        await bot.panel.refresh_panel(
            ctx=ctx,
            workday_date=workday_date,
            on_choice=bot.rsvp.on_choice,
            on_choice_with_plan=bot.rsvp.on_choice_with_plan,
        )

    await bot.db.upsert_channel(
        guild_id=ctx.guild_id,
        channel_id=ctx.channel_id,
        reminder_offsets=DEFAULT_OFFSETS_MIN,
        workday_date=workday_date,
        deadline_ts=deadline_ts,
        rsvp_message_id=rsvp_message_id,
        rollover_weekday=DEFAULT_ROLLOVER_WEEKDAY,
        rollover_time=DEFAULT_ROLLOVER_TIME,
    )

    await bot.db.clear_sent_reminders(
        guild_id=ctx.guild_id,
        channel_id=ctx.channel_id,
        workday_date=workday_date,
    )

    await interaction.followup.send(
        f"RSVP panel {action} for **{workday_date}**.\n"
        f"Deadline: <t:{deadline_ts}:f>\n"
        f"Reminders: 48h, 24h, 6h, 1h before deadline.",
        ephemeral=True,
    )


async def attendance_reset_cmd(bot, interaction: discord.Interaction) -> None:
    """
    Reset attendance state for the active workday and refresh the panel.

    This clears:

    - RSVPs (``rsvps`` table)
    - partner links (``work_pairs`` table)
    - sent reminder history (``sent_reminders`` table)

    After clearing state, the RSVP panel embed/view is refreshed.

    Parameters
    ----------
    bot : :class:`discord.Client`
        Bot instance providing database access and panel service.
    interaction : :class:`discord.Interaction`
        The Discord interaction for this command invocation.

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

    deleted_rsvps, deleted_partners, deleted_reminders = await bot.panel.reset_attendance(
        ctx=ctx,
        workday_date=workday_date,
        on_choice=bot.rsvp.on_choice,
        on_choice_with_plan=bot.rsvp.on_choice_with_plan,
    )

    extra_parts: list[str] = []
    if deleted_partners:
        extra_parts.append(f"**{deleted_partners}** partner link(s)")
    if deleted_reminders:
        extra_parts.append(f"**{deleted_reminders}** reminder record(s)")

    extra = ""
    if extra_parts:
        extra = " Cleared " + " and ".join(extra_parts) + "."

    await interaction.followup.send(
        f"Reset RSVPs for **{workday_date}**. Cleared **{deleted_rsvps}** RSVP(s).{extra}",
        ephemeral=True,
    )


async def rsvp_commands_cmd(bot, interaction: discord.Interaction) -> None:
    """
    Show a live list of registered commands available in the current guild.

    This command inspects both:

    - the guild-installed command set (if available)
    - the global command set

    and de-duplicates by command name (guild overrides global).

    Parameters
    ----------
    bot : :class:`discord.Client`
        Bot instance that owns the app command tree (``bot.tree``).
    interaction : :class:`discord.Interaction`
        The Discord interaction for this command invocation.

    Returns
    -------
    :class:`None`

    Raises
    ------
    :class:`discord.HTTPException`
        If Discord API calls fail when sending follow-up messages.
    """
    await interaction.response.defer(ephemeral=True)

    guild_cmds = bot.tree.get_commands(guild=interaction.guild) if interaction.guild else []
    global_cmds = bot.tree.get_commands()

    seen: set[str] = set()
    cmds = []
    for c in sorted(list(guild_cmds) + list(global_cmds), key=lambda x: x.name):
        if c.name in seen:
            continue
        seen.add(c.name)
        cmds.append(c)

    lines: list[str] = []
    for cmd in cmds:
        lines.append(f"/{cmd.name} — {cmd.description or ''}".rstrip())

    text = "\n".join(lines) if lines else "No commands registered."
    await interaction.followup.send(f"**Available commands:**\n{text}", ephemeral=True)


def register_admin_commands(bot) -> None:
    """
    Register core admin commands on a bot instance.

    This module registers:

    - ``/setup``
    - ``/attendance_reset``
    - ``/rsvp_commands``

    Parameters
    ----------
    bot : :class:`discord.Client`
        The bot instance that owns the :class:`discord.app_commands.CommandTree`.

    Returns
    -------
    :class:`None`
    """

    @bot.tree.command(name="setup", description="Create or reset the RSVP panel in this channel (admin only).")
    @in_guild_text_channel()
    @is_admin()
    async def setup(interaction: discord.Interaction) -> None:
        await setup_cmd(bot, interaction)

    @bot.tree.command(
        name="attendance_reset",
        description="Reset all RSVPs for the upcoming workday in this channel (admin only).",
    )
    @in_guild_text_channel()
    @is_admin()
    async def attendance_reset(interaction: discord.Interaction) -> None:
        await attendance_reset_cmd(bot, interaction)

    @bot.tree.command(name="rsvp_commands", description="Show help for available commands.")
    @in_guild_text_channel()
    @is_admin()
    async def rsvp_commands(interaction: discord.Interaction) -> None:
        await rsvp_commands_cmd(bot, interaction)


__all__ = [
    "setup_cmd",
    "attendance_reset_cmd",
    "rsvp_commands_cmd",
    "register_admin_commands",
]
