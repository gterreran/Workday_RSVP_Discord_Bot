# src/rsvp_bot/services/scheduler_service.py

"""
Background scheduling services
==============================

Periodic background tasks that keep the RSVP bot running week after week.

This module defines :class:`~rsvp_bot.services.scheduler_service.SchedulerService`,
which owns two timed loops:

- **Reminders**: post reminder messages before the RSVP deadline, mentioning only
  directory members who have not responded yet.
- **Rollover**: advance the bot to the next workday cycle on a weekly schedule,
  creating a fresh panel and updating per-channel state in the database.

The scheduler is intentionally lightweight: it runs once per minute and relies on
database state (rather than in-memory timers) so behavior is consistent across
restarts.

Classes
-------

:class:`~rsvp_bot.services.scheduler_service.SchedulerService`
    Starts and runs reminder and rollover loops for all registered channels.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime

import discord
from discord.ext import tasks

from ..commands.ctx import CommandCtx
from ..utils import default_deadline_for, next_workday


@dataclass
class SchedulerService:
    """
    Background scheduler that drives reminders and weekly rollover.

    .. rubric:: Attributes

    bot : :class:`discord.Client`
        Discord client instance that provides access to guild/channel caches and
        shared bot services (DB, panel, RSVP).
    weekly_done : :class:`set` [:class:`str`]
        In-memory guard to prevent running rollover multiple times for the same
        channel/day while the process is alive.
    """

    bot: discord.Client
    weekly_done: set[str]

    @property
    def db(self):
        """
        Convenience accessor for the bot database.

        Returns
        -------
        :class:`~rsvp_bot.db.core.DB`
            Database wrapper attached to the bot instance.
        """
        return self.bot.db

    @property
    def tz(self):
        """
        Convenience accessor for the bot timezone.

        Returns
        -------
        :class:`zoneinfo.ZoneInfo`
            Timezone used for local scheduling checks.
        """
        return self.bot.tz

    @property
    def panel(self):
        """
        Convenience accessor for the panel service.

        Returns
        -------
        :class:`~rsvp_bot.services.panel_service.PanelService`
            Service used to create, refresh, and cleanup RSVP panels.
        """
        return self.bot.panel

    @property
    def rsvp(self):
        """
        Convenience accessor for the RSVP service.

        Returns
        -------
        :class:`~rsvp_bot.services.rsvp_service.RSVPService`
            Service implementing RSVP update callbacks for UI interactions.
        """
        return self.bot.rsvp

    def _make_ctx(self, guild_id: int, channel_id: int) -> CommandCtx | None:
        """
        Build a lightweight :class:`~rsvp_bot.commands.ctx.CommandCtx` for a channel.

        Scheduler tasks operate outside of user interactions, so this helper
        synthesizes a minimal context object using cached guild/channel objects
        and the bot user as a placeholder.

        Parameters
        ----------
        guild_id : :class:`int`
            Discord guild ID.
        channel_id : :class:`int`
            Discord channel ID.

        Returns
        -------
        :class:`~rsvp_bot.commands.ctx.CommandCtx` or :class:`None`
            Context object if the guild and channel are available and usable;
            otherwise :class:`None`.
        """
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return None

        ch = guild.get_channel(channel_id)
        if not isinstance(ch, discord.TextChannel):
            return None

        # Placeholder user; PanelService does not depend on ctx.user but CommandCtx requires it.
        if self.bot.user is None:
            return None

        return CommandCtx(guild=guild, channel=ch, user=self.bot.user)

    def start(self) -> None:
        """
        Start all scheduler loops if they are not already running.

        Returns
        -------
        None
            This method returns :class:`None`.
        """
        if not self.reminder_loop.is_running():
            self.reminder_loop.start()
        if not self.rollover_loop.is_running():
            self.rollover_loop.start()

    # ---------------------------------------------------------------------
    # Reminders
    # ---------------------------------------------------------------------

    @tasks.loop(minutes=1)
    async def reminder_loop(self) -> None:
        """
        Post reminder messages prior to the RSVP deadline.

        For each registered channel, this loop:

        1. Reads the current workday and deadline from the database.
        2. Iterates reminder offsets (minutes before deadline).
        3. Sends a reminder when within a 60-second window of the offset time.
        4. Mentions only directory members who have not RSVPed yet.
        5. Records the reminder in ``sent_reminders`` to prevent duplicates.

        Returns
        -------
        None
            This coroutine returns :class:`None`.

        Notes
        -----
        - If the directory is empty, no reminder is sent (to avoid channel spam).
        - If everyone already RSVPed, the reminder is still recorded as sent to
          prevent repeated checks from re-triggering it.
        """
        await self.bot.wait_until_ready()

        now_ts = int(time.time())
        channels = await self.db.list_registered_channels()

        for guild_id, channel_id in channels:
            ctx = self._make_ctx(guild_id, channel_id)
            if ctx is None:
                continue

            workday_date = await self.db.get_workday_date(
                guild_id=ctx.guild_id,
                channel_id=ctx.channel_id,
            )
            if not workday_date:
                continue

            deadline_ts = await self.db.get_deadline(
                guild_id=ctx.guild_id,
                channel_id=ctx.channel_id,
            )
            if not deadline_ts or now_ts >= int(deadline_ts):
                continue

            offsets_min = await self.db.get_reminder_offsets(
                guild_id=ctx.guild_id,
                channel_id=ctx.channel_id,
            )

            for offset_min in offsets_min:
                offset_min = int(offset_min)
                if offset_min <= 0:
                    continue

                send_at_ts = int(deadline_ts) - offset_min * 60
                if not (send_at_ts <= now_ts < send_at_ts + 60):
                    continue

                already = await self.db.reminder_already_sent(
                    guild_id=ctx.guild_id,
                    channel_id=ctx.channel_id,
                    workday_date=workday_date,
                    offset_min=offset_min,
                )
                if already:
                    continue

                # Mention only directory members who have not RSVPed yet
                expected_user_ids = await self.db.directory_list_active(
                    guild_id=ctx.guild_id,
                    channel_id=ctx.channel_id,
                )
                if not expected_user_ids:
                    continue

                rsvped_user_ids = await self.db.list_rsvp_user_ids(
                    guild_id=ctx.guild_id,
                    channel_id=ctx.channel_id,
                    workday_date=workday_date,
                )

                missing_user_ids = sorted(set(expected_user_ids) - set(rsvped_user_ids))
                if not missing_user_ids:
                    await self.db.mark_reminder_sent(
                        guild_id=ctx.guild_id,
                        channel_id=ctx.channel_id,
                        workday_date=workday_date,
                        offset_min=offset_min,
                        sent_at_ts=now_ts,
                    )
                    continue

                # Keep the message comfortably below Discord's 2000-char limit.
                missing_user_ids = missing_user_ids[:25]
                mentions = " ".join(f"<@{uid}>" for uid in missing_user_ids)

                try:
                    await ctx.channel.send(
                        f"⏰ Reminder: RSVP deadline for **{workday_date}** is <t:{int(deadline_ts)}:f> "
                        f"({offset_min} min remaining).\n"
                        f"Missing RSVPs: {mentions}",
                        allowed_mentions=discord.AllowedMentions(users=True),
                    )
                except (discord.Forbidden, discord.HTTPException):
                    continue

                await self.db.mark_reminder_sent(
                    guild_id=ctx.guild_id,
                    channel_id=ctx.channel_id,
                    workday_date=workday_date,
                    offset_min=offset_min,
                    sent_at_ts=now_ts,
                )

    # ---------------------------------------------------------------------
    # Rollover
    # ---------------------------------------------------------------------

    @tasks.loop(minutes=1)
    async def rollover_loop(self) -> None:
        """
        Advance the bot to the next workday cycle on a weekly schedule.

        For each registered channel, this loop:

        1. Checks whether the current time matches the configured rollover schedule.
        2. Ensures rollover is not triggered multiple times in the same day.
        3. Computes the next workday and its default deadline.
        4. Cleans up the old panel (unpinned; optionally deleted).
        5. Creates a new panel and persists updated per-channel state.

        Returns
        -------
        None
            This coroutine returns :class:`None`.

        Notes
        -----
        Rollover checks are performed at **minute precision**. If the bot is not
        running during the configured rollover minute, rollover will occur at the
        next scheduled week.
        """
        await self.bot.wait_until_ready()

        channels = await self.db.list_registered_channels()

        for guild_id, channel_id in channels:
            ctx = self._make_ctx(guild_id, channel_id)
            if ctx is None:
                continue

            now = datetime.now(self.tz)

            # Skip if current date is still before the stored workday date.
            old_workday_date = await self.db.get_workday_date(
                guild_id=ctx.guild_id,
                channel_id=ctx.channel_id,
            )
            if old_workday_date:
                old_date = datetime.fromisoformat(old_workday_date).date()
                if now.date() < old_date:
                    continue

            wd, hhmm = await self.db.get_rollover_schedule(
                guild_id=ctx.guild_id,
                channel_id=ctx.channel_id,
            )
            hh, mm = (int(x) for x in hhmm.split(":"))

            if now.weekday() != int(wd):
                continue
            if now.hour != hh or now.minute != mm:
                continue

            key = f"{ctx.guild_id}:{ctx.channel_id}:{now.date().isoformat()}"
            if key in self.weekly_done:
                continue
            self.weekly_done.add(key)

            workday = next_workday(now.date())
            workday_date = workday.isoformat()
            deadline_ts = default_deadline_for(workday, self.tz)

            offsets = await self.db.get_reminder_offsets(
                guild_id=ctx.guild_id,
                channel_id=ctx.channel_id,
            )
            reminder_offsets = ",".join(str(x) for x in offsets)

            await self.panel.cleanup_panel(
                ctx=ctx,
                delete_message=False,
            )

            rsvp_message_id = await self.panel.create_new_panel(
                ctx=ctx,
                workday_date=workday_date,
                deadline_ts=deadline_ts,
                on_choice=self.rsvp.on_choice,
                on_choice_with_plan=self.rsvp.on_choice_with_plan,
            )

            await self.db.upsert_channel(
                guild_id=ctx.guild_id,
                channel_id=ctx.channel_id,
                reminder_offsets=reminder_offsets,
                workday_date=workday_date,
                deadline_ts=deadline_ts,
                rsvp_message_id=rsvp_message_id,
                rollover_weekday=int(wd),
                rollover_time=str(hhmm),
            )
