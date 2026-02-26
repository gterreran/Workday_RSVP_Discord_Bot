# src/rsvp_bot/commands/debug.py

"""
Scheduling debug commands
=========================

This module defines admin-only slash commands that override or inspect scheduling
state for a channel. These commands are intended for development, testing, and
operational debugging (e.g., forcing a deadline during a dry run).

The handlers are defined as regular top-level callables so Sphinx can discover
and document them via ``autodoc``, while :func:`register_debug_commands` wires
them into Discord's app command tree.

Functions
---------
:func:`deadline_set_cmd`
    Command handler for ``/deadline_set``.
:func:`workday_set_cmd`
    Command handler for ``/workday_set``.
:func:`workday_reset_cmd`
    Command handler for ``/workday_reset``.
:func:`rollover_set_cmd`
    Command handler for ``/rollover_set``.
:func:`rollover_show_cmd`
    Command handler for ``/rollover_show``.
:func:`reminders_set_cmd`
    Command handler for ``/reminders_set``.
:func:`reminders_show_cmd`
    Command handler for ``/reminders_show``.
:func:`register_debug_commands`
    Register debug scheduling commands on a bot instance.
"""

from __future__ import annotations

from datetime import date as ddate
from datetime import datetime, timedelta
from datetime import time as dtime

import discord
from discord import app_commands

from .checks import in_guild_text_channel, is_admin
from .ctx import get_ctx


async def deadline_set_cmd(bot, interaction: discord.Interaction, *, date: str, time: str) -> None:
    """
    Set the RSVP deadline to an explicit local date and time.

    This updates the channel's deadline using :meth:`rsvp_bot.services.panel_service.PanelService.set_deadline_at`
    and refreshes the RSVP panel. Sent reminder history is cleared as part of the
    deadline update.

    Parameters
    ----------
    bot : :class:`discord.Client`
        Bot instance providing services and database access.
    interaction : :class:`discord.Interaction`
        Interaction invoking the command.
    date : :class:`str`
        Deadline date in ISO format (``YYYY-MM-DD``).
    time : :class:`str`
        Deadline time in 24-hour format (``HH:MM``).

    Returns
    -------
    :class:`None`

    Raises
    ------
    AssertionError
        If :func:`~rsvp_bot.commands.ctx.get_ctx` is invoked outside a guild text channel.
    :class:`discord.HTTPException`
        If Discord API calls fail when responding.
    """
    try:
        d_obj = ddate.fromisoformat(date.strip())
    except Exception:
        await interaction.response.send_message(
            "Invalid date. Use YYYY-MM-DD (e.g. 2026-02-03).",
            ephemeral=True,
        )
        return

    try:
        t_obj = dtime.fromisoformat(time.strip())
    except Exception:
        await interaction.response.send_message(
            "Invalid time. Use HH:MM (24-hour, e.g. 18:30).",
            ephemeral=True,
        )
        return

    ctx = await get_ctx(interaction)
    workday_date = await bot.db.get_workday_date(guild_id=ctx.guild_id, channel_id=ctx.channel_id)

    deadline_local = datetime.combine(d_obj, t_obj).replace(tzinfo=bot.tz)

    now_local = datetime.now(bot.tz)
    if deadline_local < now_local:
        await interaction.followup.send("That deadline is in the past (in my local timezone).", ephemeral=True)
        return

    workday_local = datetime.fromisoformat(workday_date).replace(tzinfo=bot.tz) + timedelta(days=1)
    if deadline_local > workday_local:
        await interaction.followup.send("Deadline cannot be after the workday date.", ephemeral=True)
        return

    try:
        new_deadline_ts = await bot.panel.set_deadline_at(
            ctx=ctx,
            workday_date=workday_date,
            deadline_local=deadline_local,
            on_choice=bot.rsvp.on_choice,
            on_choice_with_plan=bot.rsvp.on_choice_with_plan,
        )
    except LookupError:
        await interaction.followup.send("No active workday found. Run /setup first.", ephemeral=True)
        return

    await interaction.followup.send(
        f"Deadline set to <t:{new_deadline_ts}:f> (local: {deadline_local.strftime('%Y-%m-%d %H:%M %Z')}).",
        ephemeral=True,
    )


