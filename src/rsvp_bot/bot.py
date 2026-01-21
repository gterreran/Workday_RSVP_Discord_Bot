from __future__ import annotations

import os
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
from discord.ext import tasks


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
        await self.db.init()
        self.add_view(RSVPView(on_choice=self._on_rsvp_choice))

        # Start background reminder task (if you have it)
        if hasattr(self, "reminder_loop") and not self.reminder_loop.is_running():
            self.reminder_loop.start()

        dev_gid = os.getenv("DEV_GUILD_ID", "").strip()
        if dev_gid:
            guild = discord.Object(id=int(dev_gid))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print(f"Synced commands to DEV guild {dev_gid} (guild-only)")
        else:
            await self.tree.sync()
            print("Synced commands globally")


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

    @tasks.loop(minutes=1)
    async def reminder_loop(self) -> None:
        # Runs every minute while the bot is online
        await self.wait_until_ready()

        # We scan only channels we have stored settings for by walking guilds/channels we’re in.
        # Minimal implementation: scan all guild text channels and act only if a workday exists for that channel.
        now_ts = int(time.time())
        now_local = datetime.now(self.tz)
        workday_date = next_saturday(now_local.date()).isoformat()

        for guild in self.guilds:
            for channel in guild.text_channels:
                try:
                    row = await self.db.get_workday_for_channel(
                        guild_id=guild.id,
                        channel_id=channel.id,
                        workday_date=workday_date,
                    )
                    if not row:
                        continue

                    # Make sure settings exist
                    await self.db.ensure_settings(guild_id=guild.id, channel_id=channel.id)
                    offsets = await self.db.get_reminder_offsets(guild_id=guild.id, channel_id=channel.id)

                    # Compute missing list
                    directory = await self.db.directory_list_active(guild_id=guild.id, channel_id=channel.id)
                    rsvps = await self.db.list_rsvps(guild_id=guild.id, channel_id=channel.id, workday_date=workday_date)
                    summary = build_summary(directory=directory, rsvps=rsvps)

                    if not summary.missing:
                        # Nothing to remind; skip sending and (optionally) don’t mark sent.
                        continue

                    # For each offset, if we are within the current minute window, send once
                    for off in offsets:
                        trigger_ts = row.deadline_ts - off * 60
                        if now_ts < trigger_ts or now_ts >= trigger_ts + 60:
                            continue

                        already = await self.db.reminder_already_sent(
                            guild_id=guild.id,
                            channel_id=channel.id,
                            workday_date=workday_date,
                            offset_min=off,
                        )
                        if already:
                            continue

                        mentions = " ".join(f"<@{uid}>" for uid in summary.missing)
                        hours = off / 60
                        await channel.send(
                            f"⏰ Reminder: please RSVP for **{workday_date}** before the deadline "
                            f"(<t:{row.deadline_ts}:f>). Missing: {mentions}"
                        )

                        await self.db.mark_reminder_sent(
                            guild_id=guild.id,
                            channel_id=channel.id,
                            workday_date=workday_date,
                            offset_min=off,
                            sent_at_ts=now_ts,
                        )

                except Exception:
                    # Don’t let one channel crash the loop
                    continue


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
    await bot.db.ensure_settings(guild_id=guild_id, channel_id=channel_id)

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


@bot.tree.command(name="directory_remove", description="Remove a user from this channel's RSVP directory (admin only).")
@app_commands.describe(user="User to remove")
async def directory_remove(interaction: discord.Interaction, user: discord.Member):
    if not interaction.guild or not interaction.channel:
        await interaction.response.send_message("Run this inside a server channel.", ephemeral=True)
        return
    if not is_admin(interaction):
        await interaction.response.send_message("Admin only (Manage Server).", ephemeral=True)
        return

    await bot.db.directory_remove(
        guild_id=interaction.guild.id,
        channel_id=interaction.channel.id,
        user_id=user.id,
    )
    await interaction.response.send_message(f"Removed {user.mention} from the directory for this channel.", ephemeral=True)


