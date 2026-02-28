# tests/test_db_rsvps_ops.py

"""
Tests for RSVPOps.

We keep ordering assertions minimal because SQL queries do not specify ORDER BY;
tests sort results where needed.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_set_and_get_rsvp(db, ids):
    gid = ids["guild_id"]
    cid = ids["channel_id"]
    wd = "2026-02-28"
    ua = ids["user_a"]

    await db.set_rsvp(
        guild_id=gid,
        channel_id=cid,
        workday_date=wd,
        user_id=ua,
        status="yes",
        note="bringing snacks",
        updated_at_ts=10,
    )

    got = await db.get_rsvp(guild_id=gid, channel_id=cid, workday_date=wd, user_id=ua)
    assert got is not None
    status, note = got
    assert status == "yes"
    assert note == "bringing snacks"


@pytest.mark.asyncio
async def test_list_rsvps_and_clear(db, ids):
    gid = ids["guild_id"]
    cid = ids["channel_id"]
    wd = "2026-02-28"

    await db.set_rsvp(guild_id=gid, channel_id=cid, workday_date=wd, user_id=ids["user_a"], status="yes", note=None, updated_at_ts=1)
    await db.set_rsvp(guild_id=gid, channel_id=cid, workday_date=wd, user_id=ids["user_b"], status="no", note="can't", updated_at_ts=2)

    rows = await db.list_rsvps(guild_id=gid, channel_id=cid, workday_date=wd)
    assert sorted(rows) == sorted([(ids["user_a"], "yes"), (ids["user_b"], "no")])

    rows_notes = await db.list_rsvps_with_notes(guild_id=gid, channel_id=cid, workday_date=wd)
    by_uid = {uid: (status, note) for uid, status, note in rows_notes}
    assert by_uid[ids["user_a"]][0] == "yes"
    assert by_uid[ids["user_b"]] == ("no", "can't")

    await db.clear_rsvps(guild_id=gid, channel_id=cid, workday_date=wd)
    assert await db.list_rsvps(guild_id=gid, channel_id=cid, workday_date=wd) == []
