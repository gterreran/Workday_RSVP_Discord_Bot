# src/rsvp_bot/commands/__init__.py

"""
Slash command registration
==========================

This package groups slash-command registration by feature area (admin, directory,
reports, debug). Each module exposes a single public registration function that
attaches its commands to a provided bot instance.

To support Sphinx API documentation, the per-command handler callables are defined
at module scope (e.g., :func:`~rsvp_bot.commands.directory.directory_add_cmd`) and
are registered/decorated only when the corresponding registration function is
called.

Functions
---------
:func:`register_commands`
    Register all commands for a bot instance, including optional debug commands.
"""

from __future__ import annotations

from .admin import register_admin_commands
from .debug import register_debug_commands
from .directory import register_directory_commands
from .reports import register_report_commands


def register_commands(bot) -> None:
    """
    Register all slash commands on a bot instance.

    This function is the single entry point used by :class:`~rsvp_bot.bot.RSVPBot`
    to populate its command tree. Debug-only commands are only registered when
    ``bot.debug`` is truthy.

    Parameters
    ----------
    bot : :class:`discord.Client`
        The bot instance that owns the :class:`discord.app_commands.CommandTree`.

    Returns
    -------
    :class:`None`

    Raises
    ------
    AttributeError
        If ``bot`` is missing expected attributes (e.g., ``tree`` or ``debug``).
    """
    register_admin_commands(bot)
    register_directory_commands(bot)
    register_report_commands(bot)

    if getattr(bot, "debug", False):
        register_debug_commands(bot)


__all__ = [
    "register_commands",
    "register_admin_commands",
    "register_directory_commands",
    "register_report_commands",
    "register_debug_commands",
]
