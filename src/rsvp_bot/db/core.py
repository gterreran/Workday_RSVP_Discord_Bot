# src/rsvp_bot/db/core.py

"""
Low-level database connection core
==================================

This module provides the minimal connection primitive used by all database
operation mixins in :mod:`rsvp_bot.db`.

The :class:`DBCore` class encapsulates the SQLite database path and exposes a
single method, :meth:`DBCore.connect`, which returns an
:class:`aiosqlite.Connection`. Higher-level database layers (e.g. channel,
directory, RSVP, and scheduler ops) rely on this method via composition or
multiple inheritance.

The class is intentionally minimal and does not manage migrations, pooling, or
lifecycle hooks — those concerns are handled by higher-level database wrappers.

Classes
-------

:class:`DBCore`
    Thin wrapper around a filesystem-backed SQLite database path that provides
    async connection objects.
"""

from __future__ import annotations

from pathlib import Path

import aiosqlite


class DBCore:
    """
    Minimal SQLite connection provider for async database operations.

    This class stores the path to the SQLite database file and exposes a
    :meth:`connect` helper returning a new :class:`aiosqlite.Connection`.
    It is designed to be used as a base class or mixin for higher-level database
    abstractions.

    .. rubric:: Attributes

    _path : :class:`pathlib.Path`
        Filesystem path to the SQLite database file.
    """

    def __init__(self, path: Path) -> None:
        """
        Initialize the database core with a file path.

        Parameters
        ----------
        path : :class:`pathlib.Path`
            Filesystem path to the SQLite database file.
        """
        self._path = path

    def connect(self) -> aiosqlite.Connection:
        """
        Create a new async SQLite connection.

        Returns
        -------
        :class:`aiosqlite.Connection`
            A new connection bound to the configured database path.

        Notes
        -----
        The caller is responsible for using the connection as an async context
        manager (e.g. ``async with self.connect() as db``) to ensure proper
        cleanup.
        """
        return aiosqlite.connect(self._path.as_posix())
