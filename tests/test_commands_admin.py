# tests/test_commands_admin.py

"""Tests for admin command handlers.

We test the *handler functions* (e.g. ``setup_cmd``) rather than Discord command
registration. Discord interactions are fully mocked; the DB is real.
"""

from __future__ import annotations

from datetime import date, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from rsvp_bot.commands import admin as admin_mod
from rsvp_bot.commands.ctx import CommandCtx


class DummyResponse:
    def __init__(self):
        self.defer = AsyncMock()
        self.send_message = AsyncMock()


class DummyFollowup:
    def __init__(self):
        self.send = AsyncMock()


class DummyUser:
    def __init__(self, user_id: int):
        self.id = user_id


class DummyInteraction:
    def __init__(self, *, guild_id: int, channel_id: int, user_id: int):
        self.guild = SimpleNamespace(id=guild_id)
        self.channel = SimpleNamespace(id=channel_id)
        self.user = DummyUser(user_id)
        self.response = DummyResponse()
        self.followup = DummyFollowup()


@pytest.fixture()
def bot(db):
    """Fake bot with DB + mocked services."""
    fake = SimpleNamespace()
    fake.db = db
    fake.tz = timezone.utc
    fake.rsvp = SimpleNamespace(on_choice=AsyncMock(), on_choice_with_plan=AsyncMock())
    fake.panel = SimpleNamespace(
        create_new_panel=AsyncMock(return_value=12345),
        refresh_panel=AsyncMock(),
        reset_attendance=AsyncMock(return_value=(3, 2, 1)),
    )

    # CommandTree is only used by rsvp_commands_cmd
    class _Cmd:
        def __init__(self, name: str, description: str):
            self.name = name
            self.description = description

    fake.tree = SimpleNamespace(
        get_commands=lambda guild=None: [
            _Cmd("setup", "Create or reset"),
            _Cmd("summary", "Show summary"),
        ]
        if guild is not None
        else [_Cmd("setup", "Create or reset")]
    )

    return fake


@pytest.fixture()
def patch_get_ctx(monkeypatch):
    """Patch get_ctx in the admin module to avoid discord TextChannel assertions."""
    async def _fake_get_ctx(interaction, *, defer: bool = True, ephemeral: bool = True):
        if defer:
            await interaction.response.defer(ephemeral=ephemeral)
        return CommandCtx(guild=interaction.guild, channel=interaction.channel, user=interaction.user)

    monkeypatch.setattr(admin_mod, "get_ctx", _fake_get_ctx)


@pytest.fixture()
def patch_scheduling(monkeypatch):
    """Make setup_cmd deterministic."""
    monkeypatch.setattr(admin_mod, "next_workday", lambda _d: date(2026, 2, 28))
    monkeypatch.setattr(admin_mod, "default_deadline_for", lambda _workday, _tz: 1700000000)


@pytest.mark.asyncio
async def test_setup_cmd_creates_panel_when_missing(bot, ids, patch_get_ctx, patch_scheduling):
    gid, cid = ids["guild_id"], ids["channel_id"]
    interaction = DummyInteraction(guild_id=gid, channel_id=cid, user_id=ids["admin"])

    # Precondition: no channel row
    assert await bot.db.get_rsvp_message_id(guild_id=gid, channel_id=cid) is None

    await admin_mod.setup_cmd(bot, interaction)

    # Panel created
    bot.panel.create_new_panel.assert_awaited_once()
    bot.panel.refresh_panel.assert_not_awaited()

    # Channel row created with defaults
    got_mid = await bot.db.get_rsvp_message_id(guild_id=gid, channel_id=cid)
    assert got_mid == 12345
    got_date = await bot.db.get_workday_date(guild_id=gid, channel_id=cid)
    assert got_date == "2026-02-28"
    got_deadline = await bot.db.get_deadline(guild_id=gid, channel_id=cid)
    assert int(got_deadline) == 1700000000

    # Directory seeded with invoking admin (if previously empty)
    directory = await bot.db.directory_list_active(guild_id=gid, channel_id=cid)
    assert ids["admin"] in directory

    # Confirmation
    interaction.followup.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_setup_cmd_refreshes_when_panel_exists(bot, ids, patch_get_ctx, patch_scheduling):
    gid, cid = ids["guild_id"], ids["channel_id"]
    interaction = DummyInteraction(guild_id=gid, channel_id=cid, user_id=ids["admin"])

    # Seed channel with an existing panel message id
    await bot.db.upsert_channel(
        guild_id=gid,
        channel_id=cid,
        reminder_offsets="60",
        workday_date="2026-02-27",
        deadline_ts=1699990000,
        rsvp_message_id=777,
        rollover_weekday=0,
        rollover_time="09:00",
    )

    await admin_mod.setup_cmd(bot, interaction)

    bot.panel.refresh_panel.assert_awaited_once()
    bot.panel.create_new_panel.assert_not_awaited()


@pytest.mark.asyncio
async def test_attendance_reset_cmd_calls_panel_reset(bot, ids, patch_get_ctx):
    gid, cid = ids["guild_id"], ids["channel_id"]
    interaction = DummyInteraction(guild_id=gid, channel_id=cid, user_id=ids["admin"])

    # Seed workday date so the handler can include it in the message.
    await bot.db.upsert_channel(
        guild_id=gid,
        channel_id=cid,
        reminder_offsets="60",
        workday_date="2026-02-28",
        deadline_ts=1700000000,
        rsvp_message_id=777,
        rollover_weekday=0,
        rollover_time="09:00",
    )

    await admin_mod.attendance_reset_cmd(bot, interaction)

    bot.panel.reset_attendance.assert_awaited_once()
    interaction.followup.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_rsvp_commands_cmd_lists_unique_commands(bot, ids):
    gid = ids["guild_id"]
    interaction = DummyInteraction(guild_id=gid, channel_id=ids["channel_id"], user_id=ids["admin"])
    interaction.guild = SimpleNamespace(id=gid)  # ensure guild context

    await admin_mod.rsvp_commands_cmd(bot, interaction)

    interaction.response.defer.assert_awaited_once()
    interaction.followup.send.assert_awaited_once()
    text = interaction.followup.send.call_args.args[0]
    assert "/setup" in text
