# src/rsvp_bot/commands/checks.py

"""
Slash command permission checks
===============================

This module provides reusable :mod:`discord.app_commands` checks used to
restrict where and by whom slash commands can be executed.

These helpers wrap small asynchronous predicates and return decorators
compatible with :meth:`discord.app_commands.CommandTree.command`.

Functions
---------
:func:`is_admin`
    Restrict a command to users with the ``Manage Server`` permission.
:func:`in_guild_text_channel`
    Restrict a command to guild text-channel contexts (no DMs).
"""

from __future__ import annotations

import discord
from discord import app_commands


def is_admin():
    """
    Require the invoking user to have guild administrative permissions.

    This check verifies that the interaction user has the
    ``manage_guild`` permission (shown as **Manage Server** in Discord UI).

    Returns
    -------
    :class:`discord.app_commands.check`
        A decorator that can be applied to slash command handlers.

    Notes
    -----
    This check relies on ``interaction.user.guild_permissions`` and
    therefore only works in guild contexts.
    """

    async def predicate(interaction: discord.Interaction) -> bool:
        perms = getattr(interaction.user, "guild_permissions", None)
        return bool(perms and perms.manage_guild)

    return app_commands.check(predicate)


def in_guild_text_channel():
    """
    Restrict a command to guild text channels.

    This prevents execution in DMs and ensures that both
    :attr:`discord.Interaction.guild` and
    :attr:`discord.Interaction.channel` are present.

    Returns
    -------
    :class:`discord.app_commands.check`
        A decorator that can be applied to slash command handlers.

    Notes
    -----
    This check does not enforce channel *type* beyond non-null presence.
    It is typically combined with :func:`is_admin` for moderation tools.
    """

    async def predicate(interaction: discord.Interaction) -> bool:
        return interaction.guild is not None and interaction.channel is not None

    return app_commands.check(predicate)
