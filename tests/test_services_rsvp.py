"""
Tests for RSVPService decision logic.

We keep Discord fully mocked:
- Fake Interaction object
- AsyncMock followups
- Real SQLite DB

These tests validate behavior without requiring a Discord connection.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from rsvp_bot.commands.ctx import CommandCtx
from rsvp_bot.models import WorkdayRow
from rsvp_bot.services.rsvp_service import RSVPService

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


class DummyResponse:
    """Minimal stand-in for interaction.response."""

    def __init__(self):
        self.send_modal = AsyncMock()
        self.defer = AsyncMock()


class DummyFollowup:
    """Minimal stand-in for interaction.followup."""

    def __init__(self):
        self.send = AsyncMock()


class DummyInteraction:
    """Minimal fake Discord Interaction."""

    def __init__(self, guild_id: int, channel_id: int, user_id: int):
        # Provide get_member(uid) used by _after_plan_submit() to build labels
        def _get_member(uid: int):
            return SimpleNamespace(id=uid, display_name=f"User {uid}")

        self.guild = SimpleNamespace(id=guild_id, get_member=_get_member)
        self.channel = SimpleNamespace(id=channel_id)  # not a discord.TextChannel
        self.user = SimpleNamespace(id=user_id)

        self.response = DummyResponse()
        self.followup = DummyFollowup()


def make_bot(db):
    """
    Create a fake bot with only the attributes RSVPService needs.

    Note: RSVPService.panel property expects bot.panel (not panel_service).
    """
    bot = SimpleNamespace()
    bot.db = db
    bot.panel = SimpleNamespace(refresh_panel=AsyncMock())
    return bot


async def seed_workday_row(db, guild_id: int, channel_id: int) -> WorkdayRow:
    """Create a minimal valid WorkdayRow and ensure channel state exists in DB."""
    await db.upsert_channel(
        guild_id=guild_id,
        channel_id=channel_id,
        reminder_offsets="60",
        workday_date="2026-02-28",
        deadline_ts=1700000000,
        rsvp_message_id=123,
        rollover_weekday=5,
        rollover_time="09:00",
    )
    return WorkdayRow(
        guild_id=guild_id,
        channel_id=channel_id,
        workday_date="2026-02-28",
        deadline_ts=1700000000,
        rsvp_message_id=123,
    )


@pytest.fixture()
def patch_get_ctx(monkeypatch):
    """
    Patch get_ctx used by RSVPService to avoid discord.TextChannel isinstance checks.

    RSVPService imports/uses get_ctx from its own module namespace, so we patch
    rsvp_bot.services.rsvp_service.get_ctx.
    """

    async def _fake_get_ctx(interaction, *, defer: bool = True, ephemeral: bool = True) -> CommandCtx:
        if defer:
            await interaction.response.defer(ephemeral=ephemeral)
        return CommandCtx(
            guild=interaction.guild,
            channel=interaction.channel,
            user=interaction.user,
        )

    monkeypatch.setattr("rsvp_bot.services.rsvp_service.get_ctx", _fake_get_ctx)


# ---------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_planning_status_writes_rsvp_and_refreshes(db, ids, patch_get_ctx):
    """
    Statuses like 'no' or 'maybe' should:
    - write RSVP immediately
    - refresh panel
    - send confirmation
    """
    gid = ids["guild_id"]
    cid = ids["channel_id"]
    uid = ids["user_a"]

    bot = make_bot(db)
    svc = RSVPService(bot)

    row = await seed_workday_row(db, gid, cid)
    interaction = DummyInteraction(gid, cid, uid)

    await svc.on_choice(interaction, status="no")

    got = await db.get_rsvp(guild_id=gid, channel_id=cid, workday_date=row.workday_date, user_id=uid)
    assert got is not None
    status, note = got
    assert status == "no"
    assert note is None

    bot.panel.refresh_panel.assert_awaited()
    interaction.followup.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_planning_status_opens_modal(db, ids, patch_get_ctx):
    """
    In this codebase, status 'yes'/'remote' triggers the plan modal immediately.
    """
    gid = ids["guild_id"]
    cid = ids["channel_id"]
    uid = ids["user_a"]

    bot = make_bot(db)
    svc = RSVPService(bot)

    row = await seed_workday_row(db, gid, cid)
    interaction = DummyInteraction(gid, cid, uid)

    await svc.on_choice(interaction, status="yes")

    interaction.response.send_modal.assert_awaited_once()
    interaction.followup.send.assert_not_awaited()

    assert await db.get_rsvp(guild_id=gid, channel_id=cid, workday_date=row.workday_date, user_id=uid) is None


@pytest.mark.asyncio
async def test_after_plan_submit_no_partner_candidates_sends_message(db, ids, patch_get_ctx):
    """
    After plan modal submit, RSVPService tries to build partner candidates from
    directory membership. If none exist, it sends an informative message.
    """
    gid = ids["guild_id"]
    cid = ids["channel_id"]
    uid = ids["user_a"]

    bot = make_bot(db)
    svc = RSVPService(bot) # type: ignore

    row = await seed_workday_row(db, gid, cid)
    interaction = DummyInteraction(gid, cid, uid)

    # Only the user in directory -> no candidates
    await db.directory_add(guild_id=gid, channel_id=cid, user_id=uid, added_by=999, added_at_ts=1)

    await svc._after_plan_submit(interaction, status="yes", note=None) # type: ignore

    got = await db.get_rsvp(guild_id=gid, channel_id=cid, workday_date=row.workday_date, user_id=uid)
    assert got is not None
    status, note = got
    assert status == "yes"
    assert note is None

    interaction.followup.send.assert_awaited_once()
    # Message is passed positionally in this codebase
    call = interaction.followup.send.call_args
    msg = ""
    if call.args:
        msg = str(call.args[0])
    else:
        msg = str(call.kwargs.get("content", ""))
    assert "directory" in msg.lower()

    bot.panel.refresh_panel.assert_awaited()


@pytest.mark.asyncio
async def test_after_plan_submit_with_candidates_sends_partner_picker(db, ids, patch_get_ctx):
    """
    If partner candidates exist, _after_plan_submit should send a followup with a View.
    """
    gid = ids["guild_id"]
    cid = ids["channel_id"]
    uid = ids["user_a"]

    bot = make_bot(db)
    svc = RSVPService(bot)

    row = await seed_workday_row(db, gid, cid)
    interaction = DummyInteraction(gid, cid, uid)

    # Seed directory with two users
    await db.directory_add(guild_id=gid, channel_id=cid, user_id=ids["user_a"], added_by=999, added_at_ts=1)
    await db.directory_add(guild_id=gid, channel_id=cid, user_id=ids["user_b"], added_by=999, added_at_ts=2)

    await svc._after_plan_submit(interaction, status="yes", note="bringing snacks")

    got = await db.get_rsvp(guild_id=gid, channel_id=cid, workday_date=row.workday_date, user_id=uid)
    assert got is not None
    status, note = got
    assert status == "yes"
    assert note == "bringing snacks"

    interaction.followup.send.assert_awaited_once()
    kwargs = interaction.followup.send.call_args.kwargs
    assert kwargs.get("view") is not None
    # content may be positional; ensure some human prompt exists either way
    call = interaction.followup.send.call_args
    if call.args:
        assert str(call.args[0]).strip()
    else:
        assert str(kwargs.get("content", "")).strip()
