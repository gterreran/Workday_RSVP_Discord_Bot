# src/rsvp_bot/services/rsvp_service.py

"""
RSVP interaction flow service
=============================

Service layer that implements the end-to-end RSVP interaction flow for users.

This module defines :class:`~rsvp_bot.services.rsvp_service.RSVPService`, which:

- Handles button interactions from the persistent RSVP panel (:class:`~rsvp_bot.views.RSVPView`).
- Collects optional RSVP details via a modal (:class:`~rsvp_bot.views.RSVPPlanModal`).
- Optionally collects partner selections via an ephemeral dropdown
  (:class:`~rsvp_bot.views.PartnerSelectView`).
- Persists RSVP state, notes, and partner relationships to the database.
- Refreshes the panel embed to reflect the latest summary.

The RSVP flow is designed to be user-facing and low friction:

- ``maybe`` and ``no`` record immediately (no modal).
- ``yes`` and ``remote`` prompt for an optional plan, then optionally partner selection.

Classes
-------

:class:`~rsvp_bot.services.rsvp_service.RSVPService`
    Coordinates RSVP UI callbacks and persistence, and refreshes the RSVP panel.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import discord

from ..commands.ctx import get_ctx
from ..views import PartnerSelectView, RSVPPlanModal


@dataclass
class RSVPService:
    """
    Service implementing RSVP button/modals/dropdowns and persistence.

    .. rubric:: Attributes

    bot : :class:`discord.Client`
        Discord client instance used to access shared services (DB, panel) and
        guild/member APIs.
    _pending_partner_flow : :class:`dict` [:class:`tuple` [:class:`int`, :class:`int`, :class:`int`, :class:`str`], :class:`tuple` [:class:`str`, :class:`str` | :class:`None`]]
        In-memory stash that tracks in-progress partner selection flows.

        Keys are ``(guild_id, channel_id, user_id, workday_date)`` and values are
        ``(status, note)`` captured when the plan modal is submitted.
    """

    bot: discord.Client

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
            Timezone used for local scheduling checks and formatting.
        """
        return self.bot.tz

    @property
    def panel(self):
        """
        Convenience accessor for the panel service.

        Returns
        -------
        :class:`~rsvp_bot.services.panel_service.PanelService`
            Service used to refresh RSVP panels after state changes.
        """
        return self.bot.panel

    # (guild_id, channel_id, user_id, workday_date) -> (status, note)
    _pending_partner_flow: dict[tuple[int, int, int, str], tuple[str, str | None]] = field(
        default_factory=dict, init=False
    )

    # ------------------------------------------------------------------
    # Public callbacks that Views/Commands should call
    # ------------------------------------------------------------------

    async def on_choice(self, interaction: discord.Interaction, status: str, note: str | None = None) -> None:
        """
        Handle an RSVP choice coming from the UI.

        For ``yes`` / ``remote`` this opens the plan modal so optional plan text
        (and then partners) can be collected. For all other statuses, the RSVP is
        recorded immediately.

        Parameters
        ----------
        interaction : :class:`discord.Interaction`
            Interaction that triggered the callback.
        status : :class:`str`
            RSVP status value (e.g. ``"yes"``, ``"remote"``, ``"maybe"``, ``"no"``).
        note : :class:`str` | :class:`None`, optional
            Optional note to associate with the RSVP when writing immediately.

        Returns
        -------
        None
            This coroutine returns :class:`None`.
        """
        if status in ("yes", "remote"):
            await self._open_plan_modal(interaction, status=status)
            return

        await self._set_rsvp_and_refresh(interaction, status=status, note=note)

    async def on_choice_with_plan(self, interaction: discord.Interaction, status: str) -> None:
        """
        Handle a choice that always opens the plan modal.

        This is used by buttons that are explicitly “attending” options.

        Parameters
        ----------
        interaction : :class:`discord.Interaction`
            Interaction that triggered the callback.
        status : :class:`str`
            RSVP status value (typically ``"yes"`` or ``"remote"``).

        Returns
        -------
        None
            This coroutine returns :class:`None`.
        """
        await self._open_plan_modal(interaction, status=status)

    # ------------------------------------------------------------------
    # Modal / dropdown flow
    # ------------------------------------------------------------------

    async def _open_plan_modal(self, interaction: discord.Interaction, status: str) -> None:
        """
        Open the RSVP plan modal.

        Parameters
        ----------
        interaction : :class:`discord.Interaction`
            Interaction that should receive the modal response.
        status : :class:`str`
            RSVP status to be recorded after the modal submission.

        Returns
        -------
        None
            This coroutine returns :class:`None`.
        """
        modal = RSVPPlanModal(status=status, on_submit_plan=self._after_plan_submit)
        await interaction.response.send_modal(modal)

    async def _after_plan_submit(self, interaction: discord.Interaction, status: str, note: str | None) -> None:
        """
        Handle submission of the plan modal.

        This writes the RSVP (and note), refreshes the panel, and then (for
        ``yes``/``remote``) posts a single ephemeral message containing an
        optional partner selector.

        Parameters
        ----------
        interaction : :class:`discord.Interaction`
            Interaction created by the modal submission.
        status : :class:`str`
            RSVP status selected by the user.
        note : :class:`str` | :class:`None`
            Optional note derived from the modal contents.

        Returns
        -------
        None
            This coroutine returns :class:`None`.
        """
        if not interaction.guild or not interaction.channel:
            await interaction.followup.send("This can only be used in a server channel.", ephemeral=True)
            return

        ctx = await get_ctx(interaction)

        workday_date = await self.db.get_workday_date(
            guild_id=ctx.guild_id,
            channel_id=ctx.channel_id,
        )
        now_ts = int(time.time())

        # Save RSVP + note
        await self.db.set_rsvp(
            guild_id=ctx.guild_id,
            channel_id=ctx.channel_id,
            workday_date=workday_date,
            user_id=ctx.user_id,
            status=status,
            note=note,
            updated_at_ts=now_ts,
        )

        # If not attending/remote -> clear partners immediately, refresh panel, ack
        if status not in ("yes", "remote"):
            await self.db.replace_work_partners(
                guild_id=ctx.guild_id,
                channel_id=ctx.channel_id,
                workday_date=workday_date,
                user_id=ctx.user_id,
                partner_ids=[],
                created_at_ts=now_ts,
            )

            await self.panel.refresh_panel(
                ctx=ctx,
                workday_date=workday_date,
                on_choice=self.on_choice,
                on_choice_with_plan=self.on_choice_with_plan,
            )
            await interaction.followup.send(f"Recorded: **{status}**", ephemeral=True)
            return

        # Build directory-only partner options with real display names
        directory = await self.db.directory_list_active(
            guild_id=ctx.guild_id,
            channel_id=ctx.channel_id,
        )
        candidates = [uid for uid in sorted(set(directory)) if uid != ctx.user_id]

        # No partner candidates -> refresh panel, ack
        if not candidates:
            await self.panel.refresh_panel(
                ctx=ctx,
                workday_date=workday_date,
                on_choice=self.on_choice,
                on_choice_with_plan=self.on_choice_with_plan,
            )
            await interaction.followup.send(
                f"Recorded: **{status}**" + ("" if not note else " (with note)") + "\nNo other directory members to select.",
                ephemeral=True,
            )
            return

        # Discord selects: max 25 options
        options: list[discord.SelectOption] = []
        for uid in candidates[:25]:
            member = interaction.guild.get_member(uid)
            if member is None:
                try:
                    member = await interaction.guild.fetch_member(uid)
                except discord.HTTPException:
                    member = None

            label = (member.display_name if member else f"User {uid}")[:100]
            options.append(discord.SelectOption(label=label, value=str(uid)))

        # Stash pending flow so partner select callback can complete it
        key = (ctx.guild_id, ctx.channel_id, ctx.user_id, workday_date)
        self._pending_partner_flow[key] = (status, note)

        view = PartnerSelectView(options=options, on_submit_partners=self._after_partner_select)

        msg = f"Recorded: **{status}**" + ("" if not note else " (with note)") + "\nSelect partners (optional):"
        await interaction.followup.send(msg, ephemeral=True, view=view)

    async def _after_partner_select(self, interaction: discord.Interaction, partner_ids: list[int]) -> None:
        """
        Handle partner selection from the dropdown view.

        This callback persists partner relationships for the current workday and
        refreshes the panel summary. Partner selections are constrained to:

        - directory members only
        - excluding the user themselves

        Parameters
        ----------
        interaction : :class:`discord.Interaction`
            Interaction created by the select menu or the “Skip” button.
        partner_ids : :class:`list` [:class:`int`]
            Selected partner user IDs.

        Returns
        -------
        None
            This coroutine returns :class:`None`.
        """
        if not interaction.guild or not interaction.channel:
            await interaction.followup.send("This can only be used in a server channel.", ephemeral=True)
            return

        ctx = await get_ctx(interaction)
        workday_date = await self.db.get_workday_date(
            guild_id=ctx.guild_id,
            channel_id=ctx.channel_id,
        )
        now_ts = int(time.time())

        key = (ctx.guild_id, ctx.channel_id, ctx.user_id, workday_date)
        if key in self._pending_partner_flow:
            status, _note = self._pending_partner_flow.pop(key)
        else:
            # Flow expired/restarted; still save partners safely.
            status = "yes"

        # Enforce directory-only and exclude self
        directory = await self.db.directory_list_active(
            guild_id=ctx.guild_id,
            channel_id=ctx.channel_id,
        )
        directory_set = set(directory)
        cleaned = sorted({pid for pid in (partner_ids or []) if pid != ctx.user_id and pid in directory_set})

        await self.db.replace_work_partners(
            guild_id=ctx.guild_id,
            channel_id=ctx.channel_id,
            workday_date=workday_date,
            user_id=ctx.user_id,
            partner_ids=cleaned,
            created_at_ts=now_ts,
        )

        await self.panel.refresh_panel(
            ctx=ctx,
            workday_date=workday_date,
            on_choice=self.on_choice,
            on_choice_with_plan=self.on_choice_with_plan,
        )

        # Respond to the select interaction (must respond)
        if cleaned:
            pretty = " ".join(f"<@{uid}>" for uid in cleaned)
            await interaction.followup.send(f"Saved partners: {pretty}", ephemeral=True)
        else:
            await interaction.followup.send("Saved partners: (none)", ephemeral=True)

        # Optional safeguard: if someone somehow selects partners while not attending, clear them
        if status not in ("yes", "remote") and cleaned:
            await self.db.replace_work_partners(
                guild_id=ctx.guild_id,
                channel_id=ctx.channel_id,
                workday_date=workday_date,
                partner_ids=[],
                created_at_ts=now_ts,
            )
            await self.panel.refresh_panel(
                ctx=ctx,
                workday_date=workday_date,
                on_choice=self.on_choice,
                on_choice_with_plan=self.on_choice_with_plan,
            )

    # ------------------------------------------------------------------
    # Immediate RSVP path (no modal)
    # ------------------------------------------------------------------

    async def _set_rsvp_and_refresh(self, interaction: discord.Interaction, status: str, note: str | None) -> None:
        """
        Record an RSVP immediately and refresh the panel.

        This is the “no modal” path used by the ``maybe`` and ``no`` buttons.

        Parameters
        ----------
        interaction : :class:`discord.Interaction`
            Interaction that triggered the RSVP update.
        status : :class:`str`
            RSVP status to persist.
        note : :class:`str` | :class:`None`
            Optional note to store with the RSVP.

        Returns
        -------
        None
            This coroutine returns :class:`None`.
        """
        if not interaction.guild or not interaction.channel:
            await interaction.followup.send("This can only be used in a server channel.", ephemeral=True)
            return

        ctx = await get_ctx(interaction)
        workday_date = await self.db.get_workday_date(
            guild_id=ctx.guild_id,
            channel_id=ctx.channel_id,
        )
        now_ts = int(time.time())

        prev = await self.db.get_rsvp(
            guild_id=ctx.guild_id,
            channel_id=ctx.channel_id,
            workday_date=workday_date,
            user_id=ctx.user_id,
        )
        prev_status = prev[0] if prev else None

        await self.db.set_rsvp(
            guild_id=ctx.guild_id,
            channel_id=ctx.channel_id,
            workday_date=workday_date,
            user_id=ctx.user_id,
            status=status,
            note=note,
            updated_at_ts=now_ts,
        )

        # Clear partners when not attending/remote
        if status not in ("yes", "remote"):
            await self.db.replace_work_partners(
                guild_id=ctx.guild_id,
                channel_id=ctx.channel_id,
                workday_date=workday_date,
                user_id=ctx.user_id,
                partner_ids=[],
                created_at_ts=now_ts,
            )

        await self.panel.refresh_panel(
            ctx=ctx,
            workday_date=workday_date,
            on_choice=self.on_choice,
            on_choice_with_plan=self.on_choice_with_plan,
        )

        # Safeguard notification when switching to "no"
        if status == "no" and prev_status != "no":
            dependents = await self.db.get_dependent_users(
                guild_id=ctx.guild_id,
                channel_id=ctx.channel_id,
                workday_date=workday_date,
                partner_id=ctx.user_id,
            )
            if dependents:
                mentions = " ".join(f"<@{uid}>" for uid in sorted(set(dependents)))
                try:
                    await interaction.channel.send(
                        f"⚠️ Heads up {mentions}: <@{ctx.user_id}> just updated their RSVP to ❌ **Not attending**. "
                        f"You listed them as someone you planned to work with."
                    )
                except discord.Forbidden:
                    pass

        await interaction.followup.send(f"Recorded: **{status}**", ephemeral=True)
