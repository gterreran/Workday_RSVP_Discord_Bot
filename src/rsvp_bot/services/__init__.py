# src/rsvp_bot/services/__init__.py

"""
Service layer exports
=====================

Public entry points for the RSVP bot service layer.

This package groups the core runtime services responsible for orchestrating
panel lifecycle management, RSVP interaction flows, and background scheduling.
Importing from :mod:`rsvp_bot.services` provides stable, high-level access
to the main service classes without requiring consumers to know the internal
module layout.

Classes
-------

:class:`~rsvp_bot.services.panel_service.PanelService`
    Manages creation, refresh, and cleanup of the persistent RSVP panel message.

:class:`~rsvp_bot.services.rsvp_service.RSVPService`
    Handles RSVP interaction flows, including modals, partner selection,
    and database updates triggered by button callbacks.

:class:`~rsvp_bot.services.scheduler_service.SchedulerService`
    Runs background loops for reminders and weekly rollover scheduling.
"""

from .panel_service import PanelService
from .rsvp_service import RSVPService
from .scheduler_service import SchedulerService

__all__ = [
    "PanelService",
    "RSVPService",
    "SchedulerService",
]
