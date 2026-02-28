# tests/test_smoke.py

"""
Basic smoke tests for the RSVP bot package.

These tests ensure the package imports correctly and the main entrypoint
is available. They act as a safety net for packaging and CI.

Note
----
The runtime dependencies include ``discord.py``. However, some contributors may
run unit tests in a minimal environment. Where appropriate, tests that require
Discord are skipped if the dependency is unavailable.
"""
 
from __future__ import annotations

import importlib.util

import pytest


def test_import_package():
    """The top-level package should be importable (without importing discord eagerly)."""
    import rsvp_bot  # noqa: F401
 
@pytest.mark.skipif(importlib.util.find_spec("discord") is None, reason="discord.py not installed")
def test_import_entrypoint_module():
    """The CLI entrypoint module should import without errors when discord.py is installed."""
    from rsvp_bot.bot import main  # noqa: F401
 
def test_package_has_main_symbol():
    """The top-level package should expose the lazy 'main' entrypoint."""
    import rsvp_bot

    assert hasattr(rsvp_bot, "main")
