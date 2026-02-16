"""
Pytest configuration for the energy bill app test suite.

Registers the custom 'e2e' marker used to tag Playwright end-to-end tests.
By default, tests marked with @pytest.mark.e2e are skipped unless the
'-m e2e' flag is passed explicitly.

Run unit tests only (default):
    pytest

Run E2E tests only:
    pytest -m e2e

Run everything:
    pytest -m ""
"""
import pytest


def pytest_collection_modifyitems(config, items):
    """Auto-skip E2E tests unless the user explicitly selects them."""
    # If the user passed an explicit marker expression, respect it.
    marker_expr = config.getoption("-m", default="")
    if marker_expr:
        return

    skip_e2e = pytest.mark.skip(
        reason="E2E tests are skipped by default. Run with: pytest -m e2e"
    )
    for item in items:
        if "e2e" in item.keywords:
            item.add_marker(skip_e2e)
