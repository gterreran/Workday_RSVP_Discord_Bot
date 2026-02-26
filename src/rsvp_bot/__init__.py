"""
RSVP bot package
================

Top-level package for the Workday RSVP Bot.

This module exposes the primary public entrypoint used by CLI tools and
``python -m`` execution while keeping the rest of the package structure
internally organized.

"""

from .bot import main

__all__ = ["main"]
