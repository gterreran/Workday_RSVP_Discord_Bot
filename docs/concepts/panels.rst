.. docs/concepts/panels.rst

Panels
======

The RSVP **panel** is the central user interface of the bot: a single message in a
channel that shows the current workday, the RSVP summary, and interactive buttons
for members to submit or update their RSVP.

A panel is designed to be:

- **persistent** (continues to work across bot restarts)
- **self-updating** (refreshes its embed as RSVPs change)
- **channel-scoped** (each configured channel has its own panel and cycle)

Panel anatomy
-------------

A panel message consists of:

**An embed**
  Displays the current workday and an RSVP summary broken down by status.

**An interactive view**
  A set of buttons that users click to submit or update their RSVP.

The embed and the view are updated together when the panel is refreshed.

Panel embed
-----------

The embed is built in ``src/rsvp_bot/embeds.py`` via:

- ``build_embed(workday_date, deadline_ts, summary)``

It renders:

- title: ``Workday RSVP — YYYY-MM-DD``
- deadline: displayed using Discord timestamp formatting
- fields for each RSVP status and a "Missing" category

The embed uses mention formatting (``<@user_id>``) so that names render as clickable
user references in Discord.

RSVP statuses are represented using a simple status vocabulary:

- ``yes`` (✅ Attending)
- ``remote`` (🎥 Attending (Remote))
- ``maybe`` (❔ Maybe)
- ``no`` (❌ Not attending)

The summary also includes:

- **Missing**: directory members who have not RSVPed yet for the current workday

This "Missing" category is the main bridge between panels and the directory system
(see :doc:`directory-system`).

Interactive view (buttons + flows)
----------------------------------

The panel’s interactive controls are implemented as Discord UI views in
``src/rsvp_bot/views.py``:

- ``RSVPView`` is attached directly to the panel message
- some actions route users into additional UI:
  - ``RSVPPlanModal`` (optional plan/note entry)
  - ``PartnerSelectView`` (optional partner selection)

Persistent buttons
^^^^^^^^^^^^^^^^^^

The RSVP panel view is created with:

- ``timeout=None``

This makes it a **persistent view**, meaning button interactions can still be routed
after the bot restarts *as long as the bot registers the view when it starts*.

The buttons use stable ``custom_id`` values such as:

- ``rsvp_yes``
- ``rsvp_remote``
- ``rsvp_maybe``
- ``rsvp_no``

Stable custom IDs are important: they are how Discord re-identifies which button was
clicked when the original view instance is no longer in memory.

How the bot ensures persistence
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

On startup, the bot registers the persistent RSVP view in ``RSVPBot.setup_hook``:

- ``bot.add_view(RSVPView(...))``

This step is essential: it tells Discord.py how to route interactions for existing
panel messages after a restart.

Panel creation and refresh
--------------------------

Panel lifecycle is managed by ``PanelService`` in:

- ``src/rsvp_bot/services/panel_service.py``

There are three core operations:

Create a new panel
^^^^^^^^^^^^^^^^^^

``PanelService.create_new_panel(...)``:

1. Reads the active directory for the channel
2. Clears existing RSVPs for the current workday (fresh start)
3. Builds an empty summary and embed
4. Sends a new message to the channel with:
   - the embed
   - a new ``RSVPView`` instance
5. Attempts to pin the message
6. Returns the message ID

Pinning is best-effort: if the bot lacks permission to pin messages, it continues
without error.

Refresh an existing panel
^^^^^^^^^^^^^^^^^^^^^^^^^

``PanelService.refresh_panel(...)`` updates the existing panel in-place:

1. Reads directory membership (expected users)
2. Reads RSVPs for the current workday
3. Reads the current deadline timestamp from the database
4. Builds a new summary and embed
5. Fetches the existing message using ``rsvp_message_id``
6. Edits the message with the new embed and a new ``RSVPView`` instance

If the original message cannot be found (e.g., deleted manually), refresh exits
silently.

Clean up an old panel
^^^^^^^^^^^^^^^^^^^^^

``PanelService.cleanup_panel(...)`` is used during rollover and maintenance:

- unpins the message if pinned
- optionally deletes the message

By default, rollover uses cleanup to unpin without deleting (so the history remains),
but deployments can choose to delete old panels if desired.

How panels connect to the database
----------------------------------

The panel message ID is stored per channel in the ``channels`` table as:

- ``rsvp_message_id``

This allows the bot to find and edit the panel message later.

The panel itself is not the source of truth: the current state is stored in the DB:

- RSVPs: ``rsvps`` table (keyed by guild/channel/workday/user)
- Directory membership: ``directory`` table (keyed by guild/channel/user)
- Scheduling info: ``channels.workday_date`` and ``channels.deadline_ts``

Panels render the DB state into a user-facing summary.

Panel updates triggered by commands
-----------------------------------

Some admin commands update directory membership (``/directory_add`` / ``/directory_remove``).
When that happens, the bot refreshes the panel so the "Missing" list and any directory-derived
UI stays accurate.

The command implementation uses the existence of a workday date as a proxy for whether
the panel has been initialized:

- if ``workday_date`` exists, refresh the panel
- if not, skip refresh

Panel updates triggered by RSVP interactions
--------------------------------------------

Button callbacks call into RSVP service handlers (not shown here), which are expected to:

- store RSVP changes in the DB (``rsvps.set_rsvp(...)``)
- optionally store partner selections (``work_pairs``)
- trigger a panel refresh so the embed reflects the new state

This is the standard pattern:

1. interaction occurs
2. state changes in DB
3. panel is refreshed to render new state

See also
--------

- :doc:`directory-system` for how the directory defines "Missing" users and reminder targeting
- :doc:`scheduling` for reminder timing, deadlines, and rollover behavior
- :doc:`../user-guide/commands` for user-facing commands that create/refresh panels and manage the directory
