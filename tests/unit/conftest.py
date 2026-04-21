"""Shared fixtures and environment setup for CLI unit tests.

Many tests in this directory render Typer's ``--help`` and assert on the
presence of specific option names (e.g. ``--project``, ``--filter-prefix``).
Typer defers rendering to Rich, which wraps against ``COLUMNS`` — the
default on GitHub-hosted runners is 80, which truncates long option names
off-screen and turns ``result.output`` into a panel frame with no text.

Force a wide terminal for the whole CLI-unit-test session so every
``CliRunner.invoke(..., ['cmd', '--help'])`` assertion works regardless
of the runner's ambient terminal width. CliRunner inherits ``os.environ``
(unless ``env=`` is passed explicitly), so setting it at module import
time is enough.
"""
from __future__ import annotations

import os

os.environ.setdefault("COLUMNS", "200")
# Disable any smart terminal heuristics that might re-detect width.
os.environ.setdefault("TERM", "dumb")
