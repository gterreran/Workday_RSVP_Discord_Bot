Commands
========

This page documents all available slash commands and how to use them in practice.

Most commands are **admin-only** and must be run in a guild text channel.
All replies are ephemeral unless otherwise noted.

If commands do not appear, make sure the bot is synced correctly.
See :doc:`dev-vs-prod`.

Command overview
----------------

Commands fall into four categories:

- Setup and lifecycle
- Scheduling controls (debug/admin)
- Directory management
- Reports and inspection

Quick reference
---------------

Core commands
^^^^^^^^^^^^^

- :ref:`cmd-setup` — Create or reset the RSVP panel
- :ref:`cmd-attendance-reset` — Clear all RSVPs for the upcoming workday
- :ref:`cmd-summary` — Full RSVP report (notes + partners)

Directory commands
^^^^^^^^^^^^^^^^^^

- :ref:`cmd-directory-add` — Add a user to the RSVP directory
- :ref:`cmd-directory-remove` — Remove a user from the directory
- :ref:`cmd-directory-list` — Show current directory members

Scheduling controls
^^^^^^^^^^^^^^^^^^^

- :ref:`cmd-deadline-set` — Set a specific RSVP deadline
- :ref:`cmd-workday-set` — Manually set the workday date
- :ref:`cmd-workday-reset` — Return to automatic scheduling
- :ref:`cmd-rollover-set` — Configure weekly rollover timing
- :ref:`cmd-rollover-show` — Show current rollover schedule
- :ref:`cmd-reminders-set` — Configure reminder offsets
- :ref:`cmd-reminders-show` — Show reminder offsets

Help
^^^^

- :ref:`cmd-rsvp-commands` — Show a live list of registered commands

How commands are structured internally
--------------------------------------

Each command group lives in its own module under
``src/rsvp_bot/commands/``.

Commands are registered at startup via small registration functions
(e.g. :func:`rsvp_bot.commands.admin.register_admin_commands`).
This allows the bot to enable or disable groups of commands
depending on runtime flags (such as debug mode).

This design keeps command handlers thin and makes the command system
easy to extend.

Setup and lifecycle
-------------------

.. _cmd-setup:

/setup
^^^^^^

Create or reset the RSVP panel in the current channel.

**API:** :mod:`rsvp_bot.commands.admin`  
**Panel logic:** :class:`rsvp_bot.services.panel_service.PanelService`

This is the main entry point for new channels.

What it does:

- Creates the persistent RSVP panel (if missing)
- Computes the next workday automatically
- Calculates the default deadline
- Initializes reminder offsets
- Registers the channel in the database

If the panel already exists, it is refreshed and scheduling is reset.

Typical usage:

1. Invite the bot
2. Go to the desired channel
3. Run ``/setup``

You only need to run this once per channel unless resetting the system.

---

.. _cmd-attendance-reset:

/attendance_reset
^^^^^^^^^^^^^^^^^

Clear all attendance data for the upcoming workday.

**API:** :mod:`rsvp_bot.commands.admin`  
**Panel logic:** :meth:`rsvp_bot.services.panel_service.PanelService.reset_attendance`

This removes:

- RSVPs
- Partner links
- Sent reminder history

The panel is automatically refreshed.

Use cases:

- Mistakes in RSVPs
- Restarting a week manually
- Cleaning state during testing

Scheduling controls
-------------------

These commands override automatic scheduling.
See :doc:`../concepts/scheduling` for the underlying model.

.. _cmd-deadline-set:

/deadline_set
^^^^^^^^^^^^^

Set an explicit RSVP deadline.

**API:** :mod:`rsvp_bot.commands.debug`

Parameters:

- ``date`` — YYYY-MM-DD
- ``time`` — HH:MM (24-hour)

Example:

.. code-block:: text

   /deadline_set date:2026-02-10 time:18:30

Notes:

- Must not be in the past
- Must not be after the workday date
- Uses the bot's configured timezone

Changing the deadline automatically clears reminder history.

---

.. _cmd-workday-set:

/workday_set
^^^^^^^^^^^^

Manually override the workday date.

