# src/rsvp_bot/commands/ctx.py

"""
Command context helpers
=======================

This module defines a small, typed context object used by command handlers and
services to avoid repeatedly unpacking a :class:`discord.Interaction`.

The primary entry point is :func:`get_ctx`, which optionally defers the
interaction response and then constructs a :class:`CommandCtx` with the resolved
guild, channel, and user objects.

Classes
-------
:class:`CommandCtx`
    Immutable container for a guild text-channel command invocation.

Functions
---------
:func:`get_ctx`
    Build a :class:`CommandCtx` from a :class:`discord.Interaction`.
"""

from __future__ import annotations

from dataclasses import dataclass

import discord


@dataclass(frozen=True, slots=True)
class CommandCtx:
    """
    Lightweight command invocation context.

    .. rubric:: Attributes

    guild : :class:`discord.Guild`
        Guild in which the command was invoked.
    channel : :class:`discord.TextChannel`
        Text channel in which the command was invoked.
    user : :class:`discord.abc.User`
        User who invoked the command.
    """

    guild: discord.Guild
    channel: discord.TextChannel
    user: discord.abc.User

    @property
    def guild_id(self) -> int:
        """
        Guild ID convenience accessor.

        Returns
        -------
        :class:`int`
            The guild ID.
        """
        return self.guild.id

    @property
    def channel_id(self) -> int:
        """
        Channel ID convenience accessor.

        Returns
        -------
        :class:`int`
            The channel ID.
        """
        return self.channel.id

    @property
    def user_id(self) -> int:
        """
        User ID convenience accessor.

        Returns
        -------
        :class:`int`
            The invoking user's ID.
        """
        return self.user.id


async def get_ctx(
    interaction: discord.Interaction,
    *,
    defer: bool = True,
    ephemeral: bool = True,
) -> CommandCtx:
    """
    Build a :class:`CommandCtx` from an interaction.

    Parameters
    ----------
    interaction : :class:`discord.Interaction`
        Interaction invoking a slash command.
    defer : :class:`bool`, optional
        If ``True``, call :meth:`discord.InteractionResponse.defer` before
        returning, so handlers can safely use followups. Default is ``True``.
    ephemeral : :class:`bool`, optional
        Whether the deferred response should be ephemeral. Only used when
        ``defer`` is ``True``. Default is ``True``.

    Returns
    -------
    :class:`~rsvp_bot.commands.ctx.CommandCtx`
        Resolved context for the interaction.

    Raises
    ------
    AssertionError
        If the interaction is not in a guild or not in a text channel.
    :class:`discord.HTTPException`
        If deferring the response fails.
    """
    if defer:
        await interaction.response.defer(ephemeral=ephemeral)

    assert interaction.guild is not None
    assert isinstance(interaction.channel, discord.TextChannel)

    return CommandCtx(
        guild=interaction.guild,
        channel=interaction.channel,
        user=interaction.user,
    )
