# src/rsvp_bot/db/migrations.py

"""
SQLite schema definition
========================

Declarative definition of the RSVP bot SQLite schema.

This module defines the SQL statements used to create the database tables
required by the bot. The schema is expressed as a single SQL string
(:data:`SCHEMA`) that is executed during database initialization.

The SQL uses constants from :mod:`rsvp_bot.db.schema` for all table and column
names to avoid duplicated string literals and to keep migrations, queries, and
schema documentation aligned.

Constants
---------

:const:`SCHEMA`
    Full SQL schema for the bot database, including WAL journal mode and
    ``CREATE TABLE IF NOT EXISTS`` statements for all required tables.
"""

from __future__ import annotations

from .schema import (
    ChannelColumns as CH,
)
from .schema import (
    DirectoryColumns as D,
)
from .schema import (
    RSVPsColumns as R,
)
from .schema import (
    SentRemindersColumns as SR,
)
from .schema import (
    Tables as T,
)
from .schema import (
    WorkPairsColumns as WP,
)

SCHEMA = f"""
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS {T.CHANNEL} (
  {CH.GUILD_ID}             INTEGER NOT NULL,
  {CH.CHANNEL_ID}           INTEGER NOT NULL,
  {CH.REMINDER_OFFSETS}     TEXT NOT NULL,    -- comma-separated minutes, e.g. "2880,1440,360,60"
  {CH.WORKDAY_DATE}         TEXT NOT NULL,    -- YYYY-MM-DD
  {CH.DEADLINE_TS}          INTEGER NOT NULL, -- UTC timestamp
  {CH.RSVP_MESSAGE_ID}      INTEGER NOT NULL,
  {CH.ROLLOVER_WEEKDAY}     INTEGER NOT NULL, -- 0=Mon .. 6=Sun
  {CH.ROLLOVER_TIME}        TEXT NOT NULL,    -- 'HH:MM' local time
  PRIMARY KEY ({CH.GUILD_ID}, {CH.CHANNEL_ID})
);

CREATE TABLE IF NOT EXISTS {T.DIRECTORY} (
  {D.GUILD_ID}              INTEGER NOT NULL,
  {D.CHANNEL_ID}            INTEGER NOT NULL,
  {D.USER_ID}               INTEGER NOT NULL,
  {D.ACTIVE}                INTEGER NOT NULL DEFAULT 1,
  {D.ADDED_BY}              INTEGER,
  {D.ADDED_AT_TS}           INTEGER NOT NULL,
  PRIMARY KEY ({D.GUILD_ID}, {D.CHANNEL_ID}, {D.USER_ID})
);

CREATE TABLE IF NOT EXISTS {T.RSVPS} (
  {R.GUILD_ID}              INTEGER NOT NULL,
  {R.CHANNEL_ID}            INTEGER NOT NULL,
  {R.WORKDAY_DATE}          TEXT NOT NULL,   -- YYYY-MM-DD
  {R.USER_ID}               INTEGER NOT NULL,
  {R.STATUS}                TEXT NOT NULL,   -- yes|no|maybe|remote (as used elsewhere)
  {R.NOTE}                  TEXT,
  {R.UPDATED_AT_TS}         INTEGER NOT NULL,
  PRIMARY KEY ({R.GUILD_ID}, {R.CHANNEL_ID}, {R.WORKDAY_DATE}, {R.USER_ID})
);

CREATE TABLE IF NOT EXISTS {T.SENT_REMINDERS} (
  {SR.GUILD_ID}            INTEGER NOT NULL,
  {SR.CHANNEL_ID}          INTEGER NOT NULL,
  {SR.WORKDAY_DATE}        TEXT NOT NULL,
  {SR.OFFSET_MIN}          INTEGER NOT NULL,
  {SR.SENT_AT_TS}          INTEGER NOT NULL,
  PRIMARY KEY ({SR.GUILD_ID}, {SR.CHANNEL_ID}, {SR.WORKDAY_DATE}, {SR.OFFSET_MIN})
);

CREATE TABLE IF NOT EXISTS {T.WORK_PAIRS} (
  {WP.GUILD_ID}      INTEGER NOT NULL,
  {WP.CHANNEL_ID}    INTEGER NOT NULL,
  {WP.WORKDAY_DATE}  TEXT NOT NULL,
  {WP.USER_ID}       INTEGER NOT NULL,  -- the person who wrote the plan
  {WP.PARTNER_ID}    INTEGER NOT NULL,  -- the person they plan to work with
  {WP.CREATED_AT_TS} INTEGER NOT NULL,
  PRIMARY KEY ({WP.GUILD_ID}, {WP.CHANNEL_ID}, {WP.WORKDAY_DATE}, {WP.USER_ID}, {WP.PARTNER_ID})
);
"""
