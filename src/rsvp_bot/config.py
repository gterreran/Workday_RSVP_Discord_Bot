"""
Configuration and defaults
==========================

Central configuration values and runtime configuration loading.

This module defines:

- Default scheduling constants used to initialize new channels
- The :class:`Config` runtime configuration model
- The :func:`load_config` helper that loads environment-based settings

Constants
---------

DEFAULT_WORKDAY_WEEKDAY : :class:`int`
    Default weekday for the workday cycle (0=Mon … 6=Sun).

DEFAULT_WORKDAY_WEEKDAY_DEADLINE : :class:`int`
    Deadline offset in hours relative to workday midnight.
    Negative values indicate the previous day.

DEFAULT_OFFSETS_MIN : :class:`str`
    Default reminder offsets expressed as comma-separated minutes.

DEFAULT_ROLLOVER_WEEKDAY : :class:`int`
    Default weekday when rollover occurs (0=Mon … 6=Sun).

DEFAULT_ROLLOVER_TIME : :class:`str`
    Default rollover time in local ``HH:MM`` format.

Classes
-------

:class:`Config`
    Runtime configuration container loaded from environment variables.

Functions
---------

:func:`load_config`
    Load runtime configuration from environment variables and filesystem.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_WORKDAY_WEEKDAY = 5  # Saturday
DEFAULT_WORKDAY_WEEKDAY_DEADLINE = -6  # 6 hours before workday midnight
DEFAULT_OFFSETS_MIN = "2880,1440,360,60"  # 48h, 24h, 6h, 1h
DEFAULT_ROLLOVER_WEEKDAY = 0  # Monday
DEFAULT_ROLLOVER_TIME = "09:00"


@dataclass(frozen=True)
class Config:
    """
    Runtime configuration for the bot.

    Instances of this class are produced by :func:`load_config` and passed
    into the bot during initialization.

    .. rubric:: Attributes

    token : :class:`str`
        Discord bot token used for authentication.
    tz : :class:`str`
        IANA timezone string used for scheduling and display.
    db_path : :class:`pathlib.Path`
        Filesystem path to the SQLite database file.
    """

    token: str
    tz: str
    db_path: Path


def load_config() -> Config:
    """
    Load runtime configuration from environment variables.

    This function reads required and optional configuration values and
    prepares filesystem paths for the bot runtime.

    Environment variables
    ---------------------
    DISCORD_TOKEN
        Required Discord bot token.

    BOT_TIMEZONE
        Optional timezone string (defaults to ``America/Chicago``).

    Returns
    -------
    :class:`Config`
        Fully populated runtime configuration object.

    Raises
    ------
    RuntimeError
        If the required ``DISCORD_TOKEN`` environment variable is missing.
    """
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Missing DISCORD_TOKEN in environment (.env).")

    tz = os.getenv("BOT_TIMEZONE", "America/Chicago").strip() or "America/Chicago"

    # Store DB in ./data/bot.db (relative to repo root)
    db_path = Path("data") / "bot.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    return Config(token=token, tz=tz, db_path=db_path)
