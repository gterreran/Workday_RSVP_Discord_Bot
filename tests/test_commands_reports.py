# tests/test_commands_reports.py

"""Tests for report command handlers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from rsvp_bot.commands import reports as rep_mod
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
    return fake


@pytest.fixture()
def patch_get_ctx(monkeypatch):
    async def _fake_get_ctx(interaction, *, defer: bool = True, ephemeral: bool = True):
        if defer:
            await interaction.response.defer(ephemeral=ephemeral)
        return CommandCtx(guild=interaction.guild, channel=interaction.channel, user=interaction.user)

    monkeypatch.setattr(rep_mod, "get_ctx", _fake_get_ctx)


@pytest.mark.asyncio
async def test_summary_cmd_empty_directory(bot, db, ids, patch_get_ctx):
    gid, cid = ids["guild_id"], ids["channel_id"]
    await db.upsert_channel(
        guild_id=gid,
        channel_id=cid,
        reminder_offsets="60",
        workday_date="2026-02-28",
        deadline_ts=1700000000,
        rsvp_message_id=123,
        rollover_weekday=0,
        rollover_time="09:00",
    )

    interaction = DummyInteraction(guild_id=gid, channel_id=cid, user_id=ids["admin"])
    await rep_mod.summary_cmd(bot, interaction)

    interaction.followup.send.assert_awaited_once()
    assert "Directory is empty" in interaction.followup.send.call_args.args[0]


@pytest.mark.asyncio
async def test_summary_cmd_sends_report(bot, db, ids, patch_get_ctx):
    gid, cid = ids["guild_id"], ids["channel_id"]
    await db.upsert_channel(
        guild_id=gid,
        channel_id=cid,
        reminder_offsets="60",
        workday_date="2026-02-28",
        deadline_ts=1700000000,
        rsvp_message_id=123,
        rollover_weekday=0,
        rollover_time="09:00",
    )

    # Directory + RSVPs
    await db.directory_add(guild_id=gid, channel_id=cid, user_id=ids["user_a"], added_by=ids["admin"], added_at_ts=1)
    await db.directory_add(guild_id=gid, channel_id=cid, user_id=ids["user_b"], added_by=ids["admin"], added_at_ts=2)
    await db.set_rsvp(
        guild_id=gid,
        channel_id=cid,
        workday_date="2026-02-28",
        user_id=ids["user_a"],
        status="yes",
        note="bringing snacks",
        updated_at_ts=10,
    )

    interaction = DummyInteraction(guild_id=gid, channel_id=cid, user_id=ids["admin"])
    await rep_mod.summary_cmd(bot, interaction)

    interaction.followup.send.assert_awaited()
    first = interaction.followup.send.call_args_list[0].args[0]
    assert "RSVP Summary" in first
    assert f"<@{ids['user_a']}>" in first
