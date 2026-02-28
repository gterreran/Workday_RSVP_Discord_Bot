# tests/test_db_channels_ops.py

"""
Tests for ChannelsOps (per-channel scheduling state).

We focus on persistence behavior and normalization helpers:
- default fallbacks when the channel row is missing
- reminder offsets parsing and normalization
- rollover schedule defaulting
"""

from __future__ import annotations

import pytest

from rsvp_bot.config import DEFAULT_OFFSETS_MIN, DEFAULT_ROLLOVER_TIME, DEFAULT_ROLLOVER_WEEKDAY


@pytest.mark.asyncio
async def test_get_reminder_offsets_defaults_when_missing(db, ids):
    offsets = await db.get_reminder_offsets(guild_id=ids["guild_id"], channel_id=ids["channel_id"])
    assert offsets == sorted({int(x) for x in DEFAULT_OFFSETS_MIN.split(",")}, reverse=True)


@pytest.mark.asyncio
async def test_set_reminder_offsets_normalizes_and_falls_back(db, ids):
    # Includes duplicates, <=0, and unsorted input
    await db.set_reminder_offsets(
        guild_id=ids["guild_id"],
        channel_id=ids["channel_id"],
        offsets_min=[60, 0, -5, 60, 360],
    )
    got = await db.get_reminder_offsets(guild_id=ids["guild_id"], channel_id=ids["channel_id"])
    assert got == [360, 60]

    # Empty after filtering -> stored default
    await db.set_reminder_offsets(
        guild_id=ids["guild_id"],
        channel_id=ids["channel_id"],
        offsets_min=[0, -1],
    )
    got2 = await db.get_reminder_offsets(guild_id=ids["guild_id"], channel_id=ids["channel_id"])
    assert got2 == sorted({int(x) for x in DEFAULT_OFFSETS_MIN.split(",")}, reverse=True)


@pytest.mark.asyncio
async def test_rollover_schedule_defaults_when_missing(db, ids):
    wd, hhmm = await db.get_rollover_schedule(guild_id=ids["guild_id"], channel_id=ids["channel_id"])
    assert wd == DEFAULT_ROLLOVER_WEEKDAY
    assert hhmm == DEFAULT_ROLLOVER_TIME


@pytest.mark.asyncio
async def test_upsert_channel_and_getters(db, ids):
    await db.upsert_channel(
        guild_id=ids["guild_id"],
        channel_id=ids["channel_id"],
        reminder_offsets="60,360",
        workday_date="2026-02-28",
        deadline_ts=1700000000,
        rsvp_message_id=999,
        rollover_weekday=1,
        rollover_time="10:30",
    )

    assert await db.get_workday_date(guild_id=ids["guild_id"], channel_id=ids["channel_id"]) == "2026-02-28"
    assert await db.get_deadline(guild_id=ids["guild_id"], channel_id=ids["channel_id"]) == 1700000000
    assert await db.get_rsvp_message_id(guild_id=ids["guild_id"], channel_id=ids["channel_id"]) == 999

    # Offsets are normalized by getter (sorted unique desc)
    assert await db.get_reminder_offsets(guild_id=ids["guild_id"], channel_id=ids["channel_id"]) == [360, 60]

    # Rollover schedule is stored and returned
    wd, hhmm = await db.get_rollover_schedule(guild_id=ids["guild_id"], channel_id=ids["channel_id"])
    assert wd == 1
    assert hhmm == "10:30"
