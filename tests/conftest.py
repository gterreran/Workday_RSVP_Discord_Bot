"""
Global pytest fixtures for the RSVP bot test suite.

Currently minimal, but this file is intentionally present so we can
add async fixtures, temp DBs, and fake Discord objects later without
changing test layout.
"""

import pytest


@pytest.fixture(scope="session")
def package_name() -> str:
    """Simple fixture used by smoke tests and future param tests."""
    return "rsvp_bot"
