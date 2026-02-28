# src/rsvp_bot/db/channels.py

"""
Channel scheduling state database operations
============================================

Database access layer for the per-channel scheduling state stored in the
``channels`` table.

A "registered channel" is a guild text channel where an RSVP panel has been
initialized (typically via ``/setup``). For each registered channel, the bot
persists:

- the active workday date (``YYYY-MM-DD``)
- the RSVP deadline timestamp (UTC epoch seconds)
- the reminder schedule (comma-separated minutes)
- the rollover schedule (weekday + local time)
- the message ID of the persistent RSVP panel embed

This module defines :class:`ChannelsOps`, a mixin-style class expected to be used
with a database implementation providing an async ``self.connect()`` method
returning an :class:`aiosqlite.Connection`.

Constants
---------

:data:`DEFAULT_OFFSETS_MIN`
    Fallback reminder offsets used when a channel row is missing or unset.
:data:`DEFAULT_ROLLOVER_TIME`
    Fallback rollover time (local) used when a channel row is missing or unset.
:data:`DEFAULT_ROLLOVER_WEEKDAY`
    Fallback rollover weekday used when a channel row is missing or unset.

Classes
-------

:class:`ChannelsOps`
    Read/write operations for the ``channels`` table.
"""

from __future__ import annotations

from datetime import date
from typing import Optional
from zoneinfo import ZoneInfo

import aiosqlite

from ..config import DEFAULT_OFFSETS_MIN, DEFAULT_ROLLOVER_TIME, DEFAULT_ROLLOVER_WEEKDAY
from ..utils import default_deadline_for, next_workday
from .schema import ChannelColumns as CH
from .schema import Tables as T


