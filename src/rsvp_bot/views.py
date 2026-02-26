"""
Views
=====

Discord UI components used by the Workday RSVP Bot.

This module defines the interactive elements attached to the RSVP panel message,
including persistent RSVP buttons, an optional "plan" modal, and an optional
partner-selection flow. These views are designed to be used with callbacks
provided by higher-level services (e.g., RSVP logic), keeping UI wiring separate
from business rules.

Constants
---------

STATUS_EMOJI : :class:`dict` [:class:`str`, :class:`str`]
    Mapping from RSVP status keys (``yes``, ``remote``, ``maybe``, ``no``) to
    their emoji used in the UI.

Classes
-------

:class:`RSVPPlanModal`
    Modal that collects an optional free-text plan/note after selecting a status.

:class:`PartnerSelect`
    Select menu for choosing one or more partners from a provided option list.

:class:`PartnerSelectView`
    View wrapping :class:`~rsvp_bot.views.PartnerSelect` with a "Skip" button.

:class:`RSVPView`
    Persistent RSVP button view attached to the panel message.
"""
from __future__ import annotations

import discord

from .models import OnChoice, OnChoiceWithPlan, OnSubmitPartners, OnSubmitPlan

STATUS_EMOJI = {"yes": "✅", "remote": "🎥", "maybe": "❔", "no": "❌"}


class RSVPPlanModal(discord.ui.Modal):
    """
    Modal dialog for collecting optional RSVP details.

    This modal is typically shown after a user chooses an RSVP status that supports
    an optional "plan" note. When submitted, it delegates persistence and panel
    refresh to the provided callback.

    .. rubric:: Attributes

    plan : :class:`discord.ui.TextInput`
        Text input field where the user can optionally describe their plan.
    """

    def __init__(self, *, status: str, on_submit_plan: OnSubmitPlan):
        """
        Initialize the modal.

        Parameters
        ----------
        status : :class:`str`
            RSVP status associated with this modal submission (e.g. ``"yes"`` or
            ``"remote"``).
        on_submit_plan : :class:`~rsvp_bot.models.OnSubmitPlan`
            Callback invoked when the modal is submitted. The callback receives
            ``(interaction, status, note)`` where ``note`` may be :class:`None`.

        Returns
        -------
        None
            This initializer returns :class:`None`.
        """
        super().__init__(title="RSVP details (optional)")
        self._status = status
        self._on_submit_plan = on_submit_plan

        self.plan = discord.ui.TextInput(
            label="Plan",
            placeholder="(optional) e.g., calibrate camera, clean optics, test pipeline…",
            required=False,
            max_length=400,
            style=discord.TextStyle.paragraph,
        )
        self.add_item(self.plan)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """
        Handle modal submission.

        The entered plan is normalized (trimmed). If non-empty, it is formatted as
        ``"Plan: <text>"``; otherwise, the note is :class:`None`. The resulting
        note is passed to the configured callback.

        Parameters
        ----------
        interaction : :class:`discord.Interaction`
            The interaction associated with the modal submission.

        Returns
        -------
        None
            This coroutine returns :class:`None`.
        """
        plan = (self.plan.value or "").strip()
        note = f"Plan: {plan}" if plan else None
        await self._on_submit_plan(interaction, self._status, note)


