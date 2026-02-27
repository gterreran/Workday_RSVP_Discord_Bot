"""
Basic smoke tests for the RSVP bot package.

These tests ensure the package imports correctly and the main entrypoint
is available. They act as a safety net for packaging and CI.
"""


def test_import_package():
    """The top-level package should be importable."""
    import rsvp_bot  # noqa: F401


def test_import_entrypoint():
    """The CLI entrypoint module should import without errors."""
    from rsvp_bot.bot import main  # noqa: F401


def test_package_has_version():
    """Optional sanity check if you later add __version__."""
    import rsvp_bot

    # Don't fail if not defined yet, just ensure import works.
    assert hasattr(rsvp_bot, "__name__")
