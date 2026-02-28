# tests/test_db_init.py

"""
Tests for database initialization (schema creation).

These focus on the "DB.init()" contract: it should be safe to run repeatedly
and should create all expected tables.
"""

from __future__ import annotations

import pytest

from rsvp_bot.db.schema import Tables as T


@pytest.mark.asyncio
async def test_db_init_creates_tables(db):
    async with db.connect() as conn:
        cur = await conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        names = {row[0] for row in await cur.fetchall()}

    # SQLite may create internal tables (e.g. sqlite_sequence); we assert ours exist.
    assert T.CHANNEL in names
    assert T.DIRECTORY in names
    assert T.RSVPS in names
    assert T.SENT_REMINDERS in names
    assert T.WORK_PAIRS in names


@pytest.mark.asyncio
async def test_db_init_is_idempotent(tmp_path):
    from rsvp_bot.db import DB

    path = tmp_path / "idempotent.sqlite3"
    db = DB(path=path)
    await db.init()
    await db.init()  # should not raise
