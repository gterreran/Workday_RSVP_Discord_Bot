# rsvp_bot/db.py

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import aiosqlite

DEFAULT_OFFSETS_MIN = "2880,1440,360,60"  # 48h, 24h, 6h, 1h

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

CREATE TABLE IF NOT EXISTS channel_settings (
  guild_id            INTEGER NOT NULL,
  channel_id          INTEGER NOT NULL,
  reminder_offsets    TEXT NOT NULL,   -- comma-separated minutes, e.g. "2880,1440,360,60"
  PRIMARY KEY (guild_id, channel_id)
);

CREATE TABLE IF NOT EXISTS sent_reminders (
  guild_id            INTEGER NOT NULL,
  channel_id          INTEGER NOT NULL,
  workday_date        TEXT NOT NULL,
  offset_min          INTEGER NOT NULL,
  sent_at_ts          INTEGER NOT NULL,
  PRIMARY KEY (guild_id, channel_id, workday_date, offset_min)
);

CREATE TABLE IF NOT EXISTS work_pairs (
  guild_id      INTEGER NOT NULL,
  channel_id    INTEGER NOT NULL,
  workday_date  TEXT NOT NULL,
  user_id       INTEGER NOT NULL,  -- the person who wrote the plan
  partner_id    INTEGER NOT NULL,  -- the person they plan to work with
  created_at_ts INTEGER NOT NULL,
  PRIMARY KEY (guild_id, channel_id, workday_date, user_id, partner_id)
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
        note: str | None,
        updated_at_ts: int,
    ) -> None:
        async with self.connect() as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                """
                INSERT INTO rsvps (guild_id, channel_id, workday_date, user_id, status, note, updated_at_ts)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, channel_id, workday_date, user_id)
                DO UPDATE SET
                status=excluded.status,
                note=excluded.note,
                updated_at_ts=excluded.updated_at_ts
                """,
                (guild_id, channel_id, workday_date, user_id, status, note, updated_at_ts),
            )
            await db.commit()

    async def list_rsvps(self, *, guild_id: int, channel_id: int, workday_date: str) -> list[tuple[int, str]]:
        async with self.connect() as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT user_id, status, note
                FROM rsvps
                WHERE guild_id=? AND channel_id=? AND workday_date=?
                """,
                (guild_id, channel_id, workday_date),
            )
            rows = await cur.fetchall()
            return [(int(r["user_id"]), str(r["status"])) for r in rows]

    async def list_rsvps_with_notes(self, *, guild_id: int, channel_id: int, workday_date: str) -> list[tuple[int, str, str | None]]:
        async with self.connect() as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT user_id, status, note
                FROM rsvps
                WHERE guild_id=? AND channel_id=? AND workday_date=?
                """,
                (guild_id, channel_id, workday_date),
            )
            rows = await cur.fetchall()
            return [(int(r["user_id"]), str(r["status"]), (str(r["note"]) if r["note"] is not None else None)) for r in rows]


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
        
    async def directory_remove(self, *, guild_id: int, channel_id: int, user_id: int) -> None:
        async with self.connect() as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                """
                UPDATE directory
                SET active=0
                WHERE guild_id=? AND channel_id=? AND user_id=?
                """,
                (guild_id, channel_id, user_id),
            )
            await db.commit()


    async def ensure_settings(self, *, guild_id: int, channel_id: int) -> None:
        async with self.connect() as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                """
                INSERT OR IGNORE INTO channel_settings (guild_id, channel_id, reminder_offsets)
                VALUES (?, ?, ?)
                """,
                (guild_id, channel_id, DEFAULT_OFFSETS_MIN),
            )
            await db.commit()


    async def get_reminder_offsets(self, *, guild_id: int, channel_id: int) -> list[int]:
        async with self.connect() as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT reminder_offsets
                FROM channel_settings
                WHERE guild_id=? AND channel_id=?
                """,
                (guild_id, channel_id),
            )
            row = await cur.fetchone()
            if not row:
                return [2880, 1440, 360, 60]
            raw = str(row["reminder_offsets"]).strip()
            if not raw:
                return [2880, 1440, 360, 60]
            out: list[int] = []
            for part in raw.split(","):
                part = part.strip()
                if not part:
                    continue
                out.append(int(part))
            return sorted(set(out), reverse=True)


    async def set_reminder_offsets(self, *, guild_id: int, channel_id: int, offsets_min: list[int]) -> None:
        offsets_min = sorted(set(int(x) for x in offsets_min if int(x) > 0), reverse=True)
        raw = ",".join(str(x) for x in offsets_min) if offsets_min else DEFAULT_OFFSETS_MIN
        async with self.connect() as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                """
                INSERT INTO channel_settings (guild_id, channel_id, reminder_offsets)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, channel_id) DO UPDATE SET reminder_offsets=excluded.reminder_offsets
                """,
                (guild_id, channel_id, raw),
            )
            await db.commit()


    async def reminder_already_sent(
        self, *, guild_id: int, channel_id: int, workday_date: str, offset_min: int
    ) -> bool:
        async with self.connect() as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT 1
                FROM sent_reminders
                WHERE guild_id=? AND channel_id=? AND workday_date=? AND offset_min=?
                """,
                (guild_id, channel_id, workday_date, offset_min),
            )
            row = await cur.fetchone()
            return row is not None


    async def mark_reminder_sent(
        self, *, guild_id: int, channel_id: int, workday_date: str, offset_min: int, sent_at_ts: int
    ) -> None:
        async with self.connect() as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                """
                INSERT OR IGNORE INTO sent_reminders (guild_id, channel_id, workday_date, offset_min, sent_at_ts)
                VALUES (?, ?, ?, ?, ?)
                """,
                (guild_id, channel_id, workday_date, offset_min, sent_at_ts),
            )
            await db.commit()


    async def clear_rsvps(self, *, guild_id: int, channel_id: int, workday_date: str) -> int:
        async with self.connect() as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                DELETE FROM rsvps
                WHERE guild_id=? AND channel_id=? AND workday_date=?
                """,
                (guild_id, channel_id, workday_date),
            )
            await db.commit()
            return cur.rowcount or 0


    async def clear_sent_reminders(self, *, guild_id: int, channel_id: int, workday_date: str) -> int:
        async with self.connect() as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                DELETE FROM sent_reminders
                WHERE guild_id=? AND channel_id=? AND workday_date=?
                """,
                (guild_id, channel_id, workday_date),
            )
            await db.commit()
            return cur.rowcount or 0
        
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
        partner_ids = sorted(set(int(x) for x in partner_ids if int(x) != user_id))
        async with self.connect() as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                """
                DELETE FROM work_pairs
                WHERE guild_id=? AND channel_id=? AND workday_date=? AND user_id=?
                """,
                (guild_id, channel_id, workday_date, user_id),
            )
            for pid in partner_ids:
                await db.execute(
                    """
                    INSERT OR IGNORE INTO work_pairs (guild_id, channel_id, workday_date, user_id, partner_id, created_at_ts)
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
        """Return user_ids who listed partner_id as someone they plan to work with."""
        async with self.connect() as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT user_id
                FROM work_pairs
                WHERE guild_id=? AND channel_id=? AND workday_date=? AND partner_id=?
                """,
                (guild_id, channel_id, workday_date, partner_id),
            )
            rows = await cur.fetchall()
            return [int(r["user_id"]) for r in rows]
    
    async def get_rsvp(self, *, guild_id: int, channel_id: int, workday_date: str, user_id: int) -> tuple[str, str | None] | None:
        async with self.connect() as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT status, note
                FROM rsvps
                WHERE guild_id=? AND channel_id=? AND workday_date=? AND user_id=?
                """,
                (guild_id, channel_id, workday_date, user_id),
            )
            row = await cur.fetchone()
            if not row:
                return None
            return (str(row["status"]), (str(row["note"]) if row["note"] is not None else None))
        
    
    async def list_work_partners_map(self, *, guild_id: int, channel_id: int, workday_date: str) -> dict[int, list[int]]:
        """
        Return mapping user_id -> sorted list of partner_ids for the given workday.
        """
        async with self.connect() as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT user_id, partner_id
                FROM work_pairs
                WHERE guild_id=? AND channel_id=? AND workday_date=?
                ORDER BY user_id, partner_id
                """,
                (guild_id, channel_id, workday_date),
            )
            rows = await cur.fetchall()

        out: dict[int, list[int]] = {}
        for r in rows:
            user_id = int(r["user_id"])
            partner_id = int(r["partner_id"])
            out.setdefault(user_id, []).append(partner_id)

        # de-dupe + sort
        for k in list(out.keys()):
            out[k] = sorted(set(out[k]))
        return out

    async def clear_work_partners(self, *, guild_id: int, channel_id: int, workday_date: str) -> int:
        async with self.connect() as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                DELETE FROM work_pairs
                WHERE guild_id=? AND channel_id=? AND workday_date=?
                """,
                (guild_id, channel_id, workday_date),
            )
            await db.commit()
            return int(cur.rowcount or 0)
