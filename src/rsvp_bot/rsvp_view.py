from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

import discord


STATUS_EMOJI = {
    "yes": "✅",
    "remote": "🎥",
    "maybe": "❔",
    "no": "❌",
}
STATUS_LABEL = {
    "yes": "Attending (In person)",
    "remote": "Attending (Remote)",
    "maybe": "Maybe",
    "no": "Not attending",
}


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

    return Summary(
        yes=sorted(yes),
        remote=sorted(remote),
        maybe=sorted(maybe),
        no=sorted(no),
        missing=missing,
    )



def _fmt_users(ids: list[int]) -> str:
    if not ids:
        return "—"
    return " ".join(f"<@{i}>" for i in ids)


def build_embed(*, workday_date: str, deadline_ts: int, summary: Summary) -> discord.Embed:
    deadline = datetime.fromtimestamp(deadline_ts)
    e = discord.Embed(
        title=f"Workday RSVP — {workday_date}",
        description=f"Deadline: <t:{int(deadline.timestamp())}:f>",
    )
    e.add_field(name=f"{STATUS_EMOJI['yes']} Attending ({len(summary.yes)})", value=_fmt_users(summary.yes), inline=False)
    e.add_field(name=f"{STATUS_EMOJI['remote']} Attending (Remote) ({len(summary.remote)})", value=_fmt_users(summary.remote), inline=False)
    e.add_field(name=f"{STATUS_EMOJI['maybe']} Maybe ({len(summary.maybe)})", value=_fmt_users(summary.maybe), inline=False)
    e.add_field(name=f"{STATUS_EMOJI['no']} Not attending ({len(summary.no)})", value=_fmt_users(summary.no), inline=False)
    e.add_field(name=f"⏳ Missing ({len(summary.missing)})", value=_fmt_users(summary.missing), inline=False)
    e.set_footer(text="Click a button below to set/update your RSVP.")
    return e


class RSVPView(discord.ui.View):
    def __init__(self, *, on_choice):
        super().__init__(timeout=None)
        self._on_choice = on_choice

    @discord.ui.button(
        label="Attending",
        style=discord.ButtonStyle.success,
        custom_id="rsvp_yes",
        emoji="✅",
    )
    async def yes(self, interaction, button):
        await self._on_choice(interaction, "yes")

    @discord.ui.button(
        label="Attending (Remote)",
        style=discord.ButtonStyle.primary,
        custom_id="rsvp_remote",
        emoji="🎥",
    )
    async def remote(self, interaction, button):
        await self._on_choice(interaction, "remote")

    @discord.ui.button(
        label="Maybe",
        style=discord.ButtonStyle.secondary,
        custom_id="rsvp_maybe",
        emoji="❔",
    )
    async def maybe(self, interaction, button):
        await self._on_choice(interaction, "maybe")

    @discord.ui.button(
        label="Not attending",
        style=discord.ButtonStyle.danger,
        custom_id="rsvp_no",
        emoji="❌",
    )
    async def no(self, interaction, button):
        await self._on_choice(interaction, "no")

