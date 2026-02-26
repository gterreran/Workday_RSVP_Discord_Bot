# src/rsvp_bot/db/directory.py

"""
Directory membership database operations
========================================

Database access layer for managing RSVP directory membership.

The directory defines the set of users tracked for attendance,
reminders, and summary generation. Membership is soft-deleted
via an ``active`` flag, allowing reactivation without losing
historical records.

This module defines :class:`DirectoryOps`, a mixin-style class expected
to be used with a database implementation providing an async
``self.connect()`` method returning an :class:`aiosqlite.Connection`.

Classes
-------

:class:`DirectoryOps`
    Read/write operations for the ``directory`` table.
"""

from __future__ import annotations

import aiosqlite

from .schema import DirectoryColumns as D
from .schema import Tables as T


class DirectoryOps:
    """
    Operations for managing RSVP directory membership.

    Directory membership is scoped by:

    - :class:`int` guild_id
    - :class:`int` channel_id

    Entries are soft-deleted using an ``active`` flag so users can be
    re-added without losing metadata.
    """

    async def directory_add(
        self, *, guild_id: int, channel_id: int, user_id: int, added_by: int, added_at_ts: int
    ) -> None:
        """
        Add or reactivate a user in the directory.

        If the user already exists in the directory, their membership is
        reactivated by setting ``active = 1``.

        Parameters
        ----------
        guild_id : :class:`int`
            Discord guild (server) ID.
        channel_id : :class:`int`
            Discord text channel ID.
        user_id : :class:`int`
            User being added to the directory.
        added_by : :class:`int`
            User ID of the administrator performing the action.
        added_at_ts : :class:`int`
            UTC epoch seconds when the entry was created.

        Returns
        -------
        :class:`None`
            Writes changes to the database.
        """
        async with self.connect() as db:  # type: ignore[attr-defined]
            db.row_factory = aiosqlite.Row
            await db.execute(
                f"""
                INSERT INTO {T.DIRECTORY} ({D.GUILD_ID}, {D.CHANNEL_ID}, {D.USER_ID}, {D.ACTIVE}, {D.ADDED_BY}, {D.ADDED_AT_TS})
                VALUES (?, ?, ?, 1, ?, ?)
                ON CONFLICT({D.GUILD_ID}, {D.CHANNEL_ID}, {D.USER_ID}) DO UPDATE SET {D.ACTIVE}=1
                """,
                (guild_id, channel_id, user_id, added_by, added_at_ts),
            )
            await db.commit()

    async def directory_list_active(self, *, guild_id: int, channel_id: int) -> list[int]:
        """
        Return active directory members.

        Parameters
        ----------
        guild_id : :class:`int`
            Discord guild (server) ID.
        channel_id : :class:`int`
            Discord text channel ID.

        Returns
        -------
        :class:`list` of :class:`int`
            User IDs currently marked as active directory members.
        """
        async with self.connect() as db:  # type: ignore[attr-defined]
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"""
                SELECT {D.USER_ID}
                FROM {T.DIRECTORY}
                WHERE {D.GUILD_ID}=? AND {D.CHANNEL_ID}=? AND {D.ACTIVE}=1
                """,
                (guild_id, channel_id),
            )
            rows = await cur.fetchall()
            return [int(r[D.USER_ID]) for r in rows]

    async def directory_remove(self, *, guild_id: int, channel_id: int, user_id: int) -> None:
        """
        Deactivate a directory member.

        This performs a soft delete by setting ``active = 0``. Historical
        records are preserved and the user can be reactivated later.

        Parameters
        ----------
        guild_id : :class:`int`
            Discord guild (server) ID.
        channel_id : :class:`int`
            Discord text channel ID.
        user_id : :class:`int`
            User to remove from the directory.

        Returns
        -------
        :class:`None`
            Writes changes to the database.
        """
        async with self.connect() as db:  # type: ignore[attr-defined]
            db.row_factory = aiosqlite.Row
            await db.execute(
                f"""
                UPDATE {T.DIRECTORY}
                SET {D.ACTIVE}=0
                WHERE {D.GUILD_ID}=? AND {D.CHANNEL_ID}=? AND {D.USER_ID}=?
                """,
                (guild_id, channel_id, user_id),
            )
            await db.commit()
