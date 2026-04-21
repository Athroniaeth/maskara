"""Shared fixtures for Haystack component tests.

These tests require the optional ``haystack`` extras (and, for the
LanceDB-backed ones, ``haystack-lancedb`` which pulls ``pyarrow``). When
those extras are not installed (e.g. the default CI ``uv sync --dev``),
the whole directory is skipped at collection time via ``collect_ignore_glob``
so pytest does not error out on module-level ``from haystack import …``
imports inside the sibling test files.
"""

from importlib.util import find_spec

import pytest

# Skip the whole haystack test directory at collection if the optional
# deps are missing. Sibling test modules import ``haystack``/``pyarrow``
# at top level, so gating must happen before they are collected.
if find_spec("haystack") is None or find_spec("pyarrow") is None:
    collect_ignore_glob = ["test_*.py"]

from piighost.anonymizer import Anonymizer
from piighost.detector import ExactMatchDetector
from piighost.linker.entity import ExactEntityLinker
from piighost.pipeline.thread import ThreadAnonymizationPipeline
from piighost.placeholder import HashPlaceholderFactory
from piighost.resolver.entity import MergeEntityConflictResolver
from piighost.resolver.span import ConfidenceSpanConflictResolver


@pytest.fixture
def pipeline() -> ThreadAnonymizationPipeline:
    """A ThreadAnonymizationPipeline with HashPlaceholderFactory.

    Uses ``ExactMatchDetector`` so tests don't need GLiNER2 loaded.
    Detects ``Patrick`` as PERSON, ``Paris`` and ``France`` as LOCATION.
    """
    return ThreadAnonymizationPipeline(
        detector=ExactMatchDetector(
            [("Patrick", "PERSON"), ("Paris", "LOCATION"), ("France", "LOCATION")]
        ),
        span_resolver=ConfidenceSpanConflictResolver(),
        entity_linker=ExactEntityLinker(),
        entity_resolver=MergeEntityConflictResolver(),
        anonymizer=Anonymizer(HashPlaceholderFactory()),
    )
