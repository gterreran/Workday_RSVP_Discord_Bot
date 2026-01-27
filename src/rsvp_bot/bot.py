# rsvp_bot/bot.py

from __future__ import annotations

import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

from .config import load_config
from .db import DB
from .rsvp_view import RSVPView, build_embed, build_summary, PartnerSelectView, RSVPPlanModal
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

        # Stash pending note/status between modal submit and partner select submit
        # key: (guild_id, channel_id, user_id, workday_date) -> (status, note)
        self._pending_partner_flow: dict[tuple[int, int, int, str], tuple[str, str | None]] = {}

    async def setup_hook(self) -> None:
        await self.db.init()
        self.add_view(RSVPView(on_choice=self._set_rsvp_and_refresh, on_choice_with_plan=self._open_plan_modal))

        if not self.reminder_loop.is_running():
            self.reminder_loop.start()

        dev_gid = os.getenv("DEV_GUILD_ID", "").strip()
        if dev_gid:
            guild = discord.Object(id=int(dev_gid))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def _open_plan_modal(self, interaction: discord.Interaction, status: str) -> None:
        modal = RSVPPlanModal(status=status, on_submit_plan=self._after_plan_submit)
        await interaction.response.send_modal(modal)

    async def _after_plan_submit(self, interaction: discord.Interaction, status: str, note: str | None) -> None:
        """
        Modal submit handler. Does NOT write partners yet.
        It writes RSVP (and clears partners if needed) then sends ONE ephemeral message
        that contains the partner select.
        """
        if not interaction.guild or not interaction.channel:
            await interaction.response.send_message("This can only be used in a server channel.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        channel_id = interaction.channel.id
        user_id = interaction.user.id
        workday_date = next_saturday(datetime.now(self.tz).date()).isoformat()
        now_ts = int(time.time())

        row = await self.db.get_workday_for_channel(guild_id=guild_id, channel_id=channel_id, workday_date=workday_date)
        if not row:
            await interaction.response.send_message("No active workday found here. Run /setup.", ephemeral=True)
            return

        # Save RSVP + note
        await self.db.set_rsvp(
            guild_id=guild_id,
            channel_id=channel_id,
            workday_date=workday_date,
            user_id=user_id,
            status=status,
            note=note,
            updated_at_ts=now_ts,
        )

        # If attending/remote -> prompt partner selection; else clear partners immediately
        if status not in ("yes", "remote"):
            await self.db.replace_work_partners(
                guild_id=guild_id,
                channel_id=channel_id,
                workday_date=workday_date,
                user_id=user_id,
                partner_ids=[],
                created_at_ts=now_ts,
            )
            await self._refresh_panel(guild_id=guild_id, channel_id=channel_id, workday_date=workday_date)
            await interaction.response.send_message(f"Recorded: **{status}**", ephemeral=True)
            return

        # Build directory-only partner options with REAL NAMES
        directory = await self.db.directory_list_active(guild_id=guild_id, channel_id=channel_id)
        candidates = [uid for uid in sorted(set(directory)) if uid != user_id]

        if not candidates:
            await self._refresh_panel(guild_id=guild_id, channel_id=channel_id, workday_date=workday_date)
            await interaction.response.send_message(
                f"Recorded: **{status}**" + ("" if not note else " (with note)") + "\nNo other directory members to select.",
                ephemeral=True,
            )
            return

        options: list[discord.SelectOption] = []
        for uid in candidates[:25]:
            # Prefer cache, fall back to fetch for correct display names
            member = interaction.guild.get_member(uid)
            if member is None:
                try:
                    member = await interaction.guild.fetch_member(uid)
                except discord.HTTPException:
                    member = None
            label = (member.display_name if member else f"User {uid}")[:100]
            options.append(discord.SelectOption(label=label, value=str(uid)))

        # Stash pending status/note so partner select callback can finish the flow
        key = (guild_id, channel_id, user_id, workday_date)
        self._pending_partner_flow[key] = (status, note)

        view = PartnerSelectView(options=options, on_submit_partners=self._after_partner_select)

        # ONE ephemeral message: ack + selector
        msg = f"Recorded: **{status}**" + ("" if not note else " (with note)") + "\nSelect partners (optional):"
        await interaction.response.send_message(msg, ephemeral=True, view=view)

    async def _after_partner_select(self, interaction: discord.Interaction, partner_ids: list[int]) -> None:
        """
        Called by the dropdown view. Writes partners, refreshes panel, sends final ack.
        """
        if not interaction.guild or not interaction.channel:
            await interaction.response.send_message("This can only be used in a server channel.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        channel_id = interaction.channel.id
        user_id = interaction.user.id
        workday_date = next_saturday(datetime.now(self.tz).date()).isoformat()
        now_ts = int(time.time())

        key = (guild_id, channel_id, user_id, workday_date)
        if key not in self._pending_partner_flow:
            # Flow expired or restarted; still save partners safely.
            status = "yes"
        else:
            status, _note = self._pending_partner_flow.pop(key)

        # Enforce directory-only
        directory = await self.db.directory_list_active(guild_id=guild_id, channel_id=channel_id)
        directory_set = set(directory)
        cleaned = sorted({pid for pid in (partner_ids or []) if pid != user_id and pid in directory_set})

        await self.db.replace_work_partners(
            guild_id=guild_id,
            channel_id=channel_id,
            workday_date=workday_date,
            user_id=user_id,
            partner_ids=cleaned,
            created_at_ts=now_ts,
        )

        await self._refresh_panel(guild_id=guild_id, channel_id=channel_id, workday_date=workday_date)

        # Respond to the select interaction (must respond)
        if cleaned:
            pretty = " ".join(f"<@{uid}>" for uid in cleaned)
            await interaction.response.send_message(f"Saved partners: {pretty}", ephemeral=True)
        else:
            await interaction.response.send_message("Saved partners: (none)", ephemeral=True)

    async def _refresh_panel(self, *, guild_id: int, channel_id: int, workday_date: str) -> None:
        row = await self.db.get_workday_for_channel(guild_id=guild_id, channel_id=channel_id, workday_date=workday_date)
        if not row:
            return

        directory = await self.db.directory_list_active(guild_id=guild_id, channel_id=channel_id)
        rsvps = await self.db.list_rsvps(guild_id=guild_id, channel_id=channel_id, workday_date=workday_date)
        summary = build_summary(directory=directory, rsvps=rsvps)
        embed = build_embed(workday_date=workday_date, deadline_ts=row.deadline_ts, summary=summary)

        guild = self.get_guild(guild_id)
        if not guild:
            return
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        try:
            msg = await channel.fetch_message(row.rsvp_message_id)
            await msg.edit(embed=embed, view=RSVPView(on_choice=self._set_rsvp_and_refresh, on_choice_with_plan=self._open_plan_modal))
        except discord.NotFound:
            pass

    async def _set_rsvp_and_refresh(self, interaction: discord.Interaction, status: str, note: str | None) -> None:
        """
        Used for Maybe / Not attending buttons. (No modal)
        """
        if not interaction.guild or not interaction.channel:
            await interaction.response.send_message("This can only be used in a server channel.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        channel_id = interaction.channel.id
        user_id = interaction.user.id
        workday_date = next_saturday(datetime.now(self.tz).date()).isoformat()
        now_ts = int(time.time())

        prev = await self.db.get_rsvp(guild_id=guild_id, channel_id=channel_id, workday_date=workday_date, user_id=user_id)
        prev_status = prev[0] if prev else None

        await self.db.set_rsvp(
            guild_id=guild_id,
            channel_id=channel_id,
            workday_date=workday_date,
            user_id=user_id,
            status=status,
            note=note,
            updated_at_ts=now_ts,
        )

        # Clear partners when not attending/remote
        if status not in ("yes", "remote"):
            await self.db.replace_work_partners(
                guild_id=guild_id,
                channel_id=channel_id,
                workday_date=workday_date,
                user_id=user_id,
                partner_ids=[],
                created_at_ts=now_ts,
            )

        await self._refresh_panel(guild_id=guild_id, channel_id=channel_id, workday_date=workday_date)

        # Safeguard notification when switching to "no"
        if status == "no" and prev_status != "no":
            dependents = await self.db.get_dependent_users(
                guild_id=guild_id,
                channel_id=channel_id,
                workday_date=workday_date,
                partner_id=user_id,
            )
            if dependents:
                mentions = " ".join(f"<@{uid}>" for uid in sorted(set(dependents)))
                try:
                    await interaction.channel.send(
                        f"⚠️ Heads up {mentions}: <@{user_id}> just updated their RSVP to ❌ **Not attending**. "
                        f"You listed them as someone you planned to work with."
                    )
                except discord.Forbidden:
                    pass

        await interaction.response.send_message(f"Recorded: **{status}**", ephemeral=True)

    @tasks.loop(minutes=1)
    async def reminder_loop(self) -> None:
        await self.wait_until_ready()

        now_ts = int(time.time())
        workday_date = next_saturday(datetime.now(self.tz).date()).isoformat()

        for guild in self.guilds:
            for channel in guild.text_channels:
                try:
                    row = await self.db.get_workday_for_channel(guild_id=guild.id, channel_id=channel.id, workday_date=workday_date)
                    if not row:
                        continue

                    await self.db.ensure_settings(guild_id=guild.id, channel_id=channel.id)
                    offsets = await self.db.get_reminder_offsets(guild_id=guild.id, channel_id=channel.id)

                    directory = await self.db.directory_list_active(guild_id=guild.id, channel_id=channel.id)
                    rsvps = await self.db.list_rsvps(guild_id=guild.id, channel_id=channel.id, workday_date=workday_date)
                    summary = build_summary(directory=directory, rsvps=rsvps)

                    if not summary.missing:
                        continue

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
    await bot.db.upsert_channel(guild_id=guild_id, channel_id=channel_id, timezone=str(bot.tz.key))

    now_local = datetime.now(bot.tz)
    wd = next_saturday(now_local.date())
    deadline_local = default_deadline_for(wd).replace(tzinfo=bot.tz)
    deadline_ts = int(deadline_local.timestamp())

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

    workday_date = wd.isoformat()
    rsvps = await bot.db.list_rsvps(guild_id=guild_id, channel_id=channel_id, workday_date=workday_date)
    summary = build_summary(directory=directory, rsvps=rsvps)
    embed = build_embed(workday_date=workday_date, deadline_ts=deadline_ts, summary=summary)

    view = RSVPView(on_choice=bot._set_rsvp_and_refresh, on_choice_with_plan=bot._open_plan_modal)
    msg = await interaction.channel.send(embed=embed, view=view)

    try:
        await msg.pin(reason="Workday RSVP panel")
    except discord.Forbidden:
        pass

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

    ids = await bot.db.directory_list_active(guild_id=interaction.guild.id, channel_id=interaction.channel.id)
    if not ids:
        await interaction.response.send_message("Directory is empty for this channel.", ephemeral=True)
        return

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
        f"Reminder schedule updated: **{', '.join(str(h) for h in sorted(set(hours), reverse=True))}h** before deadline.",
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
        await interaction.followup.send("No active workday found for this channel. Run /setup first.", ephemeral=True)
        return

    # Clear RSVPs (and ideally partner links too)
    deleted_rsvps = await bot.db.clear_rsvps(
        guild_id=guild_id,
        channel_id=channel_id,
        workday_date=workday_date,
    )

    # If you have partner links, clear them as well (recommended)
    try:
        await bot.db.clear_work_partners(
            guild_id=guild_id,
            channel_id=channel_id,
            workday_date=workday_date,
        )
    except Exception:
        pass

    # Optional: reset reminder send history too
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
        await msg.edit(
            embed=embed,
            view=RSVPView(
                on_choice=bot._set_rsvp_and_refresh,
                on_choice_with_plan=bot._open_plan_modal,
            ),
        )
    except discord.NotFound:
        pass

    extra = f" and **{deleted_rem}** reminder record(s)" if deleted_rem else ""
    await interaction.followup.send(
        f"Reset RSVPs for **{workday_date}**. Cleared **{deleted_rsvps}** RSVP(s){extra}.",
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

    workday_date = next_saturday(datetime.now(bot.tz).date()).isoformat()
    row = await bot.db.get_workday_for_channel(guild_id=guild_id, channel_id=channel_id, workday_date=workday_date)
    if not row:
        await interaction.followup.send("No active workday found. Run /setup first.", ephemeral=True)
        return

    await bot.db.update_workday_deadline(
        guild_id=guild_id,
        channel_id=channel_id,
        workday_date=workday_date,
        deadline_ts=new_deadline_ts,
    )

    try:
        await bot.db.clear_sent_reminders(guild_id=guild_id, channel_id=channel_id, workday_date=workday_date)
    except Exception:
        pass

    directory = await bot.db.directory_list_active(guild_id=guild_id, channel_id=channel_id)
    rsvps = await bot.db.list_rsvps(guild_id=guild_id, channel_id=channel_id, workday_date=workday_date)
    summary_obj = build_summary(directory=directory, rsvps=rsvps)
    embed = build_embed(workday_date=workday_date, deadline_ts=new_deadline_ts, summary=summary_obj)

    try:
        msg = await interaction.channel.fetch_message(row.rsvp_message_id)
        await msg.edit(embed=embed, view=RSVPView(on_choice=bot._set_rsvp_and_refresh, on_choice_with_plan=bot._open_plan_modal))
    except discord.NotFound:
        pass

    await interaction.followup.send(f"Deadline set to <t:{new_deadline_ts}:f> (in {minutes} minutes).", ephemeral=True)


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
        f"Reminder schedule updated: **{', '.join(str(m) for m in sorted(set(mins), reverse=True))} min** before deadline.",
        ephemeral=True,
    )


@bot.tree.command(name="summary", description="Show RSVP status (notes + partners) for everyone in the directory (admin only).")
async def summary(interaction: discord.Interaction):
    if not interaction.guild or not interaction.channel:
        await interaction.response.send_message("Run this inside a server channel.", ephemeral=True)
        return
    if not is_admin(interaction):
        await interaction.response.send_message("Admin only (Manage Server).", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    guild_id = interaction.guild.id
    channel_id = interaction.channel.id

    # Upcoming workday
    wd = next_saturday(datetime.now(bot.tz).date())
    workday_date = wd.isoformat()

    directory = await bot.db.directory_list_active(guild_id=guild_id, channel_id=channel_id)
    if not directory:
        await interaction.followup.send("Directory is empty for this channel.", ephemeral=True)
        return

    # RSVP rows: (user_id, status, note)
    rsvps = await bot.db.list_rsvps_with_notes(
        guild_id=guild_id,
        channel_id=channel_id,
        workday_date=workday_date,
    )
    by_user: dict[int, tuple[str, str | None]] = {int(uid): (status, note) for uid, status, note in rsvps}

    # Partners map: user_id -> [partner_id, ...]
    partners_map = await bot.db.list_work_partners_map(
        guild_id=guild_id,
        channel_id=channel_id,
        workday_date=workday_date,
    )

    # Group directory users
    groups: dict[str, list[int]] = {"yes": [], "remote": [], "maybe": [], "no": [], "missing": []}
    for uid in sorted(set(int(x) for x in directory)):
        if uid not in by_user:
            groups["missing"].append(uid)
            continue
        status, _ = by_user[uid]
        if status in groups:
            groups[status].append(uid)
        else:
            groups["missing"].append(uid)

    def _one_line(text: str) -> str:
        return " ".join((text or "").split()).strip()

    def fmt_partners(uid: int) -> str:
        ids = partners_map.get(uid, [])
        if not ids:
            return ""
        return " — partners: " + " ".join(f"<@{pid}>" for pid in ids)

    def fmt_user(uid: int, *, include_note: bool, include_partners: bool) -> str:
        mention = f"<@{uid}>"
        status, note = by_user.get(uid, ("", None))

        parts: list[str] = [f"- {mention}"]

        if include_note and note:
            parts.append(f"— {_one_line(note)}")

        if include_partners and status in ("yes", "remote"):
            p = partners_map.get(uid, [])
            if p:
                parts.append("— partners: " + " ".join(f"<@{pid}>" for pid in p))

        return " ".join(parts)

    blocks: list[str] = []
    blocks.append(f"**RSVP Summary — {workday_date}** (channel <#{channel_id}>)\n")

    def section(title: str, ids: list[int], *, show_notes: bool, show_partners: bool) -> None:
        blocks.append(f"__{title}__ (**{len(ids)}**)")
        if not ids:
            blocks.append("_None_")
            blocks.append("")
            return
        for uid in ids:
            blocks.append(fmt_user(uid, include_note=show_notes, include_partners=show_partners))
        blocks.append("")

    section("✅ Attending (In person)", groups["yes"], show_notes=True, show_partners=True)
    section("🎥 Attending (Remote)", groups["remote"], show_notes=True, show_partners=True)
    section("❔ Maybe", groups["maybe"], show_notes=False, show_partners=False)
    section("❌ Not attending", groups["no"], show_notes=False, show_partners=False)
    section("⌛ Missing", groups["missing"], show_notes=False, show_partners=False)

    # Chunk under ~1800 chars to be safe with ephemeral messages
    text = "\n".join(blocks).strip()
    chunks: list[str] = []
    cur = ""
    for line in text.splitlines(True):  # keep newlines
        if len(cur) + len(line) > 1800:
            chunks.append(cur)
            cur = ""
        cur += line
    if cur:
        chunks.append(cur)

    await interaction.followup.send(chunks[0], ephemeral=True)
    for c in chunks[1:]:
        await interaction.followup.send(c, ephemeral=True)



def main() -> None:
    bot.run(cfg.token)


if __name__ == "__main__":
    main()
