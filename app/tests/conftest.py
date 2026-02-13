"""
Pytest configuration for E2E tests.

Configures Playwright fixtures and pytest markers specific to E2E tests.
"""
import pytest


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "e2e: mark test as an end-to-end test"
    )
    config.addinivalue_line(
        "markers", "performance: mark test as a performance/stress test"
    )