**API:** :mod:`rsvp_bot.commands.debug`

Example:

.. code-block:: text

   /workday_set date:2026-03-01

This disables automatic next-workday calculation.

Use this if:

- Skipping a week
- Running special events
- Testing

The panel updates immediately.

---

.. _cmd-workday-reset:

/workday_reset
^^^^^^^^^^^^^^

Return to automatic scheduling.

**API:** :mod:`rsvp_bot.commands.debug`

After this, the bot resumes calculating the next workday automatically.

---

.. _cmd-rollover-set:

/rollover_set
^^^^^^^^^^^^^

Configure when the bot advances to the next workday cycle.

**API:** :mod:`rsvp_bot.commands.debug`

Parameters:

- ``weekday`` — 0 = Monday, 6 = Sunday
- ``time_hhmm`` — Local time in HH:MM (24-hour)

Example:

.. code-block:: text

   /rollover_set weekday:5 time_hhmm:09:00

This controls when:

- Workday date advances
- Old reminders stop
- New cycle begins

---

.. _cmd-rollover-show:

/rollover_show
^^^^^^^^^^^^^^

Display the current rollover schedule for the channel.

**API:** :mod:`rsvp_bot.commands.debug`

---

.. _cmd-reminders-set:

/reminders_set
^^^^^^^^^^^^^^

Configure when reminders are sent before the deadline.

**API:** :mod:`rsvp_bot.commands.debug`

Parameters:

- ``values`` — comma-separated numbers
- ``unit`` — minutes, hours, or days

Examples:

.. code-block:: text

   /reminders_set values:48,24,6,1 unit:hours
   /reminders_set values:2,1 unit:days

Internally, reminders are stored in minutes and sorted automatically.

---

.. _cmd-reminders-show:

/reminders_show
^^^^^^^^^^^^^^^

Display reminder offsets in minutes before the deadline.

**API:** :mod:`rsvp_bot.commands.debug`

Directory management
--------------------

The directory defines who is tracked for attendance and reminders.
See :doc:`../concepts/directory-system`.

.. _cmd-directory-add:

/directory_add
^^^^^^^^^^^^^^

Add a user to the channel directory.

**API:** :mod:`rsvp_bot.commands.directory`

Example:

.. code-block:: text

   /directory_add user:@alice

Effects:

- User appears in panel summaries
- User receives reminders
- Missing users are tracked correctly

If a panel exists, it refreshes immediately.

---

.. _cmd-directory-remove:

/directory_remove
^^^^^^^^^^^^^^^^^

Remove a user from the directory.

**API:** :mod:`rsvp_bot.commands.directory`

This does not delete historical RSVPs but removes them from future summaries.

---

.. _cmd-directory-list:

/directory_list
^^^^^^^^^^^^^^^

Show all users currently in the directory.

**API:** :mod:`rsvp_bot.commands.directory`

Useful for:

- Verifying membership
- Debugging reminder coverage

Reports
-------

.. _cmd-summary:

/summary
^^^^^^^^

Generate a full attendance report for the upcoming workday.

**API:** :mod:`rsvp_bot.commands.reports`

Includes:

- RSVP status
- Notes
- Work partners
- Missing users

Output is split into multiple messages if needed.

This is useful for:

- Planning logistics
- Copying into external tools
- Weekly summaries

Help and inspection
-------------------

.. _cmd-rsvp-commands:

/rsvp_commands
^^^^^^^^^^^^^^

Show a dynamically generated list of commands available in the current guild.

**API:** :mod:`rsvp_bot.commands.admin`

This is helpful if:

- Sync mode is unclear
- Commands are missing
- Debugging permissions

Permissions
-----------

Most commands require:

- Admin permissions in the guild
- Execution inside a guild text channel

If a command fails silently, check:

- Bot permissions
- Channel permissions
- Slash command sync mode

Tips
----

- Run ``/setup`` once per channel.
- Treat the panel as the source of truth — commands mutate the panel state.
- Use ``/summary`` instead of screenshots when sharing attendance.
- Prefer automatic scheduling unless you have a strong reason to override it.
