# tests/test_summary_and_embeds.py

"""
Tests for summary aggregation and embed formatting.

These are pure/pure-ish helpers that should remain deterministic.

We skip embed construction if ``discord.py`` is not installed in the active
environment, since :func:`rsvp_bot.embeds.build_embed` constructs a real
:class:`discord.Embed`.
"""

from __future__ import annotations

import importlib.util

import pytest

from rsvp_bot.models import Summary
from rsvp_bot.summary import build_summary


def test_build_summary_buckets_and_missing_sorted():
    directory = [3, 1, 2]
    rsvps = [(2, "yes"), (3, "no"), (999, "maybe"), (1, "remote"), (4, "weird")]

    s = build_summary(directory=directory, rsvps=rsvps)

    assert s.yes == [2]
    assert s.remote == [1]
    assert s.no == [3]
    # user 999 is not in directory but still counted as "maybe" response bucket
    assert s.maybe == [999]
    # missing are directory members who did not respond -> none here because 1,2,3 responded
    assert s.missing == []


@pytest.mark.skipif(importlib.util.find_spec("discord") is None, reason="discord.py not installed")
def test_fmt_users_empty_and_mentions():
    from rsvp_bot.embeds import _fmt_users

    assert _fmt_users([]) == "—"
    assert _fmt_users([5, 10]) == "<@5> <@10>"


@pytest.mark.skipif(importlib.util.find_spec("discord") is None, reason="discord.py not installed")
def test_build_embed_field_counts_and_values():
    from rsvp_bot.embeds import build_embed

    summary = Summary(yes=[1, 2], remote=[3], maybe=[], no=[4], missing=[5, 6, 7])
    e = build_embed(workday_date="2026-02-28", deadline_ts=1700000000, summary=summary)

    assert e.title == "Workday RSVP — 2026-02-28"
    assert "Deadline:" in (e.description or "")

    names = [f.name for f in e.fields]
    assert any("Attending (2)" in n for n in names)
    assert any("Remote" in n and "(1)" in n for n in names)
    assert any("Maybe (0)" in n for n in names)
    assert any("Not attending (1)" in n for n in names)
    assert any("Missing (3)" in n for n in names)

    yes_field = next(f for f in e.fields if "Attending (2)" in f.name)
    assert "<@1>" in yes_field.value and "<@2>" in yes_field.value


