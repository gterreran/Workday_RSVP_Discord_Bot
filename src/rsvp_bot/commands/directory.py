# src/rsvp_bot/commands/directory.py

"""
Directory commands
==================

This module implements the admin-only commands that manage the per-channel RSVP
directory. The directory defines the set of users that the bot considers
"expected" for attendance tracking and reminders.

Handlers are defined at module scope so Sphinx can document them. They are
registered to Discord via :func:`register_directory_commands`, which applies
the appropriate checks and command metadata.

Functions
---------
:func:`register_directory_commands`
    Register the directory management slash commands on a bot instance.
:func:`directory_add_cmd`
    Command handler for ``/directory_add``.
:func:`directory_remove_cmd`
    Command handler for ``/directory_remove``.
:func:`directory_list_cmd`
    Command handler for ``/directory_list``.
"""

from __future__ import annotations

import time

import discord
from discord import app_commands

from .checks import in_guild_text_channel, is_admin
from .ctx import get_ctx


async def directory_add_cmd(bot, interaction: discord.Interaction, user: discord.Member) -> None:
    """
    Add a user to this channel's RSVP directory.

    This command is intended for administrators. If the user is already active in
    the directory for the current channel, the command returns without changing
    state.

    When a valid RSVP panel exists in this channel (detected via the presence of
    a ``workday_date`` in the channel row), the panel is refreshed to reflect the
    updated directory membership.

    Parameters
    ----------
    bot : :class:`discord.Client`
        Bot instance providing access to the database layer (``bot.db``) and
        panel service (``bot.panel``).
    interaction : :class:`discord.Interaction`
        The Discord interaction for this slash command invocation.
    user : :class:`discord.Member`
        The guild member to add to this channel's directory.

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

    active_ids = set(
        await bot.db.directory_list_active(guild_id=ctx.guild_id, channel_id=ctx.channel_id)
    )
    if user.id in active_ids:
        await interaction.followup.send(f"{user.mention} is already in the directory.", ephemeral=True)
        return

    await bot.db.directory_add(
        guild_id=ctx.guild_id,
        channel_id=ctx.channel_id,
        user_id=user.id,
        added_by=interaction.user.id,
        added_at_ts=int(time.time()),
    )

    workday_date = await bot.db.get_workday_date(guild_id=ctx.guild_id, channel_id=ctx.channel_id)

    # workday_date existence is used as a proxy for the existence of the panel,
    # so only refresh if we have a valid workday_date
    if workday_date:
        await bot.panel.refresh_panel(
            ctx=ctx,
            workday_date=workday_date,
            on_choice=bot.rsvp.on_choice,
            on_choice_with_plan=bot.rsvp.on_choice_with_plan,
        )

    await interaction.followup.send(
        f"Added {user.mention} to the directory for this channel.", ephemeral=True
    )


async def directory_remove_cmd(bot, interaction: discord.Interaction, user: discord.Member) -> None:
    """
    Remove a user from this channel's RSVP directory.

    This deactivates the directory entry (soft-remove). Historical RSVPs are not
    deleted; the user simply stops being considered "expected" for future
    summaries and reminders.

    When a valid RSVP panel exists in this channel, it is refreshed to reflect
    the updated directory membership.

    Parameters
    ----------
    bot : :class:`discord.Client`
        Bot instance providing access to the database layer (``bot.db``) and
        panel service (``bot.panel``).
    interaction : :class:`discord.Interaction`
        The Discord interaction for this slash command invocation.
    user : :class:`discord.Member`
        The guild member to remove from this channel's directory.

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

    active_ids = set(
        await bot.db.directory_list_active(guild_id=ctx.guild_id, channel_id=ctx.channel_id)
    )
    if user.id not in active_ids:
        await interaction.followup.send(f"{user.mention} is not currently in the directory.", ephemeral=True)
        return

    await bot.db.directory_remove(
        guild_id=ctx.guild_id,
        channel_id=ctx.channel_id,
        user_id=user.id,
    )

    workday_date = await bot.db.get_workday_date(guild_id=ctx.guild_id, channel_id=ctx.channel_id)

    if workday_date:
        await bot.panel.refresh_panel(
            ctx=ctx,
            workday_date=workday_date,
            on_choice=bot.rsvp.on_choice,
            on_choice_with_plan=bot.rsvp.on_choice_with_plan,
        )

    await interaction.followup.send(
        f"Removed {user.mention} from the directory for this channel.", ephemeral=True
    )


async def directory_list_cmd(bot, interaction: discord.Interaction) -> None:
    """
    Show the active RSVP directory for the current channel.

    The directory is returned as one or more ephemeral messages containing user
    mentions. Output is chunked to stay well below Discord's message length
    limits.

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

    ids = await bot.db.directory_list_active(guild_id=ctx.guild_id, channel_id=ctx.channel_id)
    if not ids:
        await interaction.followup.send("Directory is empty for this channel.", ephemeral=True)
        return

    mentions = [f"<@{uid}>" for uid in sorted(set(ids))]

    lines: list[str] = []
    current = ""
    for m in mentions:
        if len(current) + len(m) + 1 > 1800:
            lines.append(current.strip())
            current = ""
        current += m + " "
    if current.strip():
        lines.append(current.strip())

    header = f"Directory for <#{ctx.channel_id}> (**{len(mentions)}** people):"
    await interaction.followup.send(f"{header}\n{lines[0]}", ephemeral=True)
    for chunk in lines[1:]:
        await interaction.followup.send(chunk, ephemeral=True)


def register_directory_commands(bot) -> None:
    """
    Register directory management commands on a bot instance.

    This function binds the module-level handlers to the bot's command tree and
    applies the appropriate checks:

    - :func:`~rsvp_bot.commands.checks.in_guild_text_channel`
    - :func:`~rsvp_bot.commands.checks.is_admin`

    Parameters
    ----------
    bot : :class:`discord.Client`
        The bot instance that owns the :class:`discord.app_commands.CommandTree`.

    Returns
    -------
    :class:`None`
    """

    # /directory_add
    bot.tree.command(
        name="directory_add",
        description="Add a user to this channel's RSVP directory (admin only).",
    )(
        in_guild_text_channel()(
            is_admin()(
                app_commands.describe(user="User to add")(
                    lambda interaction, user: directory_add_cmd(bot, interaction, user)
                )
            )
        )
    )

    # /directory_remove
    bot.tree.command(
        name="directory_remove",
        description="Remove a user from this channel's RSVP directory (admin only).",
    )(
        in_guild_text_channel()(
            is_admin()(
                app_commands.describe(user="User to remove")(
                    lambda interaction, user: directory_remove_cmd(bot, interaction, user)
                )
            )
        )
    )

    # /directory_list
    bot.tree.command(
        name="directory_list",
        description="Show the current RSVP directory for this channel (admin only).",
    )(
        in_guild_text_channel()(
            is_admin()(
                lambda interaction: directory_list_cmd(bot, interaction)
            )
        )
    )


__all__ = [
    "register_directory_commands",
    "directory_add_cmd",
    "directory_remove_cmd",
    "directory_list_cmd",
]