async def workday_set_cmd(bot, interaction: discord.Interaction, *, date: str) -> None:
    """
    Manually override the channel's workday date (``YYYY-MM-DD``).

    This writes the workday date to the channel row and refreshes the RSVP panel.
    It does not modify reminder offsets or rollover schedule.

    Parameters
    ----------
    bot : :class:`discord.Client`
        Bot instance providing services and database access.
    interaction : :class:`discord.Interaction`
        Interaction invoking the command.
    date : :class:`str`
        Workday date in ISO format (``YYYY-MM-DD``).

    Returns
    -------
    :class:`None`

    Raises
    ------
    AssertionError
        If :func:`~rsvp_bot.commands.ctx.get_ctx` is invoked outside a guild text channel.
    :class:`discord.HTTPException`
        If Discord API calls fail when responding.
    """
    try:
        parsed = datetime.fromisoformat(date).date()
    except ValueError:
        await interaction.response.send_message("Invalid date format. Use YYYY-MM-DD.", ephemeral=True)
        return

    now_local = datetime.now(bot.tz).date()
    if parsed < now_local:
        await interaction.response.send_message(
            "Workday date cannot be in the past (in my local timezone).",
            ephemeral=True,
        )
        return

    ctx = await get_ctx(interaction)

    await bot.db.update_workday_date(
        guild_id=ctx.guild_id,
        channel_id=ctx.channel_id,
        workday_date=parsed.isoformat(),
    )

    await interaction.followup.send(
        f"Default workday date set to **{parsed.isoformat()}**.",
        ephemeral=True,
    )

    await bot.panel.refresh_panel(
        ctx=ctx,
        workday_date=parsed.isoformat(),
        on_choice=bot.rsvp.on_choice,
        on_choice_with_plan=bot.rsvp.on_choice_with_plan,
    )


async def workday_reset_cmd(bot, interaction: discord.Interaction) -> None:
    """
    Restore automatic workday scheduling for the channel.

    This clears any manual workday override by storing ``NULL`` for the workday date.

    Parameters
    ----------
    bot : :class:`discord.Client`
        Bot instance providing database access.
    interaction : :class:`discord.Interaction`
        Interaction invoking the command.

    Returns
    -------
    :class:`None`

    Raises
    ------
    AssertionError
        If :func:`~rsvp_bot.commands.ctx.get_ctx` is invoked outside a guild text channel.
    :class:`discord.HTTPException`
        If Discord API calls fail when responding.
    """
    ctx = await get_ctx(interaction)

    await bot.db.update_workday_date(
        guild_id=ctx.guild_id,
        channel_id=ctx.channel_id,
        workday_date=None,
    )

    await interaction.followup.send("Automatic scheduling restored.", ephemeral=True)


async def rollover_set_cmd(bot, interaction: discord.Interaction, *, weekday: int, time_hhmm: str) -> None:
    """
    Set the weekly rollover schedule for the channel.

    Rollover controls when the bot automatically advances to the next workday
    cycle in :class:`~rsvp_bot.services.scheduler_service.SchedulerService`.

    Parameters
    ----------
    bot : :class:`discord.Client`
        Bot instance providing database access.
    interaction : :class:`discord.Interaction`
        Interaction invoking the command.
    weekday : :class:`int`
        Day of week (Mon=0 .. Sun=6).
    time_hhmm : :class:`str`
        Local time in ``HH:MM`` (24-hour).

    Returns
    -------
    :class:`None`

    Raises
    ------
    AssertionError
        If :func:`~rsvp_bot.commands.ctx.get_ctx` is invoked outside a guild text channel.
    :class:`discord.HTTPException`
        If Discord API calls fail when responding.
    """
    if weekday < 0 or weekday > 6:
        await interaction.response.send_message("weekday must be 0..6 (0=Mon ... 6=Sun).", ephemeral=True)
        return

    try:
        hh, mm = time_hhmm.split(":")
        hh_i = int(hh)
        mm_i = int(mm)
        if not (0 <= hh_i <= 23 and 0 <= mm_i <= 59):
            raise ValueError
        norm = f"{hh_i:02d}:{mm_i:02d}"
    except Exception:
        await interaction.response.send_message(
            "time_hhmm must be HH:MM (24h), e.g. 09:00 or 18:30.",
            ephemeral=True,
        )
        return

    ctx = await get_ctx(interaction)

    await bot.db.set_rollover_schedule(
        guild_id=ctx.guild_id,
        channel_id=ctx.channel_id,
        weekday=weekday,
        time_hhmm=norm,
    )

    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    await interaction.followup.send(
        f"Rollover schedule set to **{names[weekday]} {norm}** (local channel time).",
        ephemeral=True,
    )


