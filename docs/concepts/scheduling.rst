.. docs/concepts/scheduling.rst

Scheduling Concepts
===================

This bot is built around a weekly lifecycle. Each configured channel (where the
RSVP panel lives) has a "current workday" and associated scheduling settings.

This page explains the four core scheduling concepts:

- workday
- deadline
- reminder schedule
- rollover

It also explains where these values are stored (configuration defaults vs database),
and how the scheduler uses them at runtime.

Where scheduling state lives
----------------------------

  Default values live in ``src/rsvp_bot/config.py``:

  - ``DEFAULT_WORKDAY_WEEKDAY``
  - ``DEFAULT_WORKDAY_WEEKDAY_DEADLINE``
  - ``DEFAULT_OFFSETS_MIN``
  - ``DEFAULT_ROLLOVER_WEEKDAY``
  - ``DEFAULT_ROLLOVER_TIME``

  These defaults are intended as "sensible starting values" for a typical deployment.

  They do not represent specific dates, but rather rules for how to compute the current schedule
  based on the current date. Once the bot is initialized in a channel, the actual schedule
  is stored in the database and updated by rollover. In the database schema, most scheduling
  fields are stored on the ``channels`` table (see ``src/rsvp_bot/db/schema.py``
  and ``src/rsvp_bot/db/migrations.py``).  

  Relevant columns in the ``channels`` table include:

  - ``workday_date`` (``YYYY-MM-DD``)
  - ``deadline_ts`` (UTC timestamp)
  - ``reminder_offsets`` (comma-separated minutes)
  - ``rollover_weekday`` (0=Mon .. 6=Sun)
  - ``rollover_time`` (``HH:MM`` in local time)

In other words:

- defaults define the initial behavior
- the database stores the current schedule for each configured channel
- rollover updates the database so the bot can run indefinitely

Workday
-------

What it represents
^^^^^^^^^^^^^^^^^^

A **workday** is the target date for the current RSVP cycle. For example, if your
community meets on Saturday, the workday is the next Saturday.

The bot stores the workday as a *date string*:

- ``workday_date``: ``YYYY-MM-DD``

How it is represented in code
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- Default weekday: ``DEFAULT_WORKDAY_WEEKDAY`` in ``config.py`` (0=Mon .. 6=Sun)

When rollover runs, it computes the next workday date using:

- ``next_workday(...)`` in ``src/rsvp_bot/utils.py`` (used by ``SchedulerService``)

Where it is stored
^^^^^^^^^^^^^^^^^^

- Database: ``channels.workday_date`` (text, ``YYYY-MM-DD``)

How the bot uses it
^^^^^^^^^^^^^^^^^^^

The workday is not used to compute any deadlines or reminders directly.
However, it is used for:

- displaying the upcoming workday in the RSVP panel and reminders
- associating RSVPs with a specific cycle (see ``rsvps.workday_date``)
- associating reminder history with a specific cycle (see ``sent_reminders.workday_date``)
- associating partner pairs with a cycle (see ``work_pairs.workday_date``)

Deadline
--------

What it represents
^^^^^^^^^^^^^^^^^^

A **deadline** is the cutoff for submitting RSVPs for the current workday.
It serves as the anchor point for the reminders schedule.

In the database, the deadline is stored as a **UTC timestamp**:

- ``deadline_ts``: integer UTC epoch seconds

Using UTC internally prevents timezone confusion and makes comparisons trivial.
The bot displays this in Discord using Discord's timestamp formatting.

How it is represented in code
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- Default deadline behavior is controlled by:

  - ``DEFAULT_WORKDAY_WEEKDAY_DEADLINE`` in ``config.py``

  This value is an offset in *hours relative to the workday's midnight*.

  Example:
    ``-6`` means "6 hours before the workday midnight", i.e. ``18:00`` on the previous day.

- The scheduler computes deadlines using:

  - ``default_deadline_for(workday_date, tz)`` in ``src/rsvp_bot/utils.py``

- The runtime scheduler reads the per-channel deadline from the DB:

  - ``db.get_deadline(...)`` in ``SchedulerService.reminder_loop``

Where it is stored
^^^^^^^^^^^^^^^^^^

- Database: ``channels.deadline_ts`` (integer UTC timestamp)

How the bot uses it
^^^^^^^^^^^^^^^^^^^

Deadline affects:

- whether reminders can still be sent (scheduler stops after the deadline passes)
- when the cycle effectively "closes" for RSVP collection

Reminder schedule
-----------------

What it represents
^^^^^^^^^^^^^^^^^^

A reminder schedule is a list of offsets relative to the deadline, indicating when
the bot should send reminders.

Example default:

