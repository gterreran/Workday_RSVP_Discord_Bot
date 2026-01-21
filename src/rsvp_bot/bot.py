from __future__ import annotations

import time
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from .config import load_config
from .db import DB
from .rsvp_view import RSVPView, build_embed, build_summary
from .utils import next_saturday, default_deadline_for


def is_admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and perms.manage_guild)


class RSVPBot(commands.Bot):
    def __init__(self, *, db: DB, timezone: str) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

        self.db = db
        self.tz = ZoneInfo(timezone)

    async def setup_hook(self) -> None:
        # Ensure DB schema exists
        await self.db.init()

        # Register persistent view so buttons keep working after restart
        self.add_view(RSVPView(on_choice=self._on_rsvp_choice))

        # Sync commands
        await self.tree.sync()

    async def _on_rsvp_choice(self, interaction: discord.Interaction, status: str) -> None:
        if not interaction.guild or not interaction.channel:
            await interaction.response.send_message("This can only be used in a server channel.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        channel_id = interaction.channel.id
        user_id = interaction.user.id

        # We assume the RSVP message is for the next Saturday workday.
        today = datetime.now(self.tz).date()
        wd = next_saturday(today)
        workday_date = wd.isoformat()

        row = await self.db.get_workday_for_channel(guild_id=guild_id, channel_id=channel_id, workday_date=workday_date)
        if not row:
            await interaction.response.send_message(
                "No active workday found for this channel. Ask an admin to run /setup here.",
                ephemeral=True,
            )
            return

        # Update RSVP
        await self.db.set_rsvp(
            guild_id=guild_id,
            channel_id=channel_id,
            workday_date=workday_date,
            user_id=user_id,
            status=status,
            updated_at_ts=int(time.time()),
        )

        # Rebuild summary + edit the panel message
        directory = await self.db.directory_list_active(guild_id=guild_id, channel_id=channel_id)
        rsvps = await self.db.list_rsvps(guild_id=guild_id, channel_id=channel_id, workday_date=workday_date)
        summary = build_summary(directory=directory, rsvps=rsvps)
        embed = build_embed(workday_date=workday_date, deadline_ts=row.deadline_ts, summary=summary)

        try:
            msg = await interaction.channel.fetch_message(row.rsvp_message_id)
            await msg.edit(embed=embed, view=RSVPView(on_choice=self._on_rsvp_choice))
        except discord.NotFound:
            pass

        await interaction.response.send_message(f"Recorded: **{status}**", ephemeral=True)


load_dotenv()
cfg = load_config()
db = DB(cfg.db_path)
bot = RSVPBot(db=db, timezone=cfg.timezone)


@bot.tree.command(name="setup", description="Create or reset the RSVP panel in this channel (admin only).")
async def setup(interaction: discord.Interaction):
    if not interaction.guild or not interaction.channel:
        await interaction.response.send_message("Run this inside a server channel.", ephemeral=True)
        return

    if not is_admin(interaction):
        await interaction.response.send_message("Admin only (Manage Server).", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    guild_id = interaction.guild.id
    channel_id = interaction.channel.id

    # Ensure channel settings exist
    await bot.db.upsert_channel(guild_id=guild_id, channel_id=channel_id, timezone=str(bot.tz.key))

    # Compute workday + deadline in local tz, store deadline in UTC timestamp
    now_local = datetime.now(bot.tz)
    wd = next_saturday(now_local.date())
    deadline_local = default_deadline_for(wd).replace(tzinfo=bot.tz)
    deadline_ts = int(deadline_local.timestamp())

    # If directory is empty, auto-add the command invoker (nice default)
    directory = await bot.db.directory_list_active(guild_id=guild_id, channel_id=channel_id)
    if not directory:
        await bot.db.directory_add(
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=interaction.user.id,
            added_by=interaction.user.id,
            added_at_ts=int(time.time()),
        )
        directory = [interaction.user.id]

    # Create initial embed
    workday_date = wd.isoformat()
    rsvps = await bot.db.list_rsvps(guild_id=guild_id, channel_id=channel_id, workday_date=workday_date)
    summary = build_summary(directory=directory, rsvps=rsvps)
    embed = build_embed(workday_date=workday_date, deadline_ts=deadline_ts, summary=summary)

    # Post message
    view = RSVPView(on_choice=bot._on_rsvp_choice)
    msg = await interaction.channel.send(embed=embed, view=view)

    # Pin it (ignore if missing perms)
    try:
        await msg.pin(reason="Workday RSVP panel")
    except discord.Forbidden:
        pass

    # Persist workday row
    await bot.db.create_workday(
        guild_id=guild_id,
        channel_id=channel_id,
        workday_date=workday_date,
        deadline_ts=deadline_ts,
        rsvp_message_id=msg.id,
        created_at_ts=int(time.time()),
    )

    await interaction.followup.send(
        f"RSVP panel created for **{workday_date}** (deadline: <t:{deadline_ts}:f>).",
        ephemeral=True,
    )


@bot.tree.command(name="directory_add", description="Add a user to this channel's RSVP directory (admin only).")
@app_commands.describe(user="User to add")
async def directory_add(interaction: discord.Interaction, user: discord.Member):
    if not interaction.guild or not interaction.channel:
        await interaction.response.send_message("Run this inside a server channel.", ephemeral=True)
        return
    if not is_admin(interaction):
        await interaction.response.send_message("Admin only (Manage Server).", ephemeral=True)
        return

    await bot.db.directory_add(
        guild_id=interaction.guild.id,
        channel_id=interaction.channel.id,
        user_id=user.id,
        added_by=interaction.user.id,
        added_at_ts=int(time.time()),
    )
    await interaction.response.send_message(f"Added {user.mention} to the directory for this channel.", ephemeral=True)


def main() -> None:
    bot.run(cfg.token)


if __name__ == "__main__":
    main()
