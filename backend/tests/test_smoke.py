"""Smoke tests for the cycloai package scaffold (T1)."""

import cycloai


def test_package_is_importable() -> None:
    assert cycloai.__version__ == "0.1.0"
