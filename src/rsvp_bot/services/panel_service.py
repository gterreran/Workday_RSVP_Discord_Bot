# src/rsvp_bot/services/panel_service.py

"""
RSVP panel lifecycle service
============================

Helpers for creating, updating, and cleaning up the persistent RSVP panel message
in a Discord text channel.

This module defines :class:`~rsvp_bot.services.panel_service.PanelService`, a small
service layer responsible for:

- Creating a new pinned panel message with an embed and interactive buttons.
- Refreshing the panel embed to reflect the current directory and RSVPs.
- Cleaning up the prior panel during rollover (unpin and optional delete).
- Providing admin/debug helpers that reset attendance state or adjust deadlines
  and then refresh the panel.

The panel embed is built using :func:`~rsvp_bot.embeds.build_embed`, which is fed a
:class:`~rsvp_bot.models.Summary` produced by :func:`~rsvp_bot.summary.build_summary`.
User interactions are implemented by the persistent :class:`~rsvp_bot.views.RSVPView`.

Classes
-------

:class:`~rsvp_bot.services.panel_service.PanelService`
    Creates, refreshes, and cleans up the persistent RSVP panel message.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import discord

from ..commands.ctx import CommandCtx
from ..embeds import build_embed
from ..summary import build_summary
from ..views import RSVPView


@dataclass
class PanelService:
    """
    Service responsible for the persistent RSVP panel message.

    .. rubric:: Attributes

    bot : :class:`discord.Client`
        Discord client used to access shared services (DB, timezone) and
        to fetch/edit messages in channels.
    """

    bot: discord.Client

    @property
    def db(self):
        """
        Convenience accessor for the bot database.

        Returns
        -------
        :class:`~rsvp_bot.db.core.DBCore`
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
            Timezone used for local scheduling checks and formatting.
        """
        return self.bot.tz

    async def create_new_panel(
        self,
        *,
        ctx: CommandCtx,
        workday_date: str,
        deadline_ts: int,
        on_choice: callable,
        on_choice_with_plan: callable,
    ) -> int:
        """
        Create a new RSVP panel message in the channel and pin it.

        This initializes the panel embed using the current directory membership and
        an empty RSVP set, and then posts a message with a persistent
        :class:`~rsvp_bot.views.RSVPView`.

        Parameters
        ----------
        ctx : :class:`~rsvp_bot.commands.ctx.CommandCtx`
            Command context identifying the guild/channel where the panel is created.
        workday_date : :class:`str`
            Workday date for the panel cycle (ISO ``YYYY-MM-DD``).
        deadline_ts : :class:`int`
            RSVP deadline as UTC epoch seconds.
        on_choice : :class:`callable`
            Callback invoked for “immediate” RSVP choices (e.g. maybe/no).
        on_choice_with_plan : :class:`callable`
            Callback invoked for RSVP choices that should open the plan modal
            (typically yes/remote).

        Returns
        -------
        :class:`int`
            The Discord message ID of the newly created panel.

        Raises
        ------
        :class:`discord.HTTPException`
            If Discord rejects the send request.
        """
        directory = await self.db.directory_list_active(
            guild_id=ctx.guild_id,
            channel_id=ctx.channel_id,
        )

        await self.db.clear_rsvps(
            guild_id=ctx.guild_id,
            channel_id=ctx.channel_id,
            workday_date=workday_date,
        )

        summary = build_summary(directory=directory, rsvps=[])
        embed = build_embed(workday_date=workday_date, deadline_ts=deadline_ts, summary=summary)

        msg = await ctx.channel.send(
            embed=embed,
            view=RSVPView(on_choice=on_choice, on_choice_with_plan=on_choice_with_plan),
        )
        try:
            await msg.pin(reason="Workday RSVP panel")
        except discord.Forbidden:
            # Pinning is optional; the panel still functions without it.
            pass

        return msg.id

    async def refresh_panel(
        self,
        *,
        ctx: CommandCtx,
        workday_date: str,
        on_choice: callable,
        on_choice_with_plan: callable,
    ) -> None:
        """
        Refresh the existing panel message embed and view.

        This recomputes the summary using the current directory and stored RSVPs,
        rebuilds the embed, and edits the existing panel message.

        Parameters
        ----------
        ctx : :class:`~rsvp_bot.commands.ctx.CommandCtx`
            Command context identifying the guild/channel where the panel lives.
        workday_date : :class:`str`
            Workday date for which RSVPs should be summarized (ISO ``YYYY-MM-DD``).
        on_choice : :class:`callable`
            Callback invoked for “immediate” RSVP choices (e.g. maybe/no).
        on_choice_with_plan : :class:`callable`
            Callback invoked for RSVP choices that should open the plan modal
            (typically yes/remote).

        Returns
        -------
        None
            This coroutine returns :class:`None`.

        Raises
        ------
        :class:`discord.Forbidden`
            If the bot lacks permissions to fetch or edit the message.
        :class:`discord.HTTPException`
            If Discord rejects the edit request.
        """
        directory = await self.db.directory_list_active(
            guild_id=ctx.guild_id,
            channel_id=ctx.channel_id,
        )
        rsvps = await self.db.list_rsvps(
            guild_id=ctx.guild_id,
            channel_id=ctx.channel_id,
            workday_date=workday_date,
        )
        deadline_ts = await self.db.get_deadline(
            guild_id=ctx.guild_id,
            channel_id=ctx.channel_id,
        )

        summary = build_summary(directory=directory, rsvps=rsvps)
        embed = build_embed(workday_date=workday_date, deadline_ts=deadline_ts, summary=summary)

        rsvp_message_id = await self.db.get_rsvp_message_id(
            guild_id=ctx.guild_id,
            channel_id=ctx.channel_id,
        )

        try:
            msg = await ctx.channel.fetch_message(rsvp_message_id)
            await msg.edit(
                embed=embed,
                view=RSVPView(on_choice=on_choice, on_choice_with_plan=on_choice_with_plan),
            )
        except discord.NotFound:
            # The panel message was deleted; callers can recreate via /setup.
            return

    async def cleanup_panel(self, *, ctx: CommandCtx, delete_message: bool = False) -> None:
        """
        Unpin the current panel message and optionally delete it.

        This is intended for rollover cleanup.

        Parameters
        ----------
        ctx : :class:`~rsvp_bot.commands.ctx.CommandCtx`
            Command context identifying the guild/channel where the panel lives.
        delete_message : :class:`bool`, optional
            If ``True``, delete the panel message after unpinning.

        Returns
        -------
        None
            This coroutine returns :class:`None`.

        Raises
        ------
        :class:`discord.NotFound`
            If the panel message no longer exists.
        :class:`discord.Forbidden`
            If the bot lacks permissions to fetch/unpin/delete.
        :class:`discord.HTTPException`
            If Discord rejects the unpin/delete request.
        """
        rsvp_message_id = await self.db.get_rsvp_message_id(
            guild_id=ctx.guild_id,
            channel_id=ctx.channel_id,
        )
        msg = await ctx.channel.fetch_message(rsvp_message_id)

        if msg.pinned:
            await msg.unpin(reason="Old workday RSVP panel (auto-cleanup)")

        if delete_message:
            await msg.delete(reason="Old workday RSVP panel (auto-cleanup)")

    async def reset_attendance(
        self,
        *,
        ctx: CommandCtx,
        workday_date: str,
        on_choice,
        on_choice_with_plan,
    ) -> tuple[int, int, int]:
        """
        Clear attendance-related state for a workday and refresh the panel.

        This removes:

        - RSVP rows for the workday
        - partner links for the workday
        - sent reminder records for the workday

        Parameters
        ----------
        ctx : :class:`~rsvp_bot.commands.ctx.CommandCtx`
            Command context identifying the guild/channel where the panel lives.
        workday_date : :class:`str`
            Workday date whose attendance data should be cleared (ISO ``YYYY-MM-DD``).
        on_choice : :class:`callable`
            Callback invoked for “immediate” RSVP choices (e.g. maybe/no).
        on_choice_with_plan : :class:`callable`
            Callback invoked for RSVP choices that should open the plan modal
            (typically yes/remote).

        Returns
        -------
        :class:`tuple` [:class:`int`, :class:`int`, :class:`int`]
            ``(deleted_rsvps, deleted_partners, deleted_reminders)``.

        Raises
        ------
        LookupError
            If no workday exists for this (guild_id, channel_id, workday_date).
        """
        deleted_rsvps = await self.db.clear_rsvps(
            guild_id=ctx.guild_id,
            channel_id=ctx.channel_id,
            workday_date=workday_date,
        )

        deleted_partners = await self.db.clear_work_partners(
            guild_id=ctx.guild_id,
            channel_id=ctx.channel_id,
            workday_date=workday_date,
        )

        deleted_reminders = await self.db.clear_sent_reminders(
            guild_id=ctx.guild_id,
            channel_id=ctx.channel_id,
            workday_date=workday_date,
        )

        await self.refresh_panel(
            ctx=ctx,
            workday_date=workday_date,
            on_choice=on_choice,
            on_choice_with_plan=on_choice_with_plan,
        )

        return int(deleted_rsvps), int(deleted_partners), int(deleted_reminders)

    async def set_deadline_in(
        self,
        *,
        ctx: CommandCtx,
        workday_date: str,
        new_deadline_ts: int,
        on_choice,
        on_choice_with_plan,
    ) -> None:
        """
        Update the stored deadline timestamp for the current workday and refresh the panel.

        Changing the deadline invalidates reminder history for the workday, so all
        ``sent_reminders`` rows for that workday are cleared.

        Parameters
        ----------
        ctx : :class:`~rsvp_bot.commands.ctx.CommandCtx`
            Command context identifying the guild/channel whose deadline is being updated.
        workday_date : :class:`str`
            Workday date whose reminder history should be cleared (ISO ``YYYY-MM-DD``).
        new_deadline_ts : :class:`int`
            New deadline as UTC epoch seconds.
        on_choice : :class:`callable`
            Callback invoked for “immediate” RSVP choices (e.g. maybe/no).
        on_choice_with_plan : :class:`callable`
            Callback invoked for RSVP choices that should open the plan modal
            (typically yes/remote).

        Returns
        -------
        None
            This coroutine returns :class:`None`.

        Raises
        ------
        LookupError
            If no active workday exists for this channel.
        """
        updated = await self.db.update_workday_deadline(
            guild_id=ctx.guild_id,
            channel_id=ctx.channel_id,
            deadline_ts=int(new_deadline_ts),
        )
        if updated == 0:
            raise LookupError("No active workday for this channel/date.")

        await self.db.clear_sent_reminders(
            guild_id=ctx.guild_id,
            channel_id=ctx.channel_id,
            workday_date=workday_date,
        )

        await self.refresh_panel(
            ctx=ctx,
            workday_date=workday_date,
            on_choice=on_choice,
            on_choice_with_plan=on_choice_with_plan,
        )

    async def set_deadline_at(
        self,
        *,
        ctx: CommandCtx,
        workday_date: str,
        deadline_local: datetime,
        on_choice,
        on_choice_with_plan,
    ) -> int:
        """
        Set the workday deadline using a timezone-aware local datetime.

        Parameters
        ----------
        ctx : :class:`~rsvp_bot.commands.ctx.CommandCtx`
            Command context identifying the guild/channel whose deadline is being updated.
        workday_date : :class:`str`
            Workday date whose reminder history should be cleared (ISO ``YYYY-MM-DD``).
        deadline_local : :class:`datetime.datetime`
            Timezone-aware local datetime in the bot/channel timezone.
        on_choice : :class:`callable`
            Callback invoked for “immediate” RSVP choices (e.g. maybe/no).
        on_choice_with_plan : :class:`callable`
            Callback invoked for RSVP choices that should open the plan modal
            (typically yes/remote).

        Returns
        -------
        :class:`int`
            The new deadline timestamp as UTC epoch seconds.

        Raises
        ------
        ValueError
            If ``deadline_local`` is naive (missing ``tzinfo``).
        LookupError
            If no active workday exists for this channel.
        """
        if deadline_local.tzinfo is None:
            raise ValueError("deadline_local must be timezone-aware.")

        new_deadline_ts = int(deadline_local.timestamp())

        await self.set_deadline_in(
            ctx=ctx,
            workday_date=workday_date,
            new_deadline_ts=new_deadline_ts,
            on_choice=on_choice,
            on_choice_with_plan=on_choice_with_plan,
        )

        return new_deadline_ts
