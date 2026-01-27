# rsvp_bot/rsvp_view.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Callable, Awaitable

import discord


STATUS_EMOJI = {"yes": "✅", "remote": "🎥", "maybe": "❔", "no": "❌"}


@dataclass(frozen=True)
class Summary:
    yes: list[int]
    remote: list[int]
    maybe: list[int]
    no: list[int]
    missing: list[int]


def build_summary(*, directory: Iterable[int], rsvps: list[tuple[int, str]]) -> Summary:
    directory_set = set(directory)

    yes: list[int] = []
    remote: list[int] = []
    maybe: list[int] = []
    no: list[int] = []
    responded: set[int] = set()

    for user_id, status in rsvps:
        responded.add(user_id)
        if status == "yes":
            yes.append(user_id)
        elif status == "remote":
            remote.append(user_id)
        elif status == "maybe":
            maybe.append(user_id)
        elif status == "no":
            no.append(user_id)

    missing = sorted(directory_set - responded)
    return Summary(yes=sorted(yes), remote=sorted(remote), maybe=sorted(maybe), no=sorted(no), missing=missing)


def _fmt_users(ids: list[int]) -> str:
    return "—" if not ids else " ".join(f"<@{i}>" for i in ids)


def build_embed(*, workday_date: str, deadline_ts: int, summary: Summary) -> discord.Embed:
    e = discord.Embed(
        title=f"Workday RSVP — {workday_date}",
        description=f"Deadline: <t:{int(deadline_ts)}:f>",
    )
    e.add_field(name=f"{STATUS_EMOJI['yes']} Attending ({len(summary.yes)})", value=_fmt_users(summary.yes), inline=False)
    e.add_field(
        name=f"{STATUS_EMOJI['remote']} Attending (Remote) ({len(summary.remote)})",
        value=_fmt_users(summary.remote),
        inline=False,
    )
    e.add_field(name=f"{STATUS_EMOJI['maybe']} Maybe ({len(summary.maybe)})", value=_fmt_users(summary.maybe), inline=False)
    e.add_field(name=f"{STATUS_EMOJI['no']} Not attending ({len(summary.no)})", value=_fmt_users(summary.no), inline=False)
    e.add_field(name=f"⏳ Missing ({len(summary.missing)})", value=_fmt_users(summary.missing), inline=False)
    e.set_footer(text="Click a button below to set/update your RSVP.")
    return e


# ----------------------------
# Modal (plan only)
# ----------------------------

OnSubmitPlan = Callable[[discord.Interaction, str, str | None], Awaitable[None]]


class RSVPPlanModal(discord.ui.Modal):
    def __init__(self, *, status: str, on_submit_plan: OnSubmitPlan):
        super().__init__(title="RSVP details (optional)")
        self._status = status
        self._on_submit_plan = on_submit_plan

        # Label must be 1..45 chars
        self.plan = discord.ui.TextInput(
            label="Plan",
            placeholder="(optional) e.g., calibrate camera, clean optics, test pipeline…",
            required=False,
            max_length=400,
            style=discord.TextStyle.paragraph,
        )
        self.add_item(self.plan)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        plan = (self.plan.value or "").strip()
        note = f"Plan: {plan}" if plan else None
        await self._on_submit_plan(interaction, self._status, note)


# ----------------------------
# Ephemeral partner picker
# ----------------------------

OnSubmitPartners = Callable[[discord.Interaction, list[int]], Awaitable[None]]


class PartnerSelect(discord.ui.Select):
    def __init__(self, *, options: list[discord.SelectOption]):
        super().__init__(
            placeholder="(optional) Select partner(s) to work with…",
            min_values=0,
            max_values=min(25, len(options)) if options else 1,
            options=options[:25],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, PartnerSelectView):
            return
        partner_ids = [int(v) for v in self.values]
        await view._on_submit_partners(interaction, partner_ids)


class PartnerSelectView(discord.ui.View):
    def __init__(self, *, options: list[discord.SelectOption], on_submit_partners: OnSubmitPartners):
        super().__init__(timeout=5 * 60)
        self._on_submit_partners = on_submit_partners
        self.add_item(PartnerSelect(options=options))

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._on_submit_partners(interaction, [])


# ----------------------------
# Persistent RSVP panel buttons
# ----------------------------

OnChoice = Callable[[discord.Interaction, str, str | None], Awaitable[None]]
OnChoiceWithPlan = Callable[[discord.Interaction, str], Awaitable[None]]


class RSVPView(discord.ui.View):
    def __init__(self, *, on_choice: OnChoice, on_choice_with_plan: OnChoiceWithPlan):
        super().__init__(timeout=None)
        self._on_choice = on_choice
        self._on_choice_with_plan = on_choice_with_plan

    @discord.ui.button(label="Attending", style=discord.ButtonStyle.success, custom_id="rsvp_yes", emoji="✅")
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._on_choice_with_plan(interaction, "yes")

    @discord.ui.button(label="Attending (Remote)", style=discord.ButtonStyle.primary, custom_id="rsvp_remote", emoji="🎥")
    async def remote(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._on_choice_with_plan(interaction, "remote")

    @discord.ui.button(label="Maybe", style=discord.ButtonStyle.secondary, custom_id="rsvp_maybe", emoji="❔")
    async def maybe(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._on_choice(interaction, "maybe", None)

    @discord.ui.button(label="Not attending", style=discord.ButtonStyle.danger, custom_id="rsvp_no", emoji="❌")
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._on_choice(interaction, "no", None)
