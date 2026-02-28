# tests/test_commands_debug.py

"""Tests for debug scheduling command handlers.

We focus on pure parsing/DB effects and keep Discord mocked.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from discord import app_commands

from rsvp_bot.commands import debug as dbg_mod
from rsvp_bot.commands.ctx import CommandCtx


class DummyResponse:
    def __init__(self):
        self.defer = AsyncMock()
        self.send_message = AsyncMock()


class DummyFollowup:
    def __init__(self):
        self.send = AsyncMock()


class DummyInteraction:
    def __init__(self, *, guild_id: int, channel_id: int, user_id: int):
        self.guild = SimpleNamespace(id=guild_id)
        self.channel = SimpleNamespace(id=channel_id)
        self.user = SimpleNamespace(id=user_id)
        self.response = DummyResponse()
        self.followup = DummyFollowup()


@pytest.fixture()
def bot(db):
    fake = SimpleNamespace()
    fake.db = db
    fake.tz = SimpleNamespace()
    fake.panel = SimpleNamespace(refresh_panel=AsyncMock(), set_deadline_at=AsyncMock())
    fake.rsvp = SimpleNamespace(on_choice=AsyncMock(), on_choice_with_plan=AsyncMock())
    return fake


@pytest.fixture()
def patch_get_ctx(monkeypatch):
    async def _fake_get_ctx(interaction, *, defer: bool = True, ephemeral: bool = True):
        if defer:
            await interaction.response.defer(ephemeral=ephemeral)
        return CommandCtx(guild=interaction.guild, channel=interaction.channel, user=interaction.user)

    monkeypatch.setattr(dbg_mod, "get_ctx", _fake_get_ctx)


@pytest.mark.asyncio
async def test_rollover_set_cmd_validates_inputs(bot, ids, patch_get_ctx):
    interaction = DummyInteraction(guild_id=ids["guild_id"], channel_id=ids["channel_id"], user_id=ids["admin"])

    # Bad weekday
    await dbg_mod.rollover_set_cmd(bot, interaction, weekday=9, time_hhmm="09:00")
    interaction.response.send_message.assert_awaited()

    interaction.response.send_message.reset_mock()
    # Bad time
    await dbg_mod.rollover_set_cmd(bot, interaction, weekday=1, time_hhmm="99:99")
    interaction.response.send_message.assert_awaited()


@pytest.mark.asyncio
async def test_reminders_set_cmd_normalizes_and_stores(bot, db, ids, patch_get_ctx):
    gid, cid = ids["guild_id"], ids["channel_id"]
    interaction = DummyInteraction(guild_id=gid, channel_id=cid, user_id=ids["admin"])

    unit = app_commands.Choice(name="hours", value="hours")
    await dbg_mod.reminders_set_cmd(bot, interaction, values="24, 1, 24, 0, -2", unit=unit)

    # Stored in minutes (sorted desc, unique, positive)
    offsets = await db.get_reminder_offsets(guild_id=gid, channel_id=cid)
    assert offsets == [1440, 60]
    interaction.followup.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_reminders_set_cmd_rejects_non_int(bot, ids, patch_get_ctx):
    interaction = DummyInteraction(guild_id=ids["guild_id"], channel_id=ids["channel_id"], user_id=ids["admin"])
    unit = app_commands.Choice(name="minutes", value="minutes")

    await dbg_mod.reminders_set_cmd(bot, interaction, values="a,b", unit=unit)
    interaction.response.send_message.assert_awaited_once()
