# src/rsvp_bot/bot.py

"""
Bot entrypoint and Discord client
=================================

Application entrypoint and the main :class:`discord.ext.commands.Bot` subclass
used by the RSVP bot.

This module defines:

- :class:`~rsvp_bot.bot.RSVPBot`, the configured Discord client that wires
  together database access, services, and persistent UI views.
- :func:`~rsvp_bot.bot.main`, a CLI entrypoint for running the bot locally.

The bot supports two command sync modes:

- **DEV mode** (when ``DEV_GUILD_ID`` is set): commands are synced to a single
  guild for fast iteration.
- **PROD mode** (default): commands are synced globally.

Classes
-------

:class:`~rsvp_bot.bot.RSVPBot`
    Discord bot client that initializes services, registers persistent views,
    and manages slash-command synchronization.

Functions
---------

:func:`~rsvp_bot.bot.main`
    Parse CLI flags, load configuration, and run the bot process.
"""

from __future__ import annotations

import argparse
import os
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands
from dotenv import load_dotenv

from .commands import register_commands
from .config import load_config
from .db import DB
from .services import PanelService, RSVPService, SchedulerService
from .views import RSVPView


class RSVPBot(commands.Bot):
    """
    Discord bot client for the Workday RSVP Bot.

    This client owns shared resources (database connection factory, timezone,
    services) and controls command installation/synchronization in either DEV
    or PROD mode.

    .. rubric:: Attributes

    db : :class:`~rsvp_bot.db.core.DB`
        Database wrapper providing async persistence operations.
    tz : :class:`zoneinfo.ZoneInfo`
        Bot timezone used for scheduling and validation.
    debug : :class:`bool`
        Whether debug-only commands are registered.
    reset_global_commands : :class:`bool`
        Whether to wipe and re-sync global commands during startup (PROD only).
    reset_guild_commands : :class:`bool`
        Whether to wipe and re-sync guild commands during startup (DEV only).
    panel : :class:`~rsvp_bot.services.panel_service.PanelService`
        Service responsible for creating and refreshing the RSVP panel message.
        Initialized during :meth:`setup_hook`.
    rsvp : :class:`~rsvp_bot.services.rsvp_service.RSVPService`
        Service implementing RSVP update logic and callbacks for UI events.
        Initialized during :meth:`setup_hook`.
    sched : :class:`~rsvp_bot.services.scheduler_service.SchedulerService`
        Background scheduler handling reminders and weekly rollover.
        Initialized during :meth:`setup_hook`.
    """

    def __init__(
        self,
        *,
        db: DB,
        tz: str,
        debug: bool = False,
        reset_global_commands: bool = False,
        reset_guild_commands: bool = True,
    ) -> None:
        """
        Initialize the bot client.

        Parameters
        ----------
        db : :class:`~rsvp_bot.db.core.DB`
            Database wrapper used for persistence.
        tz : :class:`str`
            IANA timezone string (e.g., ``"America/Chicago"``).
        debug : :class:`bool`, optional
            If :class:`True`, register debug-only scheduling commands.
        reset_global_commands : :class:`bool`, optional
            If :class:`True`, delete and re-sync global slash commands on startup
            (PROD mode only).
        reset_guild_commands : :class:`bool`, optional
            If :class:`True`, delete and re-sync guild slash commands on startup
            (DEV mode only).

        Returns
        -------
        None
            This initializer returns :class:`None`.
        """
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)

        self.db = db
        self.tz = ZoneInfo(tz)
        self.debug = bool(debug)

        # Safety / maintenance flags
        self.reset_global_commands = bool(reset_global_commands)
        self.reset_guild_commands = bool(reset_guild_commands)

        # Filled in during setup_hook
        self.panel: PanelService
        self.rsvp: RSVPService
        self.sched: SchedulerService

        # Prevent accidental double-registration inside a single process
        self._commands_registered: bool = False

    async def setup_hook(self) -> None:
        """
        Initialize runtime services, register persistent views, and sync commands.

        This hook runs after login but before the bot is considered ready. It:

        - Initializes the database schema/connection state.
        - Instantiates core services (:class:`~rsvp_bot.services.*`).
        - Registers the persistent :class:`~rsvp_bot.views.RSVPView` so button
          interactions survive restarts.
        - Starts background scheduler loops.
        - Syncs slash commands using either DEV (guild-only) or PROD (global)
          synchronization strategy.

        Returns
        -------
        None
            This coroutine returns :class:`None`.

        Raises
        ------
        ValueError
            If ``DEV_GUILD_ID`` is set but cannot be parsed as an integer.
        """
        await self.db.init()

        self.panel = PanelService(bot=self)
        self.rsvp = RSVPService(bot=self)
        self.sched = SchedulerService(bot=self, weekly_done=set())

        # Persistent view for button interactions across restarts
        self.add_view(
            RSVPView(
                on_choice=self.rsvp.on_choice,
                on_choice_with_plan=self.rsvp.on_choice_with_plan,
            )
        )

        self.sched.start()

        dev_gid = os.getenv("DEV_GUILD_ID", "").strip()
        dev_guild: discord.Object | None = discord.Object(id=int(dev_gid)) if dev_gid else None

        # ----------------------------
        # DEV MODE (guild-only commands)
        # ----------------------------
        if dev_guild is not None:
            # 1) Optionally delete stale commands that Discord still has for this guild
            if self.reset_guild_commands:
                # Clear local *guild* command set and push empty -> deletes remote guild cmds
                self.tree.clear_commands(guild=dev_guild)
                await self.tree.sync(guild=dev_guild)

            # 2) Ensure our local tree is clean before registering (prevents duplicates)
            self.tree.clear_commands(guild=None)  # clear local globals
            self.tree.clear_commands(guild=dev_guild)  # clear local guild copy

            # 3) Register commands ONCE (global-style decorators)
            if not self._commands_registered:
                register_commands(self)
                self._commands_registered = True

            # 4) Copy global -> guild so guild sync actually installs them
            self.tree.copy_global_to(guild=dev_guild)

            # 5) Sync guild commands only (fast iteration; no global sync in dev)
            await self.tree.sync(guild=dev_guild)

            # 6) Optional: keep local globals empty in dev to avoid confusion later
            self.tree.clear_commands(guild=None)
            return

        # ----------------------------
        # PROD MODE (global commands)
        # ----------------------------

        # If requested, wipe remote GLOBAL commands first
        if self.reset_global_commands:
            # Clear local globals and push empty -> deletes remote global cmds
            self.tree.clear_commands(guild=None)
            await self.tree.sync()

        # Always start from a clean local global tree (prevents local duplicates)
        self.tree.clear_commands(guild=None)

        # Register commands ONCE
        if not self._commands_registered:
            register_commands(self)
            self._commands_registered = True

        # Sync global exactly once
        await self.tree.sync()


