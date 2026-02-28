# tests/test_db_directory_ops.py

"""
Tests for DirectoryOps.

Directory membership is soft-deleted via the "active" flag.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_directory_add_list_remove_and_readd(db, ids):
    gid = ids["guild_id"]
    cid = ids["channel_id"]
    ua = ids["user_a"]
    ub = ids["user_b"]

    # Empty to start
    assert await db.directory_list_active(guild_id=gid, channel_id=cid) == []

    # Add two users
    await db.directory_add(guild_id=gid, channel_id=cid, user_id=ua, added_by=999, added_at_ts=1)
    await db.directory_add(guild_id=gid, channel_id=cid, user_id=ub, added_by=999, added_at_ts=2)
    assert await db.directory_list_active(guild_id=gid, channel_id=cid) == [ua, ub]

    # Remove one -> no longer active
    await db.directory_remove(guild_id=gid, channel_id=cid, user_id=ua)
    assert await db.directory_list_active(guild_id=gid, channel_id=cid) == [ub]

    # Re-add should reactivate
    await db.directory_add(guild_id=gid, channel_id=cid, user_id=ua, added_by=999, added_at_ts=3)
    assert await db.directory_list_active(guild_id=gid, channel_id=cid) == [ua, ub]
