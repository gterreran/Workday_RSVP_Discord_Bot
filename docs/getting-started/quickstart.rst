.. docs/getting-started/quickstart.rst

==========
Quickstart
==========

This page explains how the Workday RSVP Bot works at a high level and walks
through the first real workflow: creating a panel and running a full cycle.

If you have not installed the bot yet, see :doc:`installation`.

Core concepts
-------------

A few concepts define how the bot behaves:

**Workday**
  The target day of the week when the event happens (e.g. Saturday).

**Deadline**
  The cutoff time for submitting RSVPs (often the evening before the workday).

**Reminders**
  Automated pings sent before the deadline (e.g. 48h, 24h, 6h, 1h).
  Reminders only mention people in the directory who have **not RSVPed yet**.

**Rollover**
  A weekly reset where the bot advances to the next workday cycle.

These defaults are defined in ``src/rsvp_bot/config.py`` and can be customized.
See :doc:`../concepts/scheduling` for details.

First-time admin workflow
-------------------------

Once the bot is running and slash commands are synced, the initial setup usually
takes less than a minute.

Step 0 — Start the bot
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   rsvp-bot

Step 1 — Create the RSVP panel
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Run:

.. code-block:: text

   /setup

This posts the persistent RSVP panel in the current channel.

The panel remains interactive across restarts and becomes the central place
where users submit their attendance.

Step 2 — Add people to the directory
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Populate the directory with the people who should receive reminders
and appear in summaries:

.. code-block:: text

   /directory_add

Only users in the directory are considered "expected" to RSVP and will be
mentioned by reminder pings.

You can run this multiple times as new members join.

See :doc:`../concepts/directory-system` for details.

What happens automatically
--------------------------

After the initial setup, most behavior is automatic.

Reminders
^^^^^^^^^

The bot sends scheduled reminders leading up to the deadline.

Each reminder mentions directory members who have not RSVPed yet,
reducing unnecessary pings.

See :doc:`../concepts/scheduling`.

Weekly rollover
^^^^^^^^^^^^^^^

At a configured day and time, the bot rolls over to the next cycle.

During rollover, the bot:

- advances the internal workday window
- prepares the next workday automatically
- refreshes the RSVP panel while keeping it persistent

This allows the bot to run indefinitely without manual resets.

Where to customize behavior
---------------------------

Most deployments only need small tweaks:

- Workday weekday
- RSVP deadline timing
- Reminder offsets
- Rollover schedule

All of these live in ``src/rsvp_bot/config.py``.

See :doc:`../concepts/scheduling` and :doc:`../user-guide/commands` for details.

Next steps
----------

- Learn the command set: :doc:`../user-guide/commands`
- Deep dive into scheduling: :doc:`../concepts/scheduling`