@bot.tree.command(name="directory_list", description="Show the current RSVP directory for this channel (admin only).")
async def directory_list(interaction: discord.Interaction):
    if not interaction.guild or not interaction.channel:
        await interaction.response.send_message("Run this inside a server channel.", ephemeral=True)
        return
    if not is_admin(interaction):
        await interaction.response.send_message("Admin only (Manage Server).", ephemeral=True)
        return

    ids = await bot.db.directory_list_active(
        guild_id=interaction.guild.id,
        channel_id=interaction.channel.id,
    )

    if not ids:
        await interaction.response.send_message("Directory is empty for this channel.", ephemeral=True)
        return

    # Discord message limit is 2000 chars; chunk if needed.
    mentions = [f"<@{uid}>" for uid in sorted(set(ids))]
    lines: list[str] = []
    current = ""
    for m in mentions:
        if len(current) + len(m) + 1 > 1800:
            lines.append(current.strip())
            current = ""
        current += m + " "
    if current.strip():
        lines.append(current.strip())

    header = f"Directory for <#{interaction.channel.id}> (**{len(mentions)}** people):"
    if len(lines) == 1:
        await interaction.response.send_message(f"{header}\n{lines[0]}", ephemeral=True)
    else:
        # Send first chunk as the response, rest as follow-ups
        await interaction.response.send_message(f"{header}\n{lines[0]}", ephemeral=True)
        for chunk in lines[1:]:
            await interaction.followup.send(chunk, ephemeral=True)


@bot.tree.command(name="reminders_set", description="Set reminder offsets (hours before deadline), e.g. 48,24,6,1 (admin only).")
@app_commands.describe(hours_csv="Comma-separated hours before deadline (e.g. 48,24,6,1)")
async def reminders_set(interaction: discord.Interaction, hours_csv: str):
    if not interaction.guild or not interaction.channel:
        await interaction.response.send_message("Run this inside a server channel.", ephemeral=True)
        return
    if not is_admin(interaction):
        await interaction.response.send_message("Admin only (Manage Server).", ephemeral=True)
        return

    parts = [p.strip() for p in hours_csv.split(",")]
    hours: list[int] = []
    for p in parts:
        if not p:
            continue
        hours.append(int(p))

    offsets_min = [h * 60 for h in hours if h > 0]
    await bot.db.set_reminder_offsets(
        guild_id=interaction.guild.id,
        channel_id=interaction.channel.id,
        offsets_min=offsets_min,
    )

    await interaction.response.send_message(
        f"Reminder schedule updated for this channel: **{', '.join(str(h) for h in sorted(set(hours), reverse=True))}h** before deadline.",
        ephemeral=True,
    )