class ChannelsOps:
    """
    Operations for persisting and retrieving per-channel scheduling state.

    Each method is scoped to a specific ``(guild_id, channel_id)`` pair and
    operates on the ``channels`` table.
    """

    async def upsert_channel(
        self,
        *,
        guild_id: int,
        channel_id: int,
        reminder_offsets: str,
        workday_date: str,
        deadline_ts: int,
        rsvp_message_id: int,
        rollover_weekday: int,
        rollover_time: str,
    ) -> None:
        """
        Insert or update a channel row.

        Parameters
        ----------
        guild_id : :class:`int`
            Discord guild (server) ID.
        channel_id : :class:`int`
            Discord text channel ID.
        reminder_offsets : :class:`str`
            Comma-separated offsets in minutes before the deadline (e.g. ``"2880,1440,360,60"``).
        workday_date : :class:`str`
            Workday date in ISO format (``YYYY-MM-DD``).
        deadline_ts : :class:`int`
            RSVP deadline as UTC epoch seconds.
        rsvp_message_id : :class:`int`
            Discord message ID of the persistent RSVP panel.
        rollover_weekday : :class:`int`
            Rollover weekday in local time (Mon=0 .. Sun=6).
        rollover_time : :class:`str`
            Rollover time in local time as ``HH:MM`` (24-hour).

        Returns
        -------
        :class:`None`
            Writes changes to the database.
        """
        async with self.connect() as db:  # type: ignore[attr-defined]
            db.row_factory = aiosqlite.Row
            await db.execute(
                f"""
                INSERT INTO {T.CHANNEL} (
                    {CH.GUILD_ID}, {CH.CHANNEL_ID},
                    {CH.REMINDER_OFFSETS}, {CH.WORKDAY_DATE},
                    {CH.DEADLINE_TS}, {CH.RSVP_MESSAGE_ID},
                    {CH.ROLLOVER_WEEKDAY}, {CH.ROLLOVER_TIME}
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT({CH.GUILD_ID}, {CH.CHANNEL_ID}) DO UPDATE SET
                    {CH.REMINDER_OFFSETS}=excluded.{CH.REMINDER_OFFSETS},
                    {CH.WORKDAY_DATE}=excluded.{CH.WORKDAY_DATE},
                    {CH.DEADLINE_TS}=excluded.{CH.DEADLINE_TS},
                    {CH.RSVP_MESSAGE_ID}=excluded.{CH.RSVP_MESSAGE_ID},
                    {CH.ROLLOVER_WEEKDAY}=excluded.{CH.ROLLOVER_WEEKDAY},
                    {CH.ROLLOVER_TIME}=excluded.{CH.ROLLOVER_TIME}
                """,
                (
                    guild_id,
                    channel_id,
                    reminder_offsets,
                    workday_date,
                    int(deadline_ts),
                    int(rsvp_message_id),
                    int(rollover_weekday),
                    str(rollover_time),
                ),
            )
            await db.commit()

    async def list_registered_channels(self) -> list[tuple[int, int]]:
        """
        List channels registered in the ``channels`` table.

        Returns
        -------
        :class:`list` of :class:`tuple` (:class:`int`, :class:`int`)
            A list of ``(guild_id, channel_id)`` pairs, ordered by guild then channel.
        """
        async with self.connect() as db:  # type: ignore[attr-defined]
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"""
                SELECT {CH.GUILD_ID}, {CH.CHANNEL_ID}
                FROM {T.CHANNEL}
                ORDER BY {CH.GUILD_ID}, {CH.CHANNEL_ID}
                """
            )
            rows = await cur.fetchall()
            return [(int(r[CH.GUILD_ID]), int(r[CH.CHANNEL_ID])) for r in rows]

    async def get_workday_date(self, *, guild_id: int, channel_id: int) -> Optional[str]:
        """
        Return the currently stored workday date for a channel.

        Parameters
        ----------
        guild_id : :class:`int`
            Discord guild (server) ID.
        channel_id : :class:`int`
            Discord text channel ID.

        Returns
        -------
        :class:`str` or :class:`None`
            The workday date in ISO format (``YYYY-MM-DD``), or :class:`None` if the
            channel row is missing or unset.
        """
        async with self.connect() as db:  # type: ignore[attr-defined]
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"""
                SELECT {CH.WORKDAY_DATE}
                FROM {T.CHANNEL}
                WHERE {CH.GUILD_ID}=? AND {CH.CHANNEL_ID}=?
                """,
                (guild_id, channel_id),
            )
            row = await cur.fetchone()
            if not row:
                return None
            val = row[CH.WORKDAY_DATE]
            return str(val) if val else None

    async def update_workday_date(self, *, guild_id: int, channel_id: int, workday_date: Optional[str]) -> int:
        """
        Update the stored workday date for a channel.

        Parameters
        ----------
        guild_id : :class:`int`
            Discord guild (server) ID.
        channel_id : :class:`int`
            Discord text channel ID.
        workday_date : :class:`str` or :class:`None`
            Workday date in ISO format (``YYYY-MM-DD``). If :class:`None`, the
            column is set to NULL.

        Returns
        -------
        :class:`int`
            Number of rows updated (0 if the channel row does not exist).
        """
        async with self.connect() as db:  # type: ignore[attr-defined]
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"""
                UPDATE {T.CHANNEL}
                SET {CH.WORKDAY_DATE}=?
                WHERE {CH.GUILD_ID}=? AND {CH.CHANNEL_ID}=?
                """,
                (workday_date, guild_id, channel_id),
            )
            await db.commit()
            return int(cur.rowcount or 0)

    async def get_deadline(self, *, guild_id: int, channel_id: int) -> Optional[int]:
        """
        Return the stored RSVP deadline timestamp for a channel.

        Parameters
        ----------
        guild_id : :class:`int`
            Discord guild (server) ID.
        channel_id : :class:`int`
            Discord text channel ID.

        Returns
        -------
        :class:`int` or :class:`None`
            Deadline as UTC epoch seconds, or :class:`None` if the channel row is
            missing or unset.
        """
        async with self.connect() as db:  # type: ignore[attr-defined]
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"""
                SELECT {CH.DEADLINE_TS}
                FROM {T.CHANNEL}
                WHERE {CH.GUILD_ID}=? AND {CH.CHANNEL_ID}=?
                """,
                (guild_id, channel_id),
            )
            row = await cur.fetchone()
            if not row:
                return None
            val = row[CH.DEADLINE_TS]
            return int(val) if val else None

    async def get_reminder_offsets(self, *, guild_id: int, channel_id: int) -> list[int]:
        """
        Return reminder offsets for a channel.

        Offsets are stored in the database as a comma-separated string of minutes.
        This method parses, normalizes, de-duplicates, and sorts offsets in
        descending order.

        If the channel row is missing or the field is unset, the value falls back
        to :data:`DEFAULT_OFFSETS_MIN`.

        Parameters
        ----------
        guild_id : :class:`int`
            Discord guild (server) ID.
        channel_id : :class:`int`
            Discord text channel ID.

        Returns
        -------
        :class:`list` of :class:`int`
            Offsets in minutes before the deadline, sorted descending.
        """
        async with self.connect() as db:  # type: ignore[attr-defined]
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"""
                SELECT {CH.REMINDER_OFFSETS}
                FROM {T.CHANNEL}
                WHERE {CH.GUILD_ID}=? AND {CH.CHANNEL_ID}=?
                """,
                (guild_id, channel_id),
            )
            row = await cur.fetchone()

        raw = (str(row[CH.REMINDER_OFFSETS]).strip() if row else DEFAULT_OFFSETS_MIN)
        out: list[int] = []
        for part in raw.split(","):
            part = part.strip()
            if part:
                out.append(int(part))
        return sorted(set(out), reverse=True)

    async def set_reminder_offsets(self, *, guild_id: int, channel_id: int, offsets_min: list[int]) -> None:
        """
        Store reminder offsets for a channel.

        Parameters
        ----------
        guild_id : :class:`int`
            Discord guild (server) ID.
        channel_id : :class:`int`
            Discord text channel ID.
        offsets_min : :class:`list` of :class:`int`
            Offsets in minutes before the deadline. Values ``<= 0`` are ignored.

        Returns
        -------
        :class:`None`
            Writes changes to the database.

        Notes
        -----
        If ``offsets_min`` becomes empty after normalization, this method stores
        :data:`DEFAULT_OFFSETS_MIN` instead.
        """
        offsets_min = sorted(set(int(x) for x in offsets_min if int(x) > 0), reverse=True)
        raw = ",".join(str(x) for x in offsets_min) if offsets_min else DEFAULT_OFFSETS_MIN
        async with self.connect() as db:  # type: ignore[attr-defined]
            db.row_factory = aiosqlite.Row
            # If the channel row exists, a simple UPDATE is sufficient.
            cur = await db.execute(
                f"""
                SELECT 1
                FROM {T.CHANNEL}
                WHERE {CH.GUILD_ID}=? AND {CH.CHANNEL_ID}=?
                """,
                (guild_id, channel_id),
            )
            exists = await cur.fetchone()

            if exists:
                await db.execute(
                    f"""
                    UPDATE {T.CHANNEL}
                    SET {CH.REMINDER_OFFSETS}=?
                    WHERE {CH.GUILD_ID}=? AND {CH.CHANNEL_ID}=?
                    """,
                    (raw, guild_id, channel_id),
                )
            else:
                # Channel has not been initialized yet. Insert a full row using defaults.
                # These values will be overwritten later by the panel/service flows.
                tz = ZoneInfo("America/Chicago")
                wd = next_workday(date.today())
                workday_date = wd.isoformat()
                deadline_ts = int(default_deadline_for(wd, tz=tz))

                await db.execute(
                    f"""
                    INSERT INTO {T.CHANNEL} (
                        {CH.GUILD_ID}, {CH.CHANNEL_ID},
                        {CH.REMINDER_OFFSETS}, {CH.WORKDAY_DATE},
                        {CH.DEADLINE_TS}, {CH.RSVP_MESSAGE_ID},
                        {CH.ROLLOVER_WEEKDAY}, {CH.ROLLOVER_TIME}
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        guild_id,
                        channel_id,
                        raw,
                        workday_date,
                        deadline_ts,
                        0,  # rsvp_message_id (unset)
                        int(DEFAULT_ROLLOVER_WEEKDAY),
                        str(DEFAULT_ROLLOVER_TIME),
                    ),
                )
            await db.commit()

    async def get_rsvp_message_id(self, *, guild_id: int, channel_id: int) -> Optional[int]:
        """
        Return the RSVP panel message ID stored for a channel.

        Parameters
        ----------
        guild_id : :class:`int`
            Discord guild (server) ID.
        channel_id : :class:`int`
            Discord text channel ID.

        Returns
        -------
        :class:`int` or :class:`None`
            Discord message ID of the RSVP panel, or :class:`None` if missing/unset.
        """
        async with self.connect() as db:  # type: ignore[attr-defined]
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"""
                SELECT {CH.RSVP_MESSAGE_ID}
                FROM {T.CHANNEL}
                WHERE {CH.GUILD_ID}=? AND {CH.CHANNEL_ID}=?
                """,
                (guild_id, channel_id),
            )
            row = await cur.fetchone()
            if not row:
                return None
            val = row[CH.RSVP_MESSAGE_ID]
            return int(val) if val else None

    async def update_workday_deadline(
        self,
        *,
        guild_id: int,
        channel_id: int,
        deadline_ts: int,
    ) -> int:
        """
        Update the stored RSVP deadline timestamp for a channel.

        Parameters
        ----------
        guild_id : :class:`int`
            Discord guild (server) ID.
        channel_id : :class:`int`
            Discord text channel ID.
        deadline_ts : :class:`int`
            Deadline as UTC epoch seconds.

        Returns
        -------
        :class:`int`
            Number of rows updated (0 if the channel row does not exist).
        """
        async with self.connect() as db:  # type: ignore[attr-defined]
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"""
                UPDATE {T.CHANNEL}
                SET {CH.DEADLINE_TS}=?
                WHERE {CH.GUILD_ID}=? AND {CH.CHANNEL_ID}=?
                """,
                (int(deadline_ts), guild_id, channel_id),
            )
            await db.commit()
            return int(cur.rowcount or 0)

    async def set_rollover_schedule(
        self,
        *,
        guild_id: int,
        channel_id: int,
        weekday: int,
        time_hhmm: str,
    ) -> None:
        """
        Set the weekly rollover schedule for a channel.

        Parameters
        ----------
        guild_id : :class:`int`
            Discord guild (server) ID.
        channel_id : :class:`int`
            Discord text channel ID.
        weekday : :class:`int`
            Rollover weekday in local time (Mon=0 .. Sun=6).
        time_hhmm : :class:`str`
            Rollover time in local time as ``HH:MM`` (24-hour).

        Returns
        -------
        :class:`None`
            Writes changes to the database.
        """
        async with self.connect() as db:  # type: ignore[attr-defined]
            db.row_factory = aiosqlite.Row
            await db.execute(
                f"""
                UPDATE {T.CHANNEL}
                SET {CH.ROLLOVER_WEEKDAY}=?, {CH.ROLLOVER_TIME}=?
                WHERE {CH.GUILD_ID}=? AND {CH.CHANNEL_ID}=?
                """,
                (int(weekday), str(time_hhmm), int(guild_id), int(channel_id)),
            )
            await db.commit()

    async def get_rollover_schedule(
        self,
        *,
        guild_id: int,
        channel_id: int,
    ) -> tuple[int, str]:
        """
        Return the rollover schedule for a channel.

        If the channel row is missing or the schedule fields are unset, this
        method falls back to :data:`DEFAULT_ROLLOVER_WEEKDAY` and
        :data:`DEFAULT_ROLLOVER_TIME`.

        Parameters
        ----------
        guild_id : :class:`int`
            Discord guild (server) ID.
        channel_id : :class:`int`
            Discord text channel ID.

        Returns
        -------
        :class:`tuple` (:class:`int`, :class:`str`)
            ``(weekday, time_hhmm)`` in local time where weekday is Mon=0 .. Sun=6.
        """
        async with self.connect() as db:  # type: ignore[attr-defined]
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"""
                SELECT {CH.ROLLOVER_WEEKDAY}, {CH.ROLLOVER_TIME}
                FROM {T.CHANNEL}
                WHERE {CH.GUILD_ID}=? AND {CH.CHANNEL_ID}=?
                """,
                (int(guild_id), int(channel_id)),
            )
            row = await cur.fetchone()
            if not row:
                return DEFAULT_ROLLOVER_WEEKDAY, DEFAULT_ROLLOVER_TIME

            wd = row[CH.ROLLOVER_WEEKDAY] if row[CH.ROLLOVER_WEEKDAY] else DEFAULT_ROLLOVER_WEEKDAY
            hhmm = row[CH.ROLLOVER_TIME] if row[CH.ROLLOVER_TIME] else DEFAULT_ROLLOVER_TIME
            return int(wd), str(hhmm)
