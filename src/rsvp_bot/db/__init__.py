# src/rsvp_bot/db/__init__.py

"""
Database facade and composition layer
=====================================

This module exposes the high-level database interface used throughout the RSVP
bot. It composes multiple operation mixins into a single :class:`DB` class,
providing a unified async API for all persistence operations.

The design follows a layered approach:

- :class:`~rsvp_bot.db.core.DBCore` provides low-level connection handling.
- Operation mixins (e.g. :class:`~rsvp_bot.db.channels.ChannelsOps`,
  :class:`~rsvp_bot.db.directory.DirectoryOps`) implement domain-specific SQL.
- :class:`DB` aggregates these into a single object consumed by services.

The module also exposes the schema migration string
:data:`~rsvp_bot.db.migrations.SCHEMA`, which is executed during initialization.

Classes
-------

:class:`DB`
    Unified async database interface combining all persistence operations.
"""

from __future__ import annotations

import aiosqlite

from .channels import ChannelsOps
from .core import DBCore
from .directory import DirectoryOps
from .migrations import SCHEMA
from .pairs import PairOps
from .reminders import ReminderOps
from .rsvps import RSVPOps


class DB(
    DBCore,
    ChannelsOps,
    DirectoryOps,
    RSVPOps,
    ReminderOps,
    PairOps,
):
    """
    Unified database interface for the RSVP bot.

    This class composes multiple operation mixins into a single async database
    facade. It provides methods for managing:

    - Channel configuration and scheduling
    - Directory membership
    - RSVP records
    - Reminder tracking
    - Work partner relationships

    The class inherits from :class:`~rsvp_bot.db.core.DBCore` for connection
    handling and augments it with domain-specific operations from the mixins.

    The database schema is created or updated via :meth:`init`.

    """

    async def init(self) -> None:
        """
        Initialize the database schema.

        This method executes the SQL schema script defined in
        :data:`~rsvp_bot.db.migrations.SCHEMA`, ensuring all tables and indexes
        required by the bot exist.

        Returns
        -------
        :class:`None`

        Notes
        -----
        This operation is idempotent and safe to run on every bot startup.
        """
        async with self.connect() as db:
            db.row_factory = aiosqlite.Row
            await db.executescript(SCHEMA)
            await db.commit()