- ``48h, 24h, 6h, 1h``

In code, the default is expressed in minutes as a comma-separated string:

- ``DEFAULT_OFFSETS_MIN = "2880,1440,360,60"``

How it is represented in code
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- Stored per channel in the DB as:

  - ``channels.reminder_offsets`` (text, comma-separated integer minutes)

- Used by the scheduler in:

  - ``SchedulerService.reminder_loop``

The scheduler logic computes, for each offset:

- ``send_at_ts = deadline_ts - offset_min * 60``

It checks a 60-second window to avoid missing the send time:

- send if ``send_at_ts <= now < send_at_ts + 60``

To prevent duplicate reminders for the same offset, the bot tracks sent reminders
in a dedicated table:

- ``sent_reminders`` keyed by ``(guild_id, channel_id, workday_date, offset_min)``

Who gets pinged
^^^^^^^^^^^^^^^

Reminders are posted to the channel, but mentions are targeted:

- Only users in the directory are considered "expected".
- The reminder message mentions only directory members who have **not RSVPed yet**
  for the current workday date.

This behavior reduces noise for people who already responded.

Where it is stored
^^^^^^^^^^^^^^^^^^

- Current schedule (per channel): ``channels.reminder_offsets``
- History / dedupe: ``sent_reminders``

How the bot uses it
^^^^^^^^^^^^^^^^^^^

The reminder schedule drives:

- when reminders are sent
- which offsets are considered "already sent" for a given workday cycle

If you change reminder offsets mid-cycle, some offsets may not match the existing
``sent_reminders`` history for that workday.

Rollover
--------

What it represents
^^^^^^^^^^^^^^^^^^

Rollover is the weekly event that advances the bot to the next workday cycle.

Rollover is defined by:

- a weekday (0=Mon .. 6=Sun)
- a time (``HH:MM``) in the bot's configured timezone

How it is represented in code
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Defaults:

- ``DEFAULT_ROLLOVER_WEEKDAY`` in ``config.py``
- ``DEFAULT_ROLLOVER_TIME`` in ``config.py``

Runtime:

- stored per channel in the DB:
  - ``channels.rollover_weekday``
  - ``channels.rollover_time``

The scheduler loop checks once per minute:

- current local weekday matches rollover weekday
- current local time matches rollover time (minute precision)

To prevent multiple rollovers in the same minute/day (because the loop runs every minute),
the service tracks a local in-memory guard:

- ``weekly_done`` set keyed by ``guild_id:channel_id:date``

What rollover does
^^^^^^^^^^^^^^^^^^

When rollover triggers for a channel, the bot:

1. Computes the next workday date
2. Computes a new deadline timestamp
3. Refreshes the RSVP panel
4. Updates the channel row in the DB with the new cycle values

This is how the bot continues operating week after week without manual resets.

Where it is stored
^^^^^^^^^^^^^^^^^^

- Schedule: ``channels.rollover_weekday``, ``channels.rollover_time``
- Guard (prevent repeats): in memory only (``weekly_done``)

Changing scheduling behavior
----------------------------

Scheduling parameters are designed to be stable during normal operation.

In a typical deployment, scheduling is defined by:

- defaults in ``src/rsvp_bot/config.py``
- per-channel state stored in the database

These values are assumed to remain consistent while the bot is running.
Changing them dynamically can lead to inconsistent state (e.g. mismatched
deadlines, reminder offsets, or rollover boundaries).

Recommended approach
^^^^^^^^^^^^^^^^^^^^

If you need to change the scheduling model (for example, different workday,
deadline rule, or reminder cadence), the recommended workflow is:

1. Stop the bot
2. Edit the relevant defaults in ``config.py``
3. Restart the bot

This ensures that scheduling logic, database state, and the scheduler service
remain coherent.

Debug mode overrides
^^^^^^^^^^^^^^^^^^^^

When the bot is started with the ``--debug`` flag, additional commands may be
available to modify scheduling values at runtime.

These commands are intended for:

- development
- testing new scheduling logic
- validating behavior in staging environments

They are **not recommended for production use**, because runtime changes can
introduce inconsistencies between in-memory scheduler state and persisted data.

See :doc:`../user-guide/dev-vs-prod` and :doc:`../user-guide/commands` for details.

Notes and troubleshooting
-------------------------

- Rollover checks time at **minute precision**. If your bot is down at the scheduled
  rollover minute, rollover will not occur until the next scheduled week.
- Reminders are deduped per offset and per workday. Restarting the bot does not
  cause already-sent reminders to re-send.
- Deadline timestamps are stored in UTC, but displayed in Discord using timestamp
  formatting, so users see it in their own timezone.

