"""Pytest collection policy: mark Qt GUI tests without repeating decorators."""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(items) -> None:
    for item in items:
        path = str(getattr(item, "path", "")).replace("\\", "/")
        if "/tests/test_gui_" in path:
            item.add_marker(pytest.mark.gui)
