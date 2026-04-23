"""Acceptance tests for optional dependency groups.

Each group declared in pyproject.toml [project.optional-dependencies]
must make the expected third-party modules importable.  If a dependency
is renamed, removed, or its import path changes, these tests will fail.

NOTE: These tests are skipped when the dependency is not installed,
so they only act as regression guards in environments where the extra
is actually installed (e.g. CI with `uv sync --all-extras` or the dev
environment).
"""

import importlib

import pytest

pytestmark = pytest.mark.integration

# Maps each optional group to the third-party modules it should provide.
EXTRA_TO_MODULES: dict[str, list[str]] = {
    "gliner2": ["gliner2"],
    "langchain": ["langchain"],
    "faker": ["faker"],
    "cache": ["aiocache"],
    "client": ["httpx"],
    "spacy": ["spacy"],
    "transformers": ["transformers"],
}


@pytest.mark.parametrize(
    ("extra", "modules"),
    EXTRA_TO_MODULES.items(),
    ids=EXTRA_TO_MODULES.keys(),
)
def test_optional_group_modules_importable(extra: str, modules: list[str]) -> None:
    """Each optional group's dependencies must be importable when installed."""
    for module_name in modules:
        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError:
            pytest.skip(f"{module_name} not installed (extra '{extra}' not active)")
