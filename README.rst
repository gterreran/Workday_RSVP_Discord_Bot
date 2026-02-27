.. image:: docs/_static/logo.png
   :alt: Workday RSVP Discord Bot logo
   :height: 100px
   :align: center

Workday RSVP Discord Bot
========================

.. image:: https://img.shields.io/badge/docs-latest-blue.svg
   :target: https://gterreran.github.io/Workday_RSVP_Discord_Bot/
   :alt: Documentation

.. image:: https://img.shields.io/github/v/tag/gterreran/Workday_RSVP_Discord_Bot
   :target: https://github.com/gterreran/Workday_RSVP_Discord_Bot/releases
   :alt: Latest version

.. image:: https://img.shields.io/github/license/gterreran/Workday_RSVP_Discord_Bot
   :target: https://github.com/gterreran/Workday_RSVP_Discord_Bot/blob/main/LICENSE
   :alt: License

A roduction-ready, lightweight RSVP Discord bot that collects attendance declarations for recurring workdays.

Why this bot?
-------------

Most Discord RSVP tools are event-based or ephemeral.  
This bot is designed for **recurring workdays** with:

- persistent panels
- weekly automation
- minimal admin overhead

Features
--------

- Per-channel RSVP tracking
- Button-based attendance selection
- Deadline-based reminders
- Admin-managed participant directory
- Automatic weekly rollover

📖 Documentation: https://gterreran.github.io/Workday_RSVP_Discord_Bot/

---

Installation
------------

Requirements
~~~~~~~~~~~~

- Python **3.11+**
- A Discord bot token

Install from GitHub
~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   pip install git+https://github.com/gterreran/Workday_RSVP_Discord_Bot.git

Development install
~~~~~~~~~~~~~~~~~~~

For local development:

.. code-block:: bash

   git clone https://github.com/gterreran/Workday_RSVP_Discord_Bot.git
   cd Workday_RSVP_Discord_Bot
   pip install -e .

Optional extras:

.. code-block:: bash

   pip install -e ".[dev]"   # docs + tests + tooling

---

Configuration
-------------

Create a ``.env`` file in the project root:

.. code-block:: bash

   DISCORD_TOKEN="your-token-here"
   BOT_TIMEZONE="America/Chicago"   # optional
   DEV_GUILD_ID="1234567890"        # optional (faster dev sync)

The bot automatically loads ``.env`` at startup.

---

Run the bot
-----------

Once installed, start the bot with:

.. code-block:: bash

   rsvp-bot

Alternatively, you can run the module directly:

.. code-block:: bash

   python -m rsvp_bot.bot

---

Documentation
-------------

Full documentation (architecture, concepts, and commands):

https://gterreran.github.io/Workday_RSVP_Discord_Bot/

---

License
-------

This project is licensed under the MIT License.  
See the `LICENSE <https://github.com/gterreran/Workday_RSVP_Discord_Bot/blob/main/LICENSE>`_ file for details.