async def rollover_show_cmd(bot, interaction: discord.Interaction) -> None:
    """
    Show the current weekly rollover schedule for the channel.

    Parameters
    ----------
    bot : :class:`discord.Client`
        Bot instance providing database access.
    interaction : :class:`discord.Interaction`
        Interaction invoking the command.

    Returns
    -------
    :class:`None`

    Raises
    ------
    AssertionError
        If :func:`~rsvp_bot.commands.ctx.get_ctx` is invoked outside a guild text channel.
    :class:`discord.HTTPException`
        If Discord API calls fail when responding.
    """
    ctx = await get_ctx(interaction)
    wd, hhmm = await bot.db.get_rollover_schedule(guild_id=ctx.guild_id, channel_id=ctx.channel_id)

    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    await interaction.followup.send(
        f"Rollover schedule: **{names[wd]} {hhmm}** (local channel time).",
        ephemeral=True,
    )


async def reminders_set_cmd(
    bot,
    interaction: discord.Interaction,
    *,
    values: str,
    unit: app_commands.Choice[str],
) -> None:
    """
    Set reminder offsets before the RSVP deadline.

    Offsets are stored as minutes before the deadline and sorted descending.

    Parameters
    ----------
    bot : :class:`discord.Client`
        Bot instance providing database access.
    interaction : :class:`discord.Interaction`
        Interaction invoking the command.
    values : :class:`str`
        Comma-separated integers (e.g. ``"48,24,6,1"``).
    unit : :class:`discord.app_commands.Choice`
        Unit for ``values`` (``minutes``, ``hours``, or ``days``).

    Returns
    -------
    :class:`None`

    Raises
    ------
    AssertionError
        If :func:`~rsvp_bot.commands.ctx.get_ctx` is invoked outside a guild text channel.
    :class:`discord.HTTPException`
        If Discord API calls fail when responding.
    """
    parts = [p.strip() for p in values.split(",")]
    nums: list[int] = []
    try:
        for p in parts:
            if not p:
                continue
            nums.append(int(p))
    except ValueError:
        await interaction.response.send_message(
            "Values must be integers (e.g. `48,24,6,1`).",
            ephemeral=True,
        )
        return

    if not nums:
        await interaction.response.send_message("Please provide at least one value.", ephemeral=True)
        return

    factor = {"minutes": 1, "hours": 60, "days": 1440}[unit.value]
    offsets_min = sorted({n * factor for n in nums if n > 0}, reverse=True)

    if not offsets_min:
        await interaction.response.send_message("All values must be positive.", ephemeral=True)
        return

    ctx = await get_ctx(interaction)

    await bot.db.set_reminder_offsets(
        guild_id=ctx.guild_id,
        channel_id=ctx.channel_id,
        offsets_min=offsets_min,
    )

    suffix = {"minutes": "min", "hours": "h", "days": "d"}[unit.value]
    pretty = ", ".join(str(n) for n in sorted(set(nums), reverse=True))

    await interaction.followup.send(
        f"Reminder schedule updated: **{pretty} {suffix}** before deadline.",
        ephemeral=True,
    )


async def reminders_show_cmd(bot, interaction: discord.Interaction) -> None:
    """
    Show reminder offsets for the channel in minutes before the deadline.

    Parameters
    ----------
    bot : :class:`discord.Client`
        Bot instance providing database access.
    interaction : :class:`discord.Interaction`
        Interaction invoking the command.

    Returns
    -------
    :class:`None`

    Raises
    ------
    AssertionError
        If :func:`~rsvp_bot.commands.ctx.get_ctx` is invoked outside a guild text channel.
    :class:`discord.HTTPException`
        If Discord API calls fail when responding.
    """
    ctx = await get_ctx(interaction)
    offsets_min = await bot.db.get_reminder_offsets(guild_id=ctx.guild_id, channel_id=ctx.channel_id)

    if not offsets_min:
        await interaction.followup.send("No reminders configured for this channel.", ephemeral=True)
        return

    pretty = ", ".join(str(x) for x in offsets_min)
    await interaction.followup.send(
        f"Reminder schedule (in minutes before deadline): **{pretty} min**.",
        ephemeral=True,
    )


