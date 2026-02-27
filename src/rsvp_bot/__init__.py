"""
RSVP bot package
================

Top-level package for the Workday RSVP Bot.

We intentionally keep the top-level import surface lightweight so that
subpackages (e.g. :mod:`rsvp_bot.db`) can be imported in environments where
optional runtime dependencies (like the Discord client) are not present.

The CLI entrypoint is still available as :func:`main`, which lazily imports
:mod:`rsvp_bot.bot` when called.

"""

from __future__ import annotations

from typing import Any

def main(*args: Any, **kwargs: Any):
    """
    CLI entrypoint for the installed ``rsvp-bot`` script.

    This function lazily imports :func:`rsvp_bot.bot.main` to avoid importing
    Discord-related dependencies when the caller only needs other parts of the
    package (e.g. while testing).

    Parameters
    ----------
    *args
        Positional arguments forwarded to :func:`rsvp_bot.bot.main`.
    **kwargs
        Keyword arguments forwarded to :func:`rsvp_bot.bot.main`.

    Returns
    -------
    Any
        Whatever :func:`rsvp_bot.bot.main` returns.
    """
    from .bot import main as _main

    return _main(*args, **kwargs)


__all__ = ["main"]