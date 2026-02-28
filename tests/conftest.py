# tests/conftest.py

"""
Global pytest fixtures for the RSVP bot test suite.
 
This file centralizes reusable fixtures like temporary databases and
common IDs. Keeping them here helps tests stay focused on behavior
rather than setup boilerplate.
"""
 
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Allow running tests against a non-installed checkout.
_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from rsvp_bot.db import DB

 
@pytest.fixture(scope="session")
def package_name() -> str:
    """Simple fixture used by smoke tests and future param tests."""
    return "rsvp_bot"


@pytest.fixture()
def ids() -> dict[str, int]:
    """
    Stable, human-readable IDs used across tests.

    Returns
    -------
    :class:`dict` [:class:`str`, :class:`int`]
        Common IDs for guild/channel/users.
    """
    return {
        "guild_id": 111,
        "channel_id": 222,
        "user_a": 1001,
        "user_b": 1002,
        "user_c": 1003,
        "admin": 9999,
    }


@pytest.fixture()
async def db(tmp_path: Path) -> DB:
    """
    Provide an initialized, isolated SQLite database for a single test.

    Parameters
    ----------
    tmp_path : :class:`pathlib.Path`
        Pytest-provided temporary directory unique to the test.

    Returns
    -------
    :class:`~rsvp_bot.db.DB`
        Initialized database facade ready for operations.
    """
    path = tmp_path / "test.sqlite3"
    db = DB(path=path)
    await db.init()
    return db
