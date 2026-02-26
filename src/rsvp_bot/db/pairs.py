# src/rsvp_bot/db/pairs.py

"""
Work partner relationship database operations
=============================================

Database access layer for storing and querying work partner relationships.

Partners represent optional collaboration links between users who plan to
work together on a given workday. These links are directional:

- A user selects one or more partners
- Each selection is stored independently
- Queries may interpret relationships as directed or inferred

This module defines :class:`PairOps`, a mixin-style class expected to be used
with a database implementation providing an async ``self.connect()`` method
returning an :class:`aiosqlite.Connection`.

Classes
-------

:class:`PairOps`
    Read/write operations for the ``work_pairs`` table.
"""

from __future__ import annotations

import aiosqlite

from .schema import Tables as T
from .schema import WorkPairsColumns as WP
    

class PairOps:
    """
    Operations for managing work partner relationships.

    Partner links are scoped by:

    - :class:`int` guild_id
    - :class:`int` channel_id
    - :class:`str` workday_date (ISO ``YYYY-MM-DD``)
    """

    async def replace_work_partners(
        self,
        *,
        guild_id: int,
        channel_id: int,
        workday_date: str,
        user_id: int,
        partner_ids: list[int],
        created_at_ts: int,
    ) -> None:
        """
        Replace all partner links for a user on a workday.

        Existing partner rows for the user are deleted and replaced with the
        provided list. The user is automatically excluded from their own
        partner list and duplicates are removed.

        Parameters
        ----------
        guild_id : :class:`int`
            Discord guild (server) ID.
        channel_id : :class:`int`
            Discord text channel ID.
        workday_date : :class:`str`
            Workday identifier (ISO ``YYYY-MM-DD``).
        user_id : :class:`int`
            User who owns the partner list.
        partner_ids : :class:`list` of :class:`int`
            Partner user IDs.
        created_at_ts : :class:`int`
            UTC epoch seconds when the relationship was recorded.

        Returns
        -------
        :class:`None`
            Writes changes to the database.
        """
        partner_ids = sorted(set(int(x) for x in partner_ids if int(x) != user_id))
        async with self.connect() as db:  # type: ignore[attr-defined]
            db.row_factory = aiosqlite.Row
            await db.execute(
                f"""
                DELETE FROM {T.WORK_PAIRS}
                WHERE {WP.GUILD_ID}=? AND {WP.CHANNEL_ID}=? AND {WP.WORKDAY_DATE}=? AND {WP.USER_ID}=?
                """,
                (guild_id, channel_id, workday_date, user_id),
            )
            for pid in partner_ids:
                await db.execute(
                    f"""
                    INSERT OR IGNORE INTO {T.WORK_PAIRS} ({WP.GUILD_ID}, {WP.CHANNEL_ID}, {WP.WORKDAY_DATE}, {WP.USER_ID}, {WP.PARTNER_ID}, {WP.CREATED_AT_TS})
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (guild_id, channel_id, workday_date, user_id, pid, created_at_ts),
                )
            await db.commit()

    async def get_dependent_users(
        self,
        *,
        guild_id: int,
        channel_id: int,
        workday_date: str,
        partner_id: int,
    ) -> list[int]:
        """
        Return users who selected a given partner.

        This is used to notify dependents when a partner changes their RSVP
        (e.g., switches to "Not attending").

        Parameters
        ----------
        guild_id : :class:`int`
            Discord guild (server) ID.
        channel_id : :class:`int`
            Discord text channel ID.
        workday_date : :class:`str`
            Workday identifier (ISO ``YYYY-MM-DD``).
        partner_id : :class:`int`
            User ID of the partner being referenced.

        Returns
        -------
        :class:`list` of :class:`int`
            User IDs who listed ``partner_id`` as a collaborator.
        """
        async with self.connect() as db:  # type: ignore[attr-defined]
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"""
                SELECT {WP.USER_ID}
                FROM {T.WORK_PAIRS}
                WHERE {WP.GUILD_ID}=? AND {WP.CHANNEL_ID}=? AND {WP.WORKDAY_DATE}=? AND {WP.PARTNER_ID}=?
                """,
                (guild_id, channel_id, workday_date, partner_id),
            )
            rows = await cur.fetchall()
            return [int(r[WP.USER_ID]) for r in rows]

    async def list_work_partners_map(
        self, *, guild_id: int, channel_id: int, workday_date: str
    ) -> dict[int, list[int]]:
        """
        Return a mapping of users to their partner lists.

        The mapping is normalized such that:

        - Keys are :class:`int` user IDs
        - Values are sorted unique :class:`list` of partner IDs

        Parameters
        ----------
        guild_id : :class:`int`
            Discord guild (server) ID.
        channel_id : :class:`int`
            Discord text channel ID.
        workday_date : :class:`str`
            Workday identifier (ISO ``YYYY-MM-DD``).

        Returns
        -------
        :class:`dict` of :class:`int` → :class:`list` of :class:`int`
            Mapping of each user to their selected partners.
        """
        async with self.connect() as db:  # type: ignore[attr-defined]
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"""
                SELECT {WP.USER_ID}, {WP.PARTNER_ID}
                FROM {T.WORK_PAIRS}
                WHERE {WP.GUILD_ID}=? AND {WP.CHANNEL_ID}=? AND {WP.WORKDAY_DATE}=?
                ORDER BY {WP.USER_ID}, {WP.PARTNER_ID}
                """,
                (guild_id, channel_id, workday_date),
            )
            rows = await cur.fetchall()

        out: dict[int, list[int]] = {}
        for r in rows:
            user_id = int(r[WP.USER_ID])
            partner_id = int(r[WP.PARTNER_ID])
            out.setdefault(user_id, []).append(partner_id)

        for k in list(out.keys()):
            out[k] = sorted(set(out[k]))
        return out

    async def clear_work_partners(self, *, guild_id: int, channel_id: int, workday_date: str) -> int:
        """
        Delete all partner relationships for a workday.

        Parameters
        ----------
        guild_id : :class:`int`
            Discord guild (server) ID.
        channel_id : :class:`int`
            Discord text channel ID.
        workday_date : :class:`str`
            Workday identifier (ISO ``YYYY-MM-DD``).

        Returns
        -------
        :class:`int`
            Number of deleted rows.
        """
        async with self.connect() as db:  # type: ignore[attr-defined]
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"""
                DELETE FROM {T.WORK_PAIRS}
                WHERE {WP.GUILD_ID}=? AND {WP.CHANNEL_ID}=? AND {WP.WORKDAY_DATE}=?
                """,
                (guild_id, channel_id, workday_date),
            )
            await db.commit()
            return int(cur.rowcount or 0)