def main() -> None:
    """
    Run the bot from the command line.

    This function loads environment variables (via :func:`dotenv.load_dotenv`),
    parses CLI flags, loads runtime configuration, constructs the bot, and starts
    the Discord event loop.

    Returns
    -------
    None
        This function returns :class:`None`.

    Raises
    ------
    RuntimeError
        If the required ``DISCORD_TOKEN`` is missing. Raised by
        :func:`~rsvp_bot.config.load_config`.
    """
    load_dotenv()

    parser = argparse.ArgumentParser(prog="rsvp_bot")
    parser.add_argument("--debug", action="store_true", help="Enable debug-only commands")
    parser.add_argument(
        "--reset-global-commands",
        action="store_true",
        help="Delete and recreate GLOBAL slash commands (prod only; slow to propagate).",
    )
    parser.add_argument(
        "--no-reset-guild-commands",
        action="store_true",
        help="In DEV (DEV_GUILD_ID), do not wipe existing guild commands before syncing.",
    )
    args = parser.parse_args()

    cfg = load_config()
    db = DB(cfg.db_path)

    bot = RSVPBot(
        db=db,
        tz=cfg.tz,
        debug=args.debug,
        reset_global_commands=args.reset_global_commands,
        reset_guild_commands=not args.no_reset_guild_commands,
    )
    bot.run(cfg.token)


if __name__ == "__main__":
    main()
