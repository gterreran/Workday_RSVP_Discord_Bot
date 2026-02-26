.. docs/concepts/directory-system.rst

Directory System
================

The **directory** is the bot's notion of who is "in scope" for a given channel's
workday cycle.

It serves two main purposes:

- Define who is **expected** to RSVP (and therefore who can be pinged by reminders)
- Provide a known set of users for workflows that involve partner selection and summaries

The directory is **per channel** (not global to the entire guild). This lets different
channels represent different groups, even within the same server.

What the directory represents
-----------------------------

In this bot, directory membership answers a very specific question:

  "Who should be considered part of the RSVP group for this channel?"

It does **not** mean:

- anyone who can see the channel
- anyone who happens to click the panel
- the server's entire membership list

Instead, it is an explicit list curated by admins.

This design keeps the bot predictable and prevents accidental mass pings.

How it is represented (database)
--------------------------------

Directory entries are stored in SQLite in the ``directory`` table.

The primary key is:

- ``(guild_id, channel_id, user_id)``

Key fields (see ``src/rsvp_bot/db/schema.py`` and ``src/rsvp_bot/db/migrations.py``):

- ``guild_id``: Discord guild ID
- ``channel_id``: Discord channel ID (directory is per-channel)
- ``user_id``: Discord user ID
- ``active``: integer flag (1 = active, 0 = inactive)
- ``added_by``: user ID of the admin who added the entry
- ``added_at_ts``: Unix timestamp when it was added

Inactive entries are retained rather than deleted, which makes "remove" reversible
and keeps a record of membership history.

How it is represented (Python)
------------------------------

The database access layer exposes the directory as a small set of operations
(``src/rsvp_bot/db/directory.py``):

**Add**
  ``directory_add(guild_id, channel_id, user_id, added_by, added_at_ts)``

  This uses an ``INSERT ... ON CONFLICT ... DO UPDATE`` strategy:
  - if a user does not exist, a row is created with ``active=1``
  - if a user already exists, they are re-activated (``active=1``)

**List active**
  ``directory_list_active(guild_id, channel_id) -> list[int]``

  Returns user IDs for active entries only.

**Remove**
  ``directory_remove(guild_id, channel_id, user_id)``

  This does not delete rows; it sets ``active=0``.

Admin-facing operations (commands)
----------------------------------

Admins manage the directory using slash commands (see ``src/rsvp_bot/commands/directory.py``):

- ``/directory_add`` — add a user to this channel's directory
- ``/directory_remove`` — deactivate a user in this channel's directory
- ``/directory_list`` — view the current directory

The command implementations intentionally scope membership to the channel where
the command is executed (using ``channel_id`` from the interaction context).

Relationship to the RSVP lifecycle
----------------------------------

Directory membership influences multiple parts of the bot's lifecycle.

Directory defines "expected RSVPs"
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The scheduler uses the directory to determine who is expected to RSVP in a channel:

- directory members are the "expected" set
- reminder pings target only directory members who have not RSVPed for the current workday

This is the mechanism that prevents annoying reminders for people who already RSVPed
and prevents mass pings to non-participants.

Directory and reminders
^^^^^^^^^^^^^^^^^^^^^^^

The reminder loop runs on a schedule (see :doc:`scheduling`). When a reminder triggers,
the bot computes:

- ``expected`` = active directory user IDs for the channel
- ``rsvped`` = user IDs with an RSVP row for the current workday
- ``missing`` = ``expected - rsvped``

Only the ``missing`` set is mentioned by reminders.

If the directory is empty, the bot should avoid pinging anyone (and typically should
avoid sending reminders at all for that channel, since there is no defined group).

Directory and panel refresh
^^^^^^^^^^^^^^^^^^^^^^^^^^^

After adding or removing a user, the bot refreshes the RSVP panel (if a panel exists
for the channel). In ``/directory_add`` and ``/directory_remove``, the code uses the
existence of ``workday_date`` as a proxy for panel setup, and calls:

- ``panel.refresh_panel(...)``

Conceptually, this keeps the panel UI consistent with the current directory membership
(e.g., directory count displays, partner selection options, or summary sections if present).

Directory and partner selection (work pairs)
--------------------------------------------

In addition to RSVP status, this bot stores "work partner" selections for a given workday.

Work pairs are stored in the ``work_pairs`` table and represent a directed relationship:

- ``user_id`` = the user who submitted the plan
- ``partner_id`` = a user they plan to work with

This allows the bot to answer questions such as:

- "Who depends on Alice as a partner this workday?"

Key operations in ``src/rsvp_bot/db/pairs.py`` include:

**Replace a user's partner list**
  ``replace_work_partners(guild_id, channel_id, workday_date, user_id, partner_ids, created_at_ts)``

  This replaces the set of partners for that user and workday, ensuring:
  - no duplicates
  - no self-pairing
  - stable ordering

**Reverse lookup**
  ``get_dependent_users(..., partner_id) -> list[int]``

  Returns users who listed ``partner_id`` as a partner.

**Full mapping**
  ``list_work_partners_map(...) -> dict[user_id, list[partner_id]]``

How directory membership interacts with pairs
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The directory acts as the "universe" of users that partner selection should draw from.

Even if a user is technically mentionable in Discord, partner flows should generally
restrict to directory members to:

- avoid surprises (picking a random server member)
- keep the workflow consistent (partners are part of the RSVP group)

Operational notes
-----------------

- The directory is per channel. Adding a user in one channel does not add them elsewhere.
- Removing a user deactivates them (``active=0``) rather than deleting their row.
- Directory membership is a control surface for notifications:
  it determines who is considered "expected" to RSVP and who can be pinged by reminders.

See also
--------

- :doc:`scheduling` for how reminders and rollover work
- :doc:`panels` for how the RSVP panel and interactions operate
- :doc:`../user-guide/commands` for command usage and admin workflows