@bot.tree.command(name="attendance_reset", description="Reset all RSVPs for the upcoming workday in this channel (admin only).")
async def attendance_reset(interaction: discord.Interaction):
    if not interaction.guild or not interaction.channel:
        await interaction.response.send_message("Run this inside a server channel.", ephemeral=True)
        return
    if not is_admin(interaction):
        await interaction.response.send_message("Admin only (Manage Server).", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    guild_id = interaction.guild.id
    channel_id = interaction.channel.id

    # Upcoming Saturday workday
    now_local = datetime.now(bot.tz)
    wd = next_saturday(now_local.date())
    workday_date = wd.isoformat()

    row = await bot.db.get_workday_for_channel(
        guild_id=guild_id,
        channel_id=channel_id,
        workday_date=workday_date,
    )
    if not row:
        await interaction.followup.send(
            "No active workday found for this channel. Run /setup first.",
            ephemeral=True,
        )
        return

    deleted_rsvps = await bot.db.clear_rsvps(
        guild_id=guild_id,
        channel_id=channel_id,
        workday_date=workday_date,
    )

    # Optional: reset reminder send history too (if table exists)
    try:
        deleted_rem = await bot.db.clear_sent_reminders(
            guild_id=guild_id,
            channel_id=channel_id,
            workday_date=workday_date,
        )
    except Exception:
        deleted_rem = 0

    # Refresh the panel message
    directory = await bot.db.directory_list_active(guild_id=guild_id, channel_id=channel_id)
    rsvps = await bot.db.list_rsvps(guild_id=guild_id, channel_id=channel_id, workday_date=workday_date)
    summary = build_summary(directory=directory, rsvps=rsvps)
    embed = build_embed(workday_date=workday_date, deadline_ts=row.deadline_ts, summary=summary)

    try:
        msg = await interaction.channel.fetch_message(row.rsvp_message_id)
        await msg.edit(embed=embed, view=RSVPView(on_choice=bot._on_rsvp_choice))
    except discord.NotFound:
        pass

    await interaction.followup.send(
        f"Reset RSVPs for **{workday_date}**. Cleared **{deleted_rsvps}** RSVP(s)"
        + (f" and **{deleted_rem}** reminder record(s)." if deleted_rem else "."),
        ephemeral=True,
    )


@bot.tree.command(name="deadline_in", description="Set the RSVP deadline to N minutes from now for the upcoming workday (admin only).")
@app_commands.describe(minutes="Minutes from now (e.g. 5)")
async def deadline_in(interaction: discord.Interaction, minutes: int):
    if not interaction.guild or not interaction.channel:
        await interaction.response.send_message("Run this inside a server channel.", ephemeral=True)
        return
    if not is_admin(interaction):
        await interaction.response.send_message("Admin only (Manage Server).", ephemeral=True)
        return
    if minutes <= 0 or minutes > 7 * 24 * 60:
        await interaction.response.send_message("Minutes must be between 1 and 10080.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    guild_id = interaction.guild.id
    channel_id = interaction.channel.id

    now_ts = int(time.time())
    new_deadline_ts = now_ts + minutes * 60

    # Upcoming Saturday workday date (same as everything else)
    wd = next_saturday(datetime.now(bot.tz).date())
    workday_date = wd.isoformat()

    row = await bot.db.get_workday_for_channel(guild_id=guild_id, channel_id=channel_id, workday_date=workday_date)
    if not row:
        await interaction.followup.send("No active workday found. Run /setup first.", ephemeral=True)
        return

    # Update deadline in workdays table
    async with bot.db.connect() as db:
        db.row_factory = __import__("aiosqlite").Row
        await db.execute(
            """
            UPDATE workdays
            SET deadline_ts=?
            WHERE guild_id=? AND channel_id=? AND workday_date=?
            """,
            (new_deadline_ts, guild_id, channel_id, workday_date),
        )
        await db.commit()

    # Clear sent reminders so they can re-fire for this test window
    try:
        await bot.db.clear_sent_reminders(guild_id=guild_id, channel_id=channel_id, workday_date=workday_date)
    except Exception:
        pass

    # Refresh panel
    directory = await bot.db.directory_list_active(guild_id=guild_id, channel_id=channel_id)
    rsvps = await bot.db.list_rsvps(guild_id=guild_id, channel_id=channel_id, workday_date=workday_date)
    summary = build_summary(directory=directory, rsvps=rsvps)
    embed = build_embed(workday_date=workday_date, deadline_ts=new_deadline_ts, summary=summary)

    try:
        msg = await interaction.channel.fetch_message(row.rsvp_message_id)
        await msg.edit(embed=embed, view=RSVPView(on_choice=bot._on_rsvp_choice))
    except discord.NotFound:
        pass

    await interaction.followup.send(
        f"Deadline set to <t:{new_deadline_ts}:f> (in {minutes} minutes).",
        ephemeral=True,
    )


@bot.tree.command(name="reminders_set_minutes", description="Set reminder offsets (minutes before deadline), e.g. 4,3,2,1 (admin only).")
@app_commands.describe(minutes_csv="Comma-separated minutes before deadline (e.g. 4,3,2,1)")
async def reminders_set_minutes(interaction: discord.Interaction, minutes_csv: str):
    if not interaction.guild or not interaction.channel:
        await interaction.response.send_message("Run this inside a server channel.", ephemeral=True)
        return
    if not is_admin(interaction):
        await interaction.response.send_message("Admin only (Manage Server).", ephemeral=True)
        return

    parts = [p.strip() for p in minutes_csv.split(",")]
    mins: list[int] = []
    for p in parts:
        if not p:
            continue
        mins.append(int(p))

    offsets_min = [m for m in mins if m > 0]
    await bot.db.set_reminder_offsets(
        guild_id=interaction.guild.id,
        channel_id=interaction.channel.id,
        offsets_min=offsets_min,
    )

    await interaction.response.send_message(
        f"Reminder schedule updated for this channel: **{', '.join(str(m) for m in sorted(set(mins), reverse=True))} min** before deadline.",
        ephemeral=True,
    )


def main() -> None:
    bot.run(cfg.token)


if __name__ == "__main__":
    main()
