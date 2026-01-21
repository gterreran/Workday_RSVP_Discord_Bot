from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import aiosqlite


SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS channels (
  guild_id              INTEGER NOT NULL,
  channel_id            INTEGER NOT NULL,
  timezone              TEXT NOT NULL,
  PRIMARY KEY (guild_id, channel_id)
);

CREATE TABLE IF NOT EXISTS directory (
  guild_id              INTEGER NOT NULL,
  channel_id            INTEGER NOT NULL,
  user_id               INTEGER NOT NULL,
  active                INTEGER NOT NULL DEFAULT 1,
  added_by              INTEGER,
  added_at_ts           INTEGER NOT NULL,
  PRIMARY KEY (guild_id, channel_id, user_id)
);

CREATE TABLE IF NOT EXISTS workdays (
  guild_id              INTEGER NOT NULL,
  channel_id            INTEGER NOT NULL,
  workday_date          TEXT NOT NULL,   -- YYYY-MM-DD
  deadline_ts           INTEGER NOT NULL, -- UTC timestamp
  rsvp_message_id       INTEGER NOT NULL,
  created_at_ts         INTEGER NOT NULL,
  PRIMARY KEY (guild_id, channel_id, workday_date)
);

CREATE TABLE IF NOT EXISTS rsvps (
  guild_id              INTEGER NOT NULL,
  channel_id            INTEGER NOT NULL,
  workday_date          TEXT NOT NULL,   -- YYYY-MM-DD
  user_id               INTEGER NOT NULL,
  status                TEXT NOT NULL,   -- yes|no|maybe
  note                  TEXT,
  updated_at_ts         INTEGER NOT NULL,
  PRIMARY KEY (guild_id, channel_id, workday_date, user_id)
);
"""


@dataclass(frozen=True)
class WorkdayRow:
    guild_id: int
    channel_id: int
    workday_date: str
    deadline_ts: int
    rsvp_message_id: int


class DB:
    def __init__(self, path: Path) -> None:
        self._path = path

    def connect(self) -> aiosqlite.Connection:
        return aiosqlite.connect(self._path.as_posix())

    async def init(self) -> None:
        async with self.connect() as db:
            db.row_factory = aiosqlite.Row
            await db.executescript(SCHEMA)
            await db.commit()

    async def upsert_channel(self, *, guild_id: int, channel_id: int, timezone: str) -> None:
        async with self.connect() as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                """
                INSERT INTO channels (guild_id, channel_id, timezone)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, channel_id) DO UPDATE SET timezone=excluded.timezone
                """,
                (guild_id, channel_id, timezone),
            )
            await db.commit()

    async def create_workday(
        self,
        *,
        guild_id: int,
        channel_id: int,
        workday_date: str,
        deadline_ts: int,
        rsvp_message_id: int,
        created_at_ts: int,
    ) -> None:
        async with self.connect() as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                """
                INSERT OR REPLACE INTO workdays
                  (guild_id, channel_id, workday_date, deadline_ts, rsvp_message_id, created_at_ts)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (guild_id, channel_id, workday_date, deadline_ts, rsvp_message_id, created_at_ts),
            )
            await db.commit()

    async def get_workday_for_channel(self, *, guild_id: int, channel_id: int, workday_date: str) -> Optional[WorkdayRow]:
        async with self.connect() as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT guild_id, channel_id, workday_date, deadline_ts, rsvp_message_id
                FROM workdays
                WHERE guild_id=? AND channel_id=? AND workday_date=?
                """,
                (guild_id, channel_id, workday_date),
            )
            row = await cur.fetchone()
            if not row:
                return None
            return WorkdayRow(**dict(row))

    async def set_rsvp(
        self,
        *,
        guild_id: int,
        channel_id: int,
        workday_date: str,
        user_id: int,
        status: str,
        updated_at_ts: int,
    ) -> None:
        async with self.connect() as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                """
                INSERT INTO rsvps (guild_id, channel_id, workday_date, user_id, status, updated_at_ts)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, channel_id, workday_date, user_id)
                DO UPDATE SET status=excluded.status, updated_at_ts=excluded.updated_at_ts
                """,
                (guild_id, channel_id, workday_date, user_id, status, updated_at_ts),
            )
            await db.commit()

    async def list_rsvps(self, *, guild_id: int, channel_id: int, workday_date: str) -> list[tuple[int, str]]:
        async with self.connect() as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT user_id, status
                FROM rsvps
                WHERE guild_id=? AND channel_id=? AND workday_date=?
                """,
                (guild_id, channel_id, workday_date),
            )
            rows = await cur.fetchall()
            return [(int(r["user_id"]), str(r["status"])) for r in rows]

    async def directory_add(self, *, guild_id: int, channel_id: int, user_id: int, added_by: int, added_at_ts: int) -> None:
        async with self.connect() as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                """
                INSERT INTO directory (guild_id, channel_id, user_id, active, added_by, added_at_ts)
                VALUES (?, ?, ?, 1, ?, ?)
                ON CONFLICT(guild_id, channel_id, user_id) DO UPDATE SET active=1
                """,
                (guild_id, channel_id, user_id, added_by, added_at_ts),
            )
            await db.commit()

    async def directory_list_active(self, *, guild_id: int, channel_id: int) -> list[int]:
        async with self.connect() as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT user_id
                FROM directory
                WHERE guild_id=? AND channel_id=? AND active=1
                """,
                (guild_id, channel_id),
            )
            rows = await cur.fetchall()
            return [int(r["user_id"]) for r in rows]
