.. docs/user-guide/dev-vs-prod.rst

Development vs Production
=========================

This page explains the difference between **development mode** and **production mode**
and how it affects command availability, syncing, and behavior.

If commands appear to be missing or behaving differently between environments,
this page is the first place to check.

Overview
--------

The bot supports two runtime modes:

- Development mode (``debug=True``)
- Production mode (``debug=False``)

The mode is typically controlled at startup via configuration or environment variables.

Why this matters:

- Slash command visibility
- Command sync behavior
- Availability of debug tools
- Safety guarantees

Command availability
--------------------

Production mode
^^^^^^^^^^^^^^^

In production:

- Only stable commands are registered
- Debug commands are **disabled**
- Commands may be registered globally or per-guild depending on sync strategy

This is the safe mode for real communities.

---

Development mode
^^^^^^^^^^^^^^^^

When ``bot.debug = True``:

- Debug commands are registered
- Scheduling can be overridden live
- Faster command iteration is possible

This mode is intended for:

- Local development
- Testing scheduling edge cases
- Rapid iteration

Never run debug mode in a public production server.

Debug-only commands
-------------------

These commands exist **only in debug mode**:

- ``/deadline_set``
- ``/workday_set``
- ``/workday_reset``
- ``/rollover_set``
- ``/rollover_show``
- ``/reminders_set``
- ``/reminders_show``

These commands allow live mutation of scheduling parameters.

In production, scheduling should normally be driven by:

- Config defaults
- Automatic rollover

Why debug commands are gated
----------------------------

Allowing runtime scheduling changes in production can lead to:

- Inconsistent reminder timing
- Unexpected rollovers
- Confusion for users
- Hard-to-reproduce bugs

For this reason, the bot uses a **hard separation** between stable and experimental controls.

Slash command syncing
---------------------

One of the most common sources of confusion is slash command syncing.

There are two ways Discord commands can be registered:

- Global commands
- Guild-scoped commands

Global commands
^^^^^^^^^^^^^^^

- Available in all guilds
- Can take up to **1 hour** to propagate
- Suitable for stable production deployments

Guild commands
^^^^^^^^^^^^^^

- Registered for a specific server
- Propagate almost instantly
- Ideal for development and testing

Typical workflow:

- Development → guild-scoped sync
- Production → global sync

If commands are missing, check which sync mode is being used.

Why commands may appear "missing"
---------------------------------

Common causes:

1. Debug mode disabled

   Debug commands are intentionally hidden in production.

2. Global sync delay

   Global commands may take time to appear.

3. Bot permissions

   The bot needs:

   - applications.commands scope
   - Proper guild permissions

4. Guild mismatch

   Guild-scoped commands only exist in the synced server.

How to tell which mode you're in
--------------------------------

Indicators you are in development mode:

- Debug commands are visible
- Scheduling can be edited live
- You started the bot with a debug flag

Indicators you are in production:

- Only core commands are available
- Scheduling is stable
- No runtime overrides

Safe deployment strategy
------------------------

Recommended workflow:

1. Develop locally with debug enabled

   - Use guild-scoped commands
   - Test scheduling changes
   - Validate reminders

2. Deploy staging bot (optional)

   - Separate bot token
   - Small test guild
   - Production-like environment

3. Deploy production bot

   - Disable debug mode
   - Use global command sync
   - Freeze scheduling behavior

This mirrors best practices used in larger Discord bots.

Environment separation
----------------------

For clean deployments, consider separating:

- Bot tokens
- Databases
- Guild IDs

Example layout:

- Dev bot → local SQLite
- Staging bot → cloud SQLite/Postgres
- Production bot → production database

This prevents accidental data pollution.

Database considerations
-----------------------

Debug mode can mutate scheduling state frequently.

To avoid corrupting production data:

- Never point dev bot at production DB
- Use separate SQLite files
- Consider timestamped dev databases

Command evolution
-----------------

As the bot evolves:

- New commands should first land in debug mode
- Once stable, promote them to production
- Remove obsolete debug commands

This keeps the production surface minimal and safe.

Troubleshooting checklist
-------------------------

Commands missing?

- Check if debug mode is enabled
- Verify sync strategy (guild vs global)
- Re-sync commands
- Confirm bot permissions

Debug commands visible in prod?

- Ensure ``bot.debug`` is False
- Restart bot with production config

Commands not updating?

- Global sync delay
- Discord caching
- Try re-inviting bot

Final note
----------

If in doubt:

- Use development mode for experimentation
- Use production mode for stability

This separation keeps scheduling predictable and avoids surprising users.