class PartnerSelect(discord.ui.Select):
    """
    Select menu for choosing work partners.

    This component collects one or more partner selections and delegates handling
    to the parent :class:`~rsvp_bot.views.PartnerSelectView` via its configured
    callback.

    .. rubric:: Attributes

    values : :class:`list` [:class:`str`]
        Selected option values returned by Discord (string IDs). This attribute is
        provided by :class:`discord.ui.Select`.
    """

    def __init__(self, *, options: list[discord.SelectOption]):
        """
        Initialize the select menu.

        Parameters
        ----------
        options : :class:`list` [:class:`discord.SelectOption`]
            Options presented to the user. At most 25 options are displayed due to
            Discord UI limits.

        Returns
        -------
        None
            This initializer returns :class:`None`.
        """
        super().__init__(
            placeholder="(optional) Select partner(s) to work with…",
            min_values=0,
            max_values=min(25, len(options)) if options else 1,
            options=options[:25],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """
        Handle a selection change.

        The selected values are converted to integer user IDs and passed to the
        parent view callback. If the select is not attached to a
        :class:`~rsvp_bot.views.PartnerSelectView`, the callback is a no-op.

        Parameters
        ----------
        interaction : :class:`discord.Interaction`
            The interaction associated with the selection.

        Returns
        -------
        None
            This coroutine returns :class:`None`.
        """
        view = self.view
        if not isinstance(view, PartnerSelectView):
            return
        partner_ids = [int(v) for v in self.values]
        await view._on_submit_partners(interaction, partner_ids)


class PartnerSelectView(discord.ui.View):
    """
    View for partner selection.

    This view wraps a :class:`~rsvp_bot.views.PartnerSelect` menu and provides a
    "Skip" button for users who do not want to select partners.

    .. rubric:: Attributes

    _on_submit_partners : :class:`~rsvp_bot.models.OnSubmitPartners`
        Callback invoked when the user submits partner selections (including the
        empty selection from "Skip").
    """

    def __init__(self, *, options: list[discord.SelectOption], on_submit_partners: OnSubmitPartners):
        """
        Initialize the partner selection view.

        Parameters
        ----------
        options : :class:`list` [:class:`discord.SelectOption`]
            Options to display in the select menu (typically directory members).
        on_submit_partners : :class:`~rsvp_bot.models.OnSubmitPartners`
            Callback invoked with ``(interaction, partner_ids)`` where
            ``partner_ids`` is a :class:`list` [:class:`int`].

        Returns
        -------
        None
            This initializer returns :class:`None`.
        """
        super().__init__(timeout=5 * 60)
        self._on_submit_partners = on_submit_partners
        self.add_item(PartnerSelect(options=options))

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """
        Skip partner selection.

        Parameters
        ----------
        interaction : :class:`discord.Interaction`
            The interaction associated with the button click.
        button : :class:`discord.ui.Button`
            The button instance that was clicked.

        Returns
        -------
        None
            This coroutine returns :class:`None`.
        """
        await self._on_submit_partners(interaction, [])


class RSVPView(discord.ui.View):
    """
    Persistent RSVP button view attached to the panel message.

    This view provides the primary RSVP actions:

    - Attending (opens the plan flow via ``on_choice_with_plan``)
    - Attending (Remote) (opens the plan flow via ``on_choice_with_plan``)
    - Maybe (records directly via ``on_choice``)
    - Not attending (records directly via ``on_choice``)

    The view is created with ``timeout=None`` to support persistence across bot
    restarts when registered via :meth:`discord.Client.add_view`.

    .. rubric:: Attributes

    _on_choice : :class:`~rsvp_bot.models.OnChoice`
        Callback invoked for status updates that do not require a plan modal.
    _on_choice_with_plan : :class:`~rsvp_bot.models.OnChoiceWithPlan`
        Callback invoked for status updates that may trigger an additional plan
        flow (e.g., showing :class:`~rsvp_bot.views.RSVPPlanModal`).
    """

    def __init__(self, *, on_choice: OnChoice, on_choice_with_plan: OnChoiceWithPlan):
        """
        Initialize the RSVP button view.

        Parameters
        ----------
        on_choice : :class:`~rsvp_bot.models.OnChoice`
            Callback invoked with ``(interaction, status, note)`` for immediate
            status changes. ``note`` may be :class:`None`.
        on_choice_with_plan : :class:`~rsvp_bot.models.OnChoiceWithPlan`
            Callback invoked with ``(interaction, status)`` for flows that may
            request additional input (e.g., a plan modal).

        Returns
        -------
        None
            This initializer returns :class:`None`.
        """
        super().__init__(timeout=None)
        self._on_choice = on_choice
        self._on_choice_with_plan = on_choice_with_plan

    @discord.ui.button(label="Attending", style=discord.ButtonStyle.success, custom_id="rsvp_yes", emoji="✅")
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Mark the user as attending (in person).

        Parameters
        ----------
        interaction : :class:`discord.Interaction`
            The interaction associated with the button click.
        button : :class:`discord.ui.Button`
            The button instance that was clicked.

        Returns
        -------
        None
            This coroutine returns :class:`None`.
        """
        await self._on_choice_with_plan(interaction, "yes")

    @discord.ui.button(label="Attending (Remote)", style=discord.ButtonStyle.primary, custom_id="rsvp_remote", emoji="🎥")
    async def remote(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Mark the user as attending remotely.

        Parameters
        ----------
        interaction : :class:`discord.Interaction`
            The interaction associated with the button click.
        button : :class:`discord.ui.Button`
            The button instance that was clicked.

        Returns
        -------
        None
            This coroutine returns :class:`None`.
        """
        await self._on_choice_with_plan(interaction, "remote")

    @discord.ui.button(label="Maybe", style=discord.ButtonStyle.secondary, custom_id="rsvp_maybe", emoji="❔")
    async def maybe(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Mark the user as a tentative attendee (maybe).

        Parameters
        ----------
        interaction : :class:`discord.Interaction`
            The interaction associated with the button click.
        button : :class:`discord.ui.Button`
            The button instance that was clicked.

        Returns
        -------
        None
            This coroutine returns :class:`None`.
        """
        await self._on_choice(interaction, "maybe", None)

    @discord.ui.button(label="Not attending", style=discord.ButtonStyle.danger, custom_id="rsvp_no", emoji="❌")
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Mark the user as not attending.

        Parameters
        ----------
        interaction : :class:`discord.Interaction`
            The interaction associated with the button click.
        button : :class:`discord.ui.Button`
            The button instance that was clicked.

        Returns
        -------
        None
            This coroutine returns :class:`None`.
        """
        await self._on_choice(interaction, "no", None)
