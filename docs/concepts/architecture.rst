.. docs/concepts/architecture.rst

Architecture
============

This bot is organized around a small number of layers with clear responsibilities:

- **Commands** (Discord slash commands)
- **Services** (application logic)
- **Database** (persistent state in SQLite)
- **UI** (panel embed + interactive views)
- **Scheduler** (background loops for reminders and rollover)

The goal is to keep Discord event handling thin and push most logic into services.

High-level data flow
--------------------

A typical interaction follows this pattern:

1. A slash command or panel interaction is triggered
2. A thin command handler builds a :class:`~rsvp_bot.commands.ctx.CommandCtx`
3. A service updates state in the database
4. The panel is refreshed to reflect the new state

In short:

``Discord interaction → service → DB → panel refresh``

Command registration model
--------------------------

Unlike traditional Discord bots where commands are defined globally,
this project uses an explicit registration model.

Each command module exposes a function like:

- :func:`rsvp_bot.commands.admin.register_admin_commands`
- :func:`rsvp_bot.commands.directory.register_directory_commands`

These functions attach commands to the Discord command tree at runtime.

Benefits:

- Debug commands can be enabled only in development mode
- Clear separation between command definition and bot wiring
- Better testability and modularity

Package map
-----------

**Commands**
  ``src/rsvp_bot/commands/`` contains command registration modules.

  Each module exposes a small registration function (e.g.
  :func:`rsvp_bot.commands.admin.register_admin_commands`) that
  attaches slash commands to the Discord command tree.

  This allows the bot to enable or disable command groups at startup
  (for example, enabling debug commands only in development mode).

  Commands should:
  - validate inputs and permissions
  - build a :class:`~rsvp_bot.commands.ctx.CommandCtx`
  - delegate real work to services and DB methods

**Services**
  ``src/rsvp_bot/services/`` contains the core application behavior:

  - ``PanelService`` manages the RSVP panel message (create/refresh/cleanup)
  - ``RSVPService`` handles RSVP updates from interactions (status, notes, partners)
  - ``SchedulerService`` runs periodic loops (reminders + weekly rollover)

**Database**
  ``src/rsvp_bot/db/`` provides async access to SQLite using ``aiosqlite``.
  The schema is defined in:

  - ``db/schema.py`` (table/column constants)
  - ``db/migrations.py`` (SQL schema creation)

  The database is the source of truth for:
  - channel scheduling state (workday, deadline, rollover, panel message id)
  - directory membership
  - RSVPs
  - sent reminder history
  - work partner links

**UI (Embeds + Views)**
  User-facing UI is built from:
  - embeds (render state into a readable message)
  - Discord UI views (buttons, modals, selects)

  The panel is a message containing:
  - an embed summarizing RSVPs and "Missing" users
  - a persistent view with RSVP buttons

  Views use stable ``custom_id`` values so button clicks can be routed across restarts.

**Bot initialization**
  ``src/rsvp_bot/bot.py`` wires everything together and provides the CLI entrypoint
  (:func:`~rsvp_bot.bot.main`). The packaged console script is ``rsvp-bot``.
  
Key concepts and where they live
--------------------------------

**Scheduling lifecycle**
  - Concepts: :doc:`scheduling`
  - Runtime state: ``channels`` table
  - Automation: ``SchedulerService``

**Directory membership**
  - Concepts: :doc:`directory-system`
  - Runtime state: ``directory`` table
  - Used by: reminders and panel summary ("Missing")

**Panels**
  - Concepts: :doc:`panels`
  - Runtime state: ``channels.rsvp_message_id``
  - Managed by: ``PanelService`` and ``RSVPView``

Operational modes
-----------------

The bot supports two syncing modes:

- **DEV mode** (``DEV_GUILD_ID`` set): fast guild-only command sync
- **PROD mode** (no ``DEV_GUILD_ID``): global command sync

See :doc:`../user-guide/dev-vs-prod` for details.

Design principles
-----------------

- Keep Discord handlers thin; put behavior in services.
- Persist all important state to SQLite; the panel is a view of DB state.
- Prefer per-channel configuration (each channel can run its own workday cycle).
- Use persistent views with stable custom IDs so panels survive restarts.
