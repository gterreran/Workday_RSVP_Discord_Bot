# src/rsvp_bot/db/schema.py

"""
Database schema constants
=========================

Centralized table and column name definitions for the RSVP bot database.

This module provides a single source of truth for all SQLite table names and
column identifiers used across the data access layer. It prevents hard-coded
string duplication and ensures consistency between migrations, queries,
and higher-level database operations.

The constants are grouped into lightweight namespace classes to mirror the
logical database structure. Each class simply contains string attributes and
does not represent a runtime model.

Classes
-------

:class:`Tables`
    Canonical table name constants used throughout the database layer.

:class:`ChannelColumns`
    Column names for the ``channels`` table (per-channel scheduling state).

:class:`DirectoryColumns`
    Column names for the ``directory`` table (tracked members per channel).

:class:`RSVPsColumns`
    Column names for the ``rsvps`` table (attendance records).

:class:`SentRemindersColumns`
    Column names for the ``sent_reminders`` table (reminder deduplication).

:class:`WorkPairsColumns`
    Column names for the ``work_pairs`` table (partner relationships).
"""

from __future__ import annotations


# --------------------------------------------
# Tables
# --------------------------------------------
class Tables:
    """
    Table name constants.

    .. rubric:: Attributes

    CHANNEL : :class:`str`
        Table storing per-channel configuration and scheduling state.
    DIRECTORY : :class:`str`
        Table tracking active directory members per channel.
    RSVPS : :class:`str`
        Table storing RSVP entries keyed by workday.
    SENT_REMINDERS : :class:`str`
        Table used to deduplicate reminder messages.
    WORK_PAIRS : :class:`str`
        Table storing partner relationships for a workday.
    """

    CHANNEL = "channels"
    DIRECTORY = "directory"
    RSVPS = "rsvps"
    SENT_REMINDERS = "sent_reminders"
    WORK_PAIRS = "work_pairs"


# --------------------------------------------
# Columns (grouped by table)
# --------------------------------------------

class ChannelColumns:
    """
    Column names for the ``channels`` table.

    .. rubric:: Attributes

    GUILD_ID : :class:`str`
        Discord guild ID.
    CHANNEL_ID : :class:`str`
        Discord channel ID.
    REMINDER_OFFSETS : :class:`str`
        Comma-separated reminder offsets (minutes).
    WORKDAY_DATE : :class:`str`
        Current workday date (ISO string).
    DEADLINE_TS : :class:`str`
        RSVP deadline timestamp (UTC epoch seconds).
    RSVP_MESSAGE_ID : :class:`str`
        ID of the persistent RSVP panel message.
    ROLLOVER_WEEKDAY : :class:`str`
        Weekly rollover weekday (0=Mon..6=Sun).
    ROLLOVER_TIME : :class:`str`
        Rollover time in local ``HH:MM`` format.
    """

    GUILD_ID = "guild_id"
    CHANNEL_ID = "channel_id"
    REMINDER_OFFSETS = "reminder_offsets"
    WORKDAY_DATE = "workday_date"
    DEADLINE_TS = "deadline_ts"
    RSVP_MESSAGE_ID = "rsvp_message_id"
    ROLLOVER_WEEKDAY = "rollover_weekday"
    ROLLOVER_TIME = "rollover_time"


class DirectoryColumns:
    """
    Column names for the ``directory`` table.

    .. rubric:: Attributes

    GUILD_ID : :class:`str`
        Discord guild ID.
    CHANNEL_ID : :class:`str`
        Discord channel ID.
    USER_ID : :class:`str`
        Discord user ID.
    ACTIVE : :class:`str`
        Boolean-like flag indicating active membership.
    ADDED_BY : :class:`str`
        User ID of the admin who added the member.
    ADDED_AT_TS : :class:`str`
        Timestamp when the member was added.
    """

    GUILD_ID = "guild_id"
    CHANNEL_ID = "channel_id"
    USER_ID = "user_id"
    ACTIVE = "active"
    ADDED_BY = "added_by"
    ADDED_AT_TS = "added_at_ts"


class RSVPsColumns:
    """
    Column names for the ``rsvps`` table.

    .. rubric:: Attributes

    GUILD_ID : :class:`str`
        Discord guild ID.
    CHANNEL_ID : :class:`str`
        Discord channel ID.
    WORKDAY_DATE : :class:`str`
        Workday date associated with the RSVP.
    USER_ID : :class:`str`
        Discord user ID.
    STATUS : :class:`str`
        RSVP status (e.g. ``yes``, ``remote``, ``maybe``, ``no``).
    NOTE : :class:`str`
        Optional note attached to the RSVP.
    UPDATED_AT_TS : :class:`str`
        Timestamp of the last RSVP update.
    """

    GUILD_ID = "guild_id"
    CHANNEL_ID = "channel_id"
    WORKDAY_DATE = "workday_date"
    USER_ID = "user_id"
    STATUS = "status"
    NOTE = "note"
    UPDATED_AT_TS = "updated_at_ts"


class SentRemindersColumns:
    """
    Column names for the ``sent_reminders`` table.

    .. rubric:: Attributes

    GUILD_ID : :class:`str`
        Discord guild ID.
    CHANNEL_ID : :class:`str`
        Discord channel ID.
    WORKDAY_DATE : :class:`str`
        Workday date associated with the reminder.
    OFFSET_MIN : :class:`str`
        Reminder offset in minutes before the deadline.
    SENT_AT_TS : :class:`str`
        Timestamp when the reminder was sent.
    """

    GUILD_ID = "guild_id"
    CHANNEL_ID = "channel_id"
    WORKDAY_DATE = "workday_date"
    OFFSET_MIN = "offset_min"
    SENT_AT_TS = "sent_at_ts"


class WorkPairsColumns:
    """
    Column names for the ``work_pairs`` table.

    .. rubric:: Attributes

    GUILD_ID : :class:`str`
        Discord guild ID.
    CHANNEL_ID : :class:`str`
        Discord channel ID.
    WORKDAY_DATE : :class:`str`
        Workday date associated with the partnership.
    USER_ID : :class:`str`
        User who declared the partnership.
    PARTNER_ID : :class:`str`
        Partner user ID.
    CREATED_AT_TS : :class:`str`
        Timestamp when the partnership was recorded.
    """

    GUILD_ID = "guild_id"
    CHANNEL_ID = "channel_id"
    WORKDAY_DATE = "workday_date"
    USER_ID = "user_id"
    PARTNER_ID = "partner_id"
    CREATED_AT_TS = "created_at_ts"
