# tests/test_db_reminders_ops.py

"""
Tests for ReminderOps (sent reminder deduplication).
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_reminder_dedupe_mark_and_clear(db, ids):
    gid = ids["guild_id"]
    cid = ids["channel_id"]
    wd = "2026-02-28"
    offset = 60

    assert await db.reminder_already_sent(guild_id=gid, channel_id=cid, workday_date=wd, offset_min=offset) is False

    await db.mark_reminder_sent(guild_id=gid, channel_id=cid, workday_date=wd, offset_min=offset, sent_at_ts=123)

    assert await db.reminder_already_sent(guild_id=gid, channel_id=cid, workday_date=wd, offset_min=offset) is True

    await db.clear_sent_reminders(guild_id=gid, channel_id=cid, workday_date=wd)
    assert await db.reminder_already_sent(guild_id=gid, channel_id=cid, workday_date=wd, offset_min=offset) is False
