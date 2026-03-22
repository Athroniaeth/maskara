"""Tests for middleware import guard."""

import sys
from unittest.mock import patch

import pytest


def test_import_error_when_langchain_missing() -> None:
    """ImportError is raised if langchain is not installed."""
    module = "maskara.middleware"
    saved = sys.modules.pop(module, None)
    try:
        with patch("importlib.util.find_spec", return_value=None):
            with pytest.raises(ImportError, match="maskara\\[langchain\\]"):
                import maskara.middleware  # noqa: F401
    finally:
        if saved is not None:
            sys.modules[module] = saved
        else:
            sys.modules.pop(module, None)
