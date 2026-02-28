# tests/test_services_scheduler.py

"""
Tests for SchedulerService loops.

No production refactor required.

We run each @tasks.loop body exactly once by invoking the task coroutine:
    await SchedulerService.reminder_loop.coro(service)
    await SchedulerService.rollover_loop.coro(service)

Discord is fully faked:
- ctx comes from a monkeypatched _make_ctx
- ctx.channel.send is an AsyncMock
- panel methods are AsyncMocks

DB is real SQLite (db fixture).
"""

from __future__ import annotations

from datetime import datetime as _real_datetime
from datetime import timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from rsvp_bot.commands.ctx import CommandCtx
from rsvp_bot.services.scheduler_service import SchedulerService


class DummyChannel:
    """Minimal channel with send()."""

    def __init__(self, channel_id: int):
        self.id = channel_id
        self.send = AsyncMock()


def make_ctx(*, guild_id: int, channel: DummyChannel) -> CommandCtx:
    """Construct a CommandCtx with minimal guild/user placeholders."""
    guild = SimpleNamespace(id=guild_id)
    user = SimpleNamespace(id=999)
    return CommandCtx(guild=guild, channel=channel, user=user)


def make_bot(db):
    """Fake bot exposing only attributes SchedulerService touches."""
    bot = SimpleNamespace()
    bot.db = db
    bot.tz = timezone.utc
    bot.wait_until_ready = AsyncMock()
    bot.panel = SimpleNamespace(
        cleanup_panel=AsyncMock(),
        create_new_panel=AsyncMock(return_value=4242),
    )
    bot.rsvp = SimpleNamespace(on_choice=AsyncMock(), on_choice_with_plan=AsyncMock())
    bot.user = SimpleNamespace(id=999)
    bot.get_guild = lambda gid: None  # unused because we patch _make_ctx
    return bot


@pytest.mark.asyncio
async def test_reminder_loop_sends_and_marks_sent(db, ids, monkeypatch):
    """
    When within the 60-second send window and not already sent:
    - sends reminder mentioning only missing directory members
    - marks reminder as sent
    """
    gid = ids["guild_id"]
    cid = ids["channel_id"]
    workday = "2026-02-28"

    bot = make_bot(db)
    svc = SchedulerService(bot=bot, weekly_done=set())

    # Make deterministic "now" so send_at_ts == now.
    # Choose deadline_ts=4600 and offset=60 => send_at_ts = 4600 - 3600 = 1000.
    now_ts = 1000
    deadline_ts = 4600

    # Patch time.time() used in scheduler_service module
    import rsvp_bot.services.scheduler_service as sched_mod

    monkeypatch.setattr(sched_mod.time, "time", lambda: now_ts)

    # Patch _make_ctx to avoid discord.TextChannel/isinstance checks
    ch = DummyChannel(cid)
    ctx = make_ctx(guild_id=gid, channel=ch)
    monkeypatch.setattr(svc, "_make_ctx", lambda g, c: ctx)

    # Seed channel state and reminders
    await db.upsert_channel(
        guild_id=gid,
        channel_id=cid,
        reminder_offsets="60",
        workday_date=workday,
        deadline_ts=deadline_ts,
        rsvp_message_id=123,
        rollover_weekday=4,
        rollover_time="09:00",
    )

    # Directory contains two users
    await db.directory_add(guild_id=gid, channel_id=cid, user_id=ids["user_a"], added_by=999, added_at_ts=1)
    await db.directory_add(guild_id=gid, channel_id=cid, user_id=ids["user_b"], added_by=999, added_at_ts=2)

    # Only user_a RSVPed, so user_b is missing
    await db.set_rsvp(
        guild_id=gid,
        channel_id=cid,
        workday_date=workday,
        user_id=ids["user_a"],
        status="yes",
        note=None,
        updated_at_ts=1,
    )

    # Run loop body once
    await SchedulerService.reminder_loop.coro(svc)

    # Message sent once and mentions only missing user_b
    ch.send.assert_awaited_once()
    sent_text = str(ch.send.call_args.args[0])
    assert f"<@{ids['user_b']}>" in sent_text
    assert f"<@{ids['user_a']}>" not in sent_text

    # Marked as sent
    assert await db.reminder_already_sent(
        guild_id=gid,
        channel_id=cid,
        workday_date=workday,
        offset_min=60,
    ) is True


