"""Shared fixtures for Haystack component tests."""

import pytest

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
