# tests/test_commands_directory.py

"""Tests for directory command handlers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from rsvp_bot.commands import directory as dir_mod
from rsvp_bot.commands.ctx import CommandCtx


class DummyResponse:
    def __init__(self):
        self.defer = AsyncMock()
        self.send_message = AsyncMock()


class DummyFollowup:
    def __init__(self):
        self.send = AsyncMock()


class DummyMember:
    def __init__(self, user_id: int):
        self.id = user_id
        self.mention = f"<@{user_id}>"


class DummyInteraction:
    def __init__(self, *, guild_id: int, channel_id: int, invoker_id: int):
        self.guild = SimpleNamespace(id=guild_id)
        self.channel = SimpleNamespace(id=channel_id)
        self.user = DummyMember(invoker_id)
        self.response = DummyResponse()
        self.followup = DummyFollowup()


@pytest.fixture()
def bot(db):
    fake = SimpleNamespace()
    fake.db = db
    fake.panel = SimpleNamespace(refresh_panel=AsyncMock())
    fake.rsvp = SimpleNamespace(on_choice=AsyncMock(), on_choice_with_plan=AsyncMock())
    return fake


@pytest.fixture()
def patch_get_ctx(monkeypatch):
    async def _fake_get_ctx(interaction, *, defer: bool = True, ephemeral: bool = True):
        if defer:
            await interaction.response.defer(ephemeral=ephemeral)
        return CommandCtx(guild=interaction.guild, channel=interaction.channel, user=interaction.user)

    monkeypatch.setattr(dir_mod, "get_ctx", _fake_get_ctx)


async def _seed_channel(db, *, guild_id: int, channel_id: int):
    await db.upsert_channel(
        guild_id=guild_id,
        channel_id=channel_id,
        reminder_offsets="60",
        workday_date="2026-02-28",
        deadline_ts=1700000000,
        rsvp_message_id=123,
        rollover_weekday=0,
        rollover_time="09:00",
    )


@pytest.mark.asyncio
async def test_directory_add_cmd_adds_and_refreshes(bot, db, ids, patch_get_ctx):
    gid, cid = ids["guild_id"], ids["channel_id"]
    await _seed_channel(db, guild_id=gid, channel_id=cid)

    interaction = DummyInteraction(guild_id=gid, channel_id=cid, invoker_id=ids["admin"])
    member = DummyMember(ids["user_a"])

    await dir_mod.directory_add_cmd(bot, interaction, user=member)

    directory = await db.directory_list_active(guild_id=gid, channel_id=cid)
    assert member.id in directory
    bot.panel.refresh_panel.assert_awaited_once()
    interaction.followup.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_directory_add_cmd_noop_when_already_active(bot, db, ids, patch_get_ctx):
    gid, cid = ids["guild_id"], ids["channel_id"]
    await _seed_channel(db, guild_id=gid, channel_id=cid)

    # Already active
    await db.directory_add(guild_id=gid, channel_id=cid, user_id=ids["user_a"], added_by=ids["admin"], added_at_ts=1)

    interaction = DummyInteraction(guild_id=gid, channel_id=cid, invoker_id=ids["admin"])
    member = DummyMember(ids["user_a"])
    await dir_mod.directory_add_cmd(bot, interaction, user=member)

    # No refresh needed
    bot.panel.refresh_panel.assert_not_awaited()
    interaction.followup.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_directory_remove_cmd_deactivates_and_refreshes(bot, db, ids, patch_get_ctx):
    gid, cid = ids["guild_id"], ids["channel_id"]
    await _seed_channel(db, guild_id=gid, channel_id=cid)
    await db.directory_add(guild_id=gid, channel_id=cid, user_id=ids["user_a"], added_by=ids["admin"], added_at_ts=1)

    interaction = DummyInteraction(guild_id=gid, channel_id=cid, invoker_id=ids["admin"])
    member = DummyMember(ids["user_a"])
    await dir_mod.directory_remove_cmd(bot, interaction, user=member)

    directory = await db.directory_list_active(guild_id=gid, channel_id=cid)
    assert member.id not in directory
    bot.panel.refresh_panel.assert_awaited_once()


@pytest.mark.asyncio
async def test_directory_list_cmd_sends_compact_listing(bot, db, ids, patch_get_ctx):
    gid, cid = ids["guild_id"], ids["channel_id"]

    # Seed some members
    await db.directory_add(guild_id=gid, channel_id=cid, user_id=ids["user_a"], added_by=ids["admin"], added_at_ts=1)
    await db.directory_add(guild_id=gid, channel_id=cid, user_id=ids["user_b"], added_by=ids["admin"], added_at_ts=2)

    interaction = DummyInteraction(guild_id=gid, channel_id=cid, invoker_id=ids["admin"])
    await dir_mod.directory_list_cmd(bot, interaction)

    interaction.followup.send.assert_awaited()
    first = interaction.followup.send.call_args_list[0].args[0]
    assert "Directory" in first
    assert f"<@{ids['user_a']}>" in first