@pytest.mark.asyncio
async def test_reminder_loop_records_sent_when_no_missing_users(db, ids, monkeypatch):
    """
    If everyone RSVPed, SchedulerService should still mark the reminder as sent
    (and not send a message).
    """
    gid = ids["guild_id"]
    cid = ids["channel_id"]
    workday = "2026-02-28"

    bot = make_bot(db)
    svc = SchedulerService(bot=bot, weekly_done=set())

    now_ts = 1000
    deadline_ts = 4600

    import rsvp_bot.services.scheduler_service as sched_mod

    monkeypatch.setattr(sched_mod.time, "time", lambda: now_ts)

    ch = DummyChannel(cid)
    ctx = make_ctx(guild_id=gid, channel=ch)
    monkeypatch.setattr(svc, "_make_ctx", lambda g, c: ctx)

    await db.upsert_channel(
        guild_id=gid,
        channel_id=cid,
        reminder_offsets="60",
        workday_date=workday,
        deadline_ts=deadline_ts,
        rsvp_message_id=123,
        rollover_weekday=4,
        rollover_time="09:00",
    )

    # Directory has one user and they already RSVPed
    await db.directory_add(guild_id=gid, channel_id=cid, user_id=ids["user_a"], added_by=999, added_at_ts=1)
    await db.set_rsvp(
        guild_id=gid,
        channel_id=cid,
        workday_date=workday,
        user_id=ids["user_a"],
        status="no",
        note=None,
        updated_at_ts=1,
    )

    await SchedulerService.reminder_loop.coro(svc)

    ch.send.assert_not_awaited()
    assert await db.reminder_already_sent(
        guild_id=gid,
        channel_id=cid,
        workday_date=workday,
        offset_min=60,
    ) is True


@pytest.mark.asyncio
async def test_rollover_loop_runs_once_and_updates_channel_state(db, ids, monkeypatch):
    """
    When now matches rollover schedule exactly:
    - calls panel.cleanup_panel
    - calls panel.create_new_panel
    - upserts channel with new workday_date and new rsvp_message_id
    - weekly_done prevents second run on same date
    """
    gid = ids["guild_id"]
    cid = ids["channel_id"]

    bot = make_bot(db)
    svc = SchedulerService(bot=bot, weekly_done=set())

    # Ensure loop thinks it's Friday 09:00
    now = _real_datetime(2026, 2, 27, 9, 0, tzinfo=timezone.utc)  # Friday

    # Patch datetime.now used in scheduler_service module (not builtins)
    import rsvp_bot.services.scheduler_service as sched_mod

    class _FakeDateTime:
        @staticmethod
        def now(tz):
            return now

        @staticmethod
        def fromisoformat(s: str):
            return _real_datetime.fromisoformat(s)

    monkeypatch.setattr(sched_mod, "datetime", _FakeDateTime)

    # Patch _make_ctx
    ch = DummyChannel(cid)
    ctx = make_ctx(guild_id=gid, channel=ch)
    monkeypatch.setattr(svc, "_make_ctx", lambda g, c: ctx)

    # Seed stored workday_date so "now.date() < old_date" check doesn't skip.
    # Use same date as now or earlier.
    await db.upsert_channel(
        guild_id=gid,
        channel_id=cid,
        reminder_offsets="60",
        workday_date="2026-02-27",
        deadline_ts=1700000000,
        rsvp_message_id=111,
        rollover_weekday=4,      # Friday
        rollover_time="09:00",
    )

    # Run loop once
    await SchedulerService.rollover_loop.coro(svc)

    bot.panel.cleanup_panel.assert_awaited_once()
    bot.panel.create_new_panel.assert_awaited_once()

    # rsvp_message_id updated
    new_mid = await db.get_rsvp_message_id(guild_id=gid, channel_id=cid)
    assert int(new_mid) == 4242

    # Guard prevents running again same day
    await SchedulerService.rollover_loop.coro(svc)
    assert bot.panel.create_new_panel.await_count == 1