def register_debug_commands(bot) -> None:
    """
    Register scheduling debug commands on a bot instance.

    This module registers:

    - ``/deadline_set``
    - ``/workday_set``
    - ``/workday_reset``
    - ``/rollover_set``
    - ``/rollover_show``
    - ``/reminders_set``
    - ``/reminders_show``

    Parameters
    ----------
    bot : :class:`discord.Client`
        The bot instance that owns the :class:`discord.app_commands.CommandTree`.

    Returns
    -------
    :class:`None`
    """

    @bot.tree.command(
        name="deadline_set",
        description="Set the RSVP deadline to a specific local date + time for the upcoming workday (admin only).",
    )
    @app_commands.describe(date="Deadline date (YYYY-MM-DD)", time="Deadline time (HH:MM, 24-hour)")
    @in_guild_text_channel()
    @is_admin()
    async def deadline_set(interaction: discord.Interaction, date: str, time: str) -> None:
        await deadline_set_cmd(bot, interaction, date=date, time=time)

    @bot.tree.command(
        name="workday_set",
        description="Set the default workday date (ISO: YYYY-MM-DD) for this channel (admin only).",
    )
    @app_commands.describe(date="Workday date in ISO format (YYYY-MM-DD)")
    @in_guild_text_channel()
    @is_admin()
    async def workday_set(interaction: discord.Interaction, date: str) -> None:
        await workday_set_cmd(bot, interaction, date=date)

    @bot.tree.command(name="workday_reset", description="Reset the workday to the automatic scheduling.")
    @in_guild_text_channel()
    @is_admin()
    async def workday_reset(interaction: discord.Interaction) -> None:
        await workday_reset_cmd(bot, interaction)

    @bot.tree.command(
        name="rollover_set",
        description="Set when the bot auto-creates the new workday (weekday + local time) (admin only).",
    )
    @app_commands.describe(
        weekday="0=Mon ... 6=Sun",
        time_hhmm="Local time in HH:MM (24h), e.g. 09:00 or 18:30",
    )
    @in_guild_text_channel()
    @is_admin()
    async def rollover_set(interaction: discord.Interaction, weekday: int, time_hhmm: str) -> None:
        await rollover_set_cmd(bot, interaction, weekday=weekday, time_hhmm=time_hhmm)

    @bot.tree.command(name="rollover_show", description="Show this channel's rollover schedule (admin only).")
    @in_guild_text_channel()
    @is_admin()
    async def rollover_show(interaction: discord.Interaction) -> None:
        await rollover_show_cmd(bot, interaction)

    @bot.tree.command(name="reminders_set", description="Set reminder offsets before the deadline (admin only).")
    @app_commands.describe(values="Comma-separated numbers, e.g. 48,24,6,1", unit="Unit: days, hours, or minutes")
    @app_commands.choices(
        unit=[
            app_commands.Choice(name="minutes", value="minutes"),
            app_commands.Choice(name="hours", value="hours"),
            app_commands.Choice(name="days", value="days"),
        ]
    )
    @in_guild_text_channel()
    @is_admin()
    async def reminders_set(
        interaction: discord.Interaction,
        values: str,
        unit: app_commands.Choice[str],
    ) -> None:
        await reminders_set_cmd(bot, interaction, values=values, unit=unit)

    @bot.tree.command(name="reminders_show", description="Show this channel's reminder schedule (admin only).")
    @in_guild_text_channel()
    @is_admin()
    async def reminders_show(interaction: discord.Interaction) -> None:
        await reminders_show_cmd(bot, interaction)


__all__ = [
    "deadline_set_cmd",
    "workday_set_cmd",
    "workday_reset_cmd",
    "rollover_set_cmd",
    "rollover_show_cmd",
    "reminders_set_cmd",
    "reminders_show_cmd",
    "register_debug_commands",
]
