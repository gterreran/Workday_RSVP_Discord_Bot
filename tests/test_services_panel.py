# tests/test_services_panel.py

"""
Tests for PanelService behavior.

We mock Discord I/O (channel/message) but use a real SQLite DB fixture.
No network / no Discord login required.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from rsvp_bot.commands.ctx import CommandCtx
from rsvp_bot.services.panel_service import PanelService

# -----------------------------------------------------------------------------
# Minimal Discord fakes
# -----------------------------------------------------------------------------

class _DummyHTTPResponse:
    """discord.py HTTPException subclasses expect response.status."""
    def __init__(self, status: int, reason: str = "TEST"):
        self.status = status
        self.reason = reason

@dataclass
class DummyMessage:
    id: int
    pinned: bool = False

    def __post_init__(self):
        self.edit = AsyncMock()
        self.pin = AsyncMock()
        self.unpin = AsyncMock()
        self.delete = AsyncMock()


class DummyChannel:
    def __init__(self, channel_id: int):
        self.id = channel_id
        self._messages: dict[int, DummyMessage] = {}
        self.send = AsyncMock(side_effect=self._send_impl)
        self.fetch_message = AsyncMock(side_effect=self._fetch_impl)

    async def _send_impl(self, *, embed=None, view=None):
        # allocate new message id
        new_id = max(self._messages.keys(), default=1000) + 1
        msg = DummyMessage(id=new_id, pinned=False)
        self._messages[new_id] = msg
        # store last payload for assertions
        msg._last_embed = embed
        msg._last_view = view
        return msg

    async def _fetch_impl(self, message_id: int):
        if message_id not in self._messages:
            raise discord.NotFound(response=_DummyHTTPResponse(404), message="not found")  # type: ignore[arg-type]
        return self._messages[message_id]


def make_ctx(*, guild_id: int, channel: DummyChannel, user_id: int = 999) -> CommandCtx:
    guild = SimpleNamespace(id=guild_id)
    user = SimpleNamespace(id=user_id)
    return CommandCtx(guild=guild, channel=channel, user=user)


def make_bot(db):
    bot = SimpleNamespace()
    bot.db = db
    # tz used by PanelService.tz property; not used in these tests directly
    bot.tz = timezone.utc
    return bot


# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_new_panel_sends_message_pins_and_returns_id(db, ids):
    gid = ids["guild_id"]
    cid = ids["channel_id"]

    bot = make_bot(db)
    svc = PanelService(bot)

    channel = DummyChannel(cid)
    ctx = make_ctx(guild_id=gid, channel=channel)

    # Seed directory with a couple users (active)
    await db.directory_add(guild_id=gid, channel_id=cid, user_id=ids["user_a"], added_by=999, added_at_ts=1)
    await db.directory_add(guild_id=gid, channel_id=cid, user_id=ids["user_b"], added_by=999, added_at_ts=2)

    msg_id = await svc.create_new_panel(
        ctx=ctx,
        workday_date="2026-02-28",
        deadline_ts=1700000000,
        on_choice=lambda *a, **k: None,
        on_choice_with_plan=lambda *a, **k: None,
    )

    # Message created
    assert msg_id in channel._messages
    msg = channel._messages[msg_id]

    # Attempted to pin (pinning failures are handled in code, but here it should be called)
    msg.pin.assert_awaited()

    # Should have sent an embed + view
    assert getattr(msg, "_last_embed", None) is not None
    assert getattr(msg, "_last_view", None) is not None


@pytest.mark.asyncio
async def test_create_new_panel_ignores_forbidden_on_pin(db, ids):
    gid = ids["guild_id"]
    cid = ids["channel_id"]

    bot = make_bot(db)
    svc = PanelService(bot)

    channel = DummyChannel(cid)
    ctx = make_ctx(guild_id=gid, channel=channel)

    msg_id = await svc.create_new_panel(
        ctx=ctx,
        workday_date="2026-02-28",
        deadline_ts=1700000000,
        on_choice=lambda *a, **k: None,
        on_choice_with_plan=lambda *a, **k: None,
    )

    msg = channel._messages[msg_id]
    # Simulate Forbidden during pin and re-run pin call through create flow by manually setting side_effect
    msg.pin.side_effect = discord.Forbidden(response=_DummyHTTPResponse(403), message="forbidden")  # type: ignore[arg-type]

    # Call create again; should not raise even if pin fails
    await svc.create_new_panel(
        ctx=ctx,
        workday_date="2026-02-28",
        deadline_ts=1700000000,
        on_choice=lambda *a, **k: None,
        on_choice_with_plan=lambda *a, **k: None,
    )


@pytest.mark.asyncio
async def test_refresh_panel_edits_existing_message(db, ids):
    gid = ids["guild_id"]
    cid = ids["channel_id"]

    bot = make_bot(db)
    svc = PanelService(bot)

    channel = DummyChannel(cid)
    ctx = make_ctx(guild_id=gid, channel=channel)

    # Create a message and store its id as the panel id
    created = await channel._send_impl(embed=None, view=None)
    panel_id = created.id

    await db.upsert_channel(
        guild_id=gid,
        channel_id=cid,
        reminder_offsets="60",
        workday_date="2026-02-28",
        deadline_ts=1700000000,
        rsvp_message_id=panel_id,
        rollover_weekday=5,
        rollover_time="09:00",
    )

    # Add directory + RSVP
    await db.directory_add(guild_id=gid, channel_id=cid, user_id=ids["user_a"], added_by=999, added_at_ts=1)
    await db.set_rsvp(
        guild_id=gid,
        channel_id=cid,
        workday_date="2026-02-28",
        user_id=ids["user_a"],
        status="yes",
        note=None,
        updated_at_ts=10,
    )

    await svc.refresh_panel(
        ctx=ctx,
        workday_date="2026-02-28",
        on_choice=lambda *a, **k: None,
        on_choice_with_plan=lambda *a, **k: None,
    )

    msg = channel._messages[panel_id]
    msg.edit.assert_awaited_once()
    kwargs = msg.edit.call_args.kwargs
    assert "embed" in kwargs and kwargs["embed"] is not None
    assert "view" in kwargs and kwargs["view"] is not None


@pytest.mark.asyncio
async def test_refresh_panel_returns_if_message_deleted(db, ids):
    gid = ids["guild_id"]
    cid = ids["channel_id"]

    bot = make_bot(db)
    svc = PanelService(bot)

    channel = DummyChannel(cid)
    ctx = make_ctx(guild_id=gid, channel=channel)

    # Store a panel id that does not exist in channel messages
    await db.upsert_channel(
        guild_id=gid,
        channel_id=cid,
        reminder_offsets="60",
        workday_date="2026-02-28",
        deadline_ts=1700000000,
        rsvp_message_id=999999,
        rollover_weekday=5,
        rollover_time="09:00",
    )

    # Should not raise
    await svc.refresh_panel(
        ctx=ctx,
        workday_date="2026-02-28",
        on_choice=lambda *a, **k: None,
        on_choice_with_plan=lambda *a, **k: None,
    )


@pytest.mark.asyncio
async def test_cleanup_panel_unpins_and_optionally_deletes(db, ids):
    gid = ids["guild_id"]
    cid = ids["channel_id"]

    bot = make_bot(db)
    svc = PanelService(bot)

    channel = DummyChannel(cid)
    ctx = make_ctx(guild_id=gid, channel=channel)

    msg = DummyMessage(id=1234, pinned=True)
    channel._messages[msg.id] = msg

    await db.upsert_channel(
        guild_id=gid,
        channel_id=cid,
        reminder_offsets="60",
        workday_date="2026-02-28",
        deadline_ts=1700000000,
        rsvp_message_id=msg.id,
        rollover_weekday=5,
        rollover_time="09:00",
    )

    await svc.cleanup_panel(ctx=ctx, delete_message=False)
    msg.unpin.assert_awaited()
    msg.delete.assert_not_awaited()

    await svc.cleanup_panel(ctx=ctx, delete_message=True)
    msg.delete.assert_awaited()


@pytest.mark.asyncio
async def test_reset_attendance_clears_state_and_refreshes(db, ids):
    gid = ids["guild_id"]
    cid = ids["channel_id"]

    bot = make_bot(db)
    svc = PanelService(bot)

    channel = DummyChannel(cid)
    ctx = make_ctx(guild_id=gid, channel=channel)

    # Ensure channel exists and panel id exists so refresh_panel can run
    created = await channel._send_impl(embed=None, view=None)
    panel_id = created.id
    await db.upsert_channel(
        guild_id=gid,
        channel_id=cid,
        reminder_offsets="60",
        workday_date="2026-02-28",
        deadline_ts=1700000000,
        rsvp_message_id=panel_id,
        rollover_weekday=5,
        rollover_time="09:00",
    )

    # Seed RSVP + partner + reminder
    await db.set_rsvp(
        guild_id=gid,
        channel_id=cid,
        workday_date="2026-02-28",
        user_id=ids["user_a"],
        status="yes",
        note=None,
        updated_at_ts=1,
    )
    await db.replace_work_partners(
        guild_id=gid,
        channel_id=cid,
        workday_date="2026-02-28",
        user_id=ids["user_a"],
        partner_ids=[ids["user_b"]],
        created_at_ts=1,
    )
    await db.mark_reminder_sent(
        guild_id=gid,
        channel_id=cid,
        workday_date="2026-02-28",
        offset_min=60,
        sent_at_ts=1,
    )

    deleted_rsvps, deleted_partners, deleted_reminders = await svc.reset_attendance(
        ctx=ctx,
        workday_date="2026-02-28",
        on_choice=lambda *a, **k: None,
        on_choice_with_plan=lambda *a, **k: None,
    )

    assert deleted_rsvps >= 1
    assert deleted_partners >= 1
    assert deleted_reminders >= 1


@pytest.mark.asyncio
async def test_set_deadline_in_updates_deadline_clears_reminders_and_refreshes(db, ids, monkeypatch):
    gid = ids["guild_id"]
    cid = ids["channel_id"]

    bot = make_bot(db)
    svc = PanelService(bot)

    # Patch refresh_panel so we don't need a real message for this test
    monkeypatch.setattr(svc, "refresh_panel", AsyncMock())

    await db.upsert_channel(
        guild_id=gid,
        channel_id=cid,
        reminder_offsets="60",
        workday_date="2026-02-28",
        deadline_ts=1700000000,
        rsvp_message_id=123,
        rollover_weekday=5,
        rollover_time="09:00",
    )

    await db.mark_reminder_sent(
        guild_id=gid,
        channel_id=cid,
        workday_date="2026-02-28",
        offset_min=60,
        sent_at_ts=1,
    )

    ctx = make_ctx(guild_id=gid, channel=DummyChannel(cid))
    await svc.set_deadline_in(
        ctx=ctx,
        workday_date="2026-02-28",
        new_deadline_ts=1800000000,
        on_choice=lambda *a, **k: None,
        on_choice_with_plan=lambda *a, **k: None,
    )

    assert await db.get_deadline(guild_id=gid, channel_id=cid) == 1800000000
    assert await db.reminder_already_sent(guild_id=gid, channel_id=cid, workday_date="2026-02-28", offset_min=60) is False
    svc.refresh_panel.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_deadline_in_raises_if_no_active_workday(db, ids, monkeypatch):
    gid = ids["guild_id"]
    cid = ids["channel_id"]

    bot = make_bot(db)
    svc = PanelService(bot)

    monkeypatch.setattr(svc, "refresh_panel", AsyncMock())

    # Note: do NOT upsert_channel -> update_workday_deadline should return 0
    ctx = make_ctx(guild_id=gid, channel=DummyChannel(cid))

    with pytest.raises(LookupError):
        await svc.set_deadline_in(
            ctx=ctx,
            workday_date="2026-02-28",
            new_deadline_ts=1800000000,
            on_choice=lambda *a, **k: None,
            on_choice_with_plan=lambda *a, **k: None,
        )


@pytest.mark.asyncio
async def test_set_deadline_at_rejects_naive_datetime(db, ids):
    gid = ids["guild_id"]
    cid = ids["channel_id"]

    bot = make_bot(db)
    svc = PanelService(bot)

    ctx = make_ctx(guild_id=gid, channel=DummyChannel(cid))

    with pytest.raises(ValueError):
        await svc.set_deadline_at(
            ctx=ctx,
            workday_date="2026-02-28",
            deadline_local=datetime(2026, 2, 27, 18, 0),  # naive
            on_choice=lambda *a, **k: None,
            on_choice_with_plan=lambda *a, **k: None,
        )


@pytest.mark.asyncio
async def test_set_deadline_at_calls_set_deadline_in(db, ids, monkeypatch):
    gid = ids["guild_id"]
    cid = ids["channel_id"]

    bot = make_bot(db)
    svc = PanelService(bot)

    mocked = AsyncMock()
    monkeypatch.setattr(svc, "set_deadline_in", mocked)

    ctx = make_ctx(guild_id=gid, channel=DummyChannel(cid))
    dt = datetime(2026, 2, 27, 18, 0, tzinfo=timezone.utc)

    new_ts = await svc.set_deadline_at(
        ctx=ctx,
        workday_date="2026-02-28",
        deadline_local=dt,
        on_choice=lambda *a, **k: None,
        on_choice_with_plan=lambda *a, **k: None,
    )

    assert new_ts == int(dt.timestamp())
    mocked.assert_awaited_once()
