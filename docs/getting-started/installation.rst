.. docs/getting-started/installation.rst

============
Installation
============

This page covers installing and running the bot locally, including the minimal
environment variables required to start it.

Create the Discord application (high level)
===========================================

This project requires a Discord *application* with an associated *bot user*.
Discord’s official documentation is the best reference (`Discord Developer Portal docs <https://discord.com/developers/docs/intro>`_),
but the short version is:

1. Open the Discord Developer Portal.
2. Create a **New Application**.
3. In the application settings, go to **Bot** and click **Add Bot**.
4. Under **Bot**, copy the token and store it in your local ``.env`` file as
   ``DISCORD_TOKEN``.

.. warning::

   Treat the bot token like a password. Do not commit it to git or paste it in logs.
   Use a local ``.env`` file for development, and environment variables/secrets for deployment.

Gateway intents (important)
---------------------------

This bot enables the **Members** intent:

- In the Developer Portal, go to **Bot → Privileged Gateway Intents**
  and enable **Server Members Intent**.

If the Members intent is not enabled, some user- and member-related functionality
may not work as expected.

Invite the bot to your server
-----------------------------

You must invite the bot into a Discord server (guild) before it can operate there.

In the Developer Portal, go to **OAuth2 → URL Generator** and select:

**Scopes**
  - ``bot``
  - ``applications.commands`` (required for slash commands)

**Bot permissions**
  The bot needs a small, practical set of permissions to function correctly. The
  exact set depends on where you use it, but the recommended baseline is:

  - **View Channels**
    Needed to see the channel where the RSVP panel is posted.
  - **Send Messages**
    Needed to post RSVP panels and bot responses.
  - **Embed Links**
    Needed if the bot uses embeds for panels, confirmations, or reports.
  - **Read Message History**
    Recommended if the bot needs to find/refresh an existing panel message.
  - **Add Reactions** (optional)
    Only needed if your bot uses reactions anywhere (some bots do; if you don't, omit it).
  - **Manage Messages** (optional, admin-only deployments)
    Only needed if your bot edits/replaces/pins panel messages or performs cleanup actions.

.. note::

   For typical operation, you usually **do not** need administrator permissions.
   Prefer granting the minimal permissions above in the channel(s) where the bot runs.


The python environment
======================

This project requires Python 3.10 or higher. It is recommended to use a virtual
environment to manage dependencies.

Create a virtual environment
----------------------------

From the repository root:

.. code-block:: bash

   python -m venv .venv
   source .venv/bin/activate
   python -m pip install -U pip

Install the package
-------------------

Install the project so the ``rsvp_bot`` package is importable:

.. code-block:: bash

   pip install -e .

If your project uses a different workflow (uv/poetry/pip-tools), install the
package in whatever way you prefer. The requirement for the docs and scripts is
that ``import rsvp_bot`` succeeds.

Environment variables
---------------------

The bot reads runtime configuration from environment variables.
The minimal setup is a ``.env`` file at the project root:

.. code-block:: bash

   # Required: Discord bot token
   DISCORD_TOKEN="paste-your-token-here"

   # Optional: timezone used for scheduling and display
   BOT_TIMEZONE="America/Chicago"

   # Optional (DEV mode): sync commands only to this guild for fast iteration
   DEV_GUILD_ID="123456789012345678"

The database location is managed by the bot. By default it stores SQLite at:

- ``./data/bot.db`` (relative to the repo root)

The ``data/`` directory is created automatically if missing.

Run the bot
-----------

Start the bot with:

.. code-block:: bash

   python -m rsvp_bot.bot

You should see the bot connect and then sync commands.
This may take a few seconds on the first run.

Verify command installation
---------------------------

In your Discord server, open the chat input and type ``/``.
You should see the bot’s slash commands appear after syncing completes.

Next
----

- Continue to :doc:`quickstart` to understand the first-run flow.
- Learn the command set: :doc:`../user-guide/commands`
