# src/rsvp_bot/db/reminders.py

"""
Reminder history database operations
====================================

Database access layer for tracking which reminder offsets have already been sent.

The scheduler sends reminders at specific offsets before a workday deadline.
To prevent duplicate reminders (including across bot restarts), the bot records
each successfully sent reminder in the ``sent_reminders`` table.

This module defines :class:`~rsvp_bot.db.reminders.ReminderOps`, a mixin-style class
expected to be combined with a database implementation that provides an async
connection factory via ``self.connect()`` (returning an :class:`aiosqlite.Connection`).

Classes
-------

:class:`ReminderOps`
    Read/write operations for the ``sent_reminders`` table.
"""

from __future__ import annotations

import aiosqlite

from .schema import SentRemindersColumns as SR
from .schema import Tables as T


class ReminderOps:
    """
    Operations for reminder deduplication state.

    A reminder is uniquely identified by:

    - :class:`int` ``guild_id``
    - :class:`int` ``channel_id``
    - :class:`str` ``workday_date`` (ISO ``YYYY-MM-DD``)
    - :class:`int` ``offset_min`` (minutes before deadline)
    """

    async def reminder_already_sent(
        self, *, guild_id: int, channel_id: int, workday_date: str, offset_min: int
    ) -> bool:
        """
        Check whether a reminder offset has already been sent for a workday.

        Parameters
        ----------
        guild_id : :class:`int`
            Discord guild (server) ID.
        channel_id : :class:`int`
            Discord text channel ID where the panel lives.
        workday_date : :class:`str`
            Workday cycle identifier (ISO date string ``YYYY-MM-DD``).
        offset_min : :class:`int`
            Reminder offset in minutes before the deadline.

        Returns
        -------
        :class:`bool`
            :class:`True` if a reminder record exists for this offset; otherwise
            :class:`False`.
        """
        async with self.connect() as db:  # type: ignore[attr-defined]
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"""
                SELECT 1
                FROM {T.SENT_REMINDERS}
                WHERE {SR.GUILD_ID}=? AND {SR.CHANNEL_ID}=? AND {SR.WORKDAY_DATE}=? AND {SR.OFFSET_MIN}=?
                """,
                (guild_id, channel_id, workday_date, offset_min),
            )
            row = await cur.fetchone()
            return row is not None

    async def mark_reminder_sent(
        self, *, guild_id: int, channel_id: int, workday_date: str, offset_min: int, sent_at_ts: int
    ) -> None:
        """
        Record that a reminder offset has been sent for a workday.

        Parameters
        ----------
        guild_id : :class:`int`
            Discord guild (server) ID.
        channel_id : :class:`int`
            Discord text channel ID where the panel lives.
        workday_date : :class:`str`
            Workday cycle identifier (ISO date string ``YYYY-MM-DD``).
        offset_min : :class:`int`
            Reminder offset in minutes before the deadline.
        sent_at_ts : :class:`int`
            UTC epoch seconds for when the reminder was recorded as sent.

        Returns
        -------
        :class:`None`
            This method writes to the database and returns nothing.
        """
        async with self.connect() as db:  # type: ignore[attr-defined]
            db.row_factory = aiosqlite.Row
            await db.execute(
                f"""
                INSERT OR IGNORE INTO {T.SENT_REMINDERS} ({SR.GUILD_ID}, {SR.CHANNEL_ID}, {SR.WORKDAY_DATE}, {SR.OFFSET_MIN}, {SR.SENT_AT_TS})
                VALUES (?, ?, ?, ?, ?)
                """,
                (guild_id, channel_id, workday_date, offset_min, sent_at_ts),
            )
            await db.commit()

    async def clear_sent_reminders(self, *, guild_id: int, channel_id: int, workday_date: str) -> int:
        """
        Delete reminder history for a workday.

        This is used when resetting attendance state or when changing a deadline,
        since previously recorded offsets may no longer be valid.

        Parameters
        ----------
        guild_id : :class:`int`
            Discord guild (server) ID.
        channel_id : :class:`int`
            Discord text channel ID where the panel lives.
        workday_date : :class:`str`
            Workday cycle identifier (ISO date string ``YYYY-MM-DD``).

        Returns
        -------
        :class:`int`
            Number of rows deleted.
        """
        async with self.connect() as db:  # type: ignore[attr-defined]
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"""
                DELETE FROM {T.SENT_REMINDERS}
                WHERE {SR.GUILD_ID}=? AND {SR.CHANNEL_ID}=? AND {SR.WORKDAY_DATE}=?
                """,
                (guild_id, channel_id, workday_date),
            )
            await db.commit()
            return cur.rowcount or 0
