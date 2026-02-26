# src/rsvp_bot/db/rsvps.py

"""
RSVP database operations
========================

Database access layer for reading and writing RSVP records.

This module defines :class:`~rsvp_bot.db.rsvps.RSVPOps`, a mixin-style class
expected to be combined with a database implementation that provides an async
connection factory via ``self.connect()`` (returning an :class:`aiosqlite.Connection`).

All operations are scoped by:

- :class:`int` ``guild_id``
- :class:`int` ``channel_id``
- :class:`str` ``workday_date`` (ISO ``YYYY-MM-DD``)

The underlying table/column names are defined in :mod:`rsvp_bot.db.schema`.

Classes
-------

:class:`RSVPOps`
    CRUD operations for the ``rsvps`` table.
"""

from __future__ import annotations

import aiosqlite

from .schema import RSVPsColumns as R
from .schema import Tables as T


class RSVPOps:
    """
    CRUD operations for RSVP entries.

    This class assumes the parent :class:`~rsvp_bot.db.core.DB` (or equivalent)
    provides a ``connect()`` method that yields an :class:`aiosqlite.Connection`.

    Notes
    -----
    - The RSVP primary key is ``(guild_id, channel_id, workday_date, user_id)``.
      Writing the same key updates the existing row.
    """

    async def set_rsvp(
        self,
        *,
        guild_id: int,
        channel_id: int,
        workday_date: str,
        user_id: int,
        status: str,
        note: str | None,
        updated_at_ts: int,
    ) -> None:
        """
        Insert or update a user's RSVP for a workday.

        Parameters
        ----------
        guild_id : :class:`int`
            Discord guild (server) ID.
        channel_id : :class:`int`
            Discord text channel ID where the panel lives.
        workday_date : :class:`str`
            Workday cycle identifier (ISO date string ``YYYY-MM-DD``).
        user_id : :class:`int`
            Discord user ID.
        status : :class:`str`
            RSVP status (e.g. ``"yes"``, ``"remote"``, ``"maybe"``, ``"no"``).
        note : :class:`str` or :class:`None`
            Optional free-form note saved with the RSVP.
        updated_at_ts : :class:`int`
            UTC epoch seconds representing when the RSVP was recorded.

        Returns
        -------
        :class:`None`
            This method writes to the database and returns nothing.
        """
        async with self.connect() as db:  # type: ignore[attr-defined]
            db.row_factory = aiosqlite.Row
            await db.execute(
                f"""
                INSERT INTO {T.RSVPS} ({R.GUILD_ID}, {R.CHANNEL_ID}, {R.WORKDAY_DATE}, {R.USER_ID}, {R.STATUS}, {R.NOTE}, {R.UPDATED_AT_TS})
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT({R.GUILD_ID}, {R.CHANNEL_ID}, {R.WORKDAY_DATE}, {R.USER_ID})
                DO UPDATE SET
                {R.STATUS}=excluded.{R.STATUS},
                {R.NOTE}=excluded.{R.NOTE},
                {R.UPDATED_AT_TS}=excluded.{R.UPDATED_AT_TS}
                """,
                (guild_id, channel_id, workday_date, user_id, status, note, updated_at_ts),
            )
            await db.commit()

    async def list_rsvps(self, *, guild_id: int, channel_id: int, workday_date: str) -> list[tuple[int, str]]:
        """
        List RSVP statuses for a workday.

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
        :class:`list` of :class:`tuple` (:class:`int`, :class:`str`)
            A list of ``(user_id, status)`` tuples for all RSVP records in the cycle.
        """
        async with self.connect() as db:  # type: ignore[attr-defined]
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"""
                SELECT {R.USER_ID}, {R.STATUS}, {R.NOTE}
                FROM {T.RSVPS}
                WHERE {R.GUILD_ID}=? AND {R.CHANNEL_ID}=? AND {R.WORKDAY_DATE}=?
                """,
                (guild_id, channel_id, workday_date),
            )
            rows = await cur.fetchall()
            return [(int(r[R.USER_ID]), str(r[R.STATUS])) for r in rows]

    async def list_rsvps_with_notes(
        self, *, guild_id: int, channel_id: int, workday_date: str
    ) -> list[tuple[int, str, str | None]]:
        """
        List RSVP statuses and notes for a workday.

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
        :class:`list` of :class:`tuple` (:class:`int`, :class:`str`, :class:`str` or :class:`None`)
            A list of ``(user_id, status, note)`` tuples. ``note`` is :class:`None`
            when no note is present.
        """
        async with self.connect() as db:  # type: ignore[attr-defined]
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"""
                SELECT {R.USER_ID}, {R.STATUS}, {R.NOTE}
                FROM {T.RSVPS}
                WHERE {R.GUILD_ID}=? AND {R.CHANNEL_ID}=? AND {R.WORKDAY_DATE}=?
                """,
                (guild_id, channel_id, workday_date),
            )
            rows = await cur.fetchall()
            return [
                (int(r[R.USER_ID]), str(r[R.STATUS]), (str(r[R.NOTE]) if r[R.NOTE] is not None else None))
                for r in rows
            ]

    async def get_rsvp(
        self, *, guild_id: int, channel_id: int, workday_date: str, user_id: int
    ) -> tuple[str, str | None] | None:
        """
        Fetch a single user's RSVP for a workday.

        Parameters
        ----------
        guild_id : :class:`int`
            Discord guild (server) ID.
        channel_id : :class:`int`
            Discord text channel ID where the panel lives.
        workday_date : :class:`str`
            Workday cycle identifier (ISO date string ``YYYY-MM-DD``).
        user_id : :class:`int`
            Discord user ID.

        Returns
        -------
        :class:`tuple` (:class:`str`, :class:`str` or :class:`None`) or :class:`None`
            ``(status, note)`` if a record exists; otherwise :class:`None`.
        """
        async with self.connect() as db:  # type: ignore[attr-defined]
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"""
                SELECT {R.STATUS}, {R.NOTE}
                FROM {T.RSVPS}
                WHERE {R.GUILD_ID}=? AND {R.CHANNEL_ID}=? AND {R.WORKDAY_DATE}=? AND {R.USER_ID}=?
                """,
                (guild_id, channel_id, workday_date, user_id),
            )
            row = await cur.fetchone()
            if not row:
                return None
            return (str(row[R.STATUS]), (str(row[R.NOTE]) if row[R.NOTE] is not None else None))

    async def clear_rsvps(self, *, guild_id: int, channel_id: int, workday_date: str) -> int:
        """
        Delete all RSVP records for a workday in a channel.

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
                DELETE FROM {T.RSVPS}
                WHERE {R.GUILD_ID}=? AND {R.CHANNEL_ID}=? AND {R.WORKDAY_DATE}=?
                """,
                (guild_id, channel_id, workday_date),
            )
            await db.commit()
            return cur.rowcount or 0

    async def list_rsvp_user_ids(self, *, guild_id: int, channel_id: int, workday_date: str) -> list[int]:
        """
        List user IDs who have submitted an RSVP for a workday.

        This is a lightweight query intended for reminder targeting and other
        "has responded" checks.

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
        :class:`list` of :class:`int`
            User IDs with RSVP records for the cycle.
        """
        async with self.connect() as db:  # type: ignore[attr-defined]
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"""
                SELECT {R.USER_ID}
                FROM {T.RSVPS}
                WHERE {R.GUILD_ID}=? AND {R.CHANNEL_ID}=? AND {R.WORKDAY_DATE}=?
                """,
                (guild_id, channel_id, workday_date),
            )
            rows = await cur.fetchall()
            return [int(r[R.USER_ID]) for r in rows]
