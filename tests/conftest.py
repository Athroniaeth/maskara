"""Shared fixtures and helpers for the piighost test suite.

The existing tests build their own pipelines via small local helpers
(``_pipeline``, ``_entity``).  Centralising the common building blocks
here lets new tests skip that boilerplate while keeping older files
working unchanged.
"""

from __future__ import annotations

import pytest
from aiocache import SimpleMemoryCache

from piighost.anonymizer import Anonymizer
from piighost.detector import ExactMatchDetector
from piighost.models import Detection, Entity, Span
from piighost.pipeline.base import AnonymizationPipeline
from piighost.pipeline.thread import ThreadAnonymizationPipeline
from piighost.placeholder import CounterPlaceholderFactory


# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------


def make_entity(
    text: str, label: str, start: int = 0, confidence: float = 1.0
) -> Entity:
    """Build a single-detection Entity for quick test setup."""
    return Entity(
        detections=(
            Detection(
                text=text,
                label=label,
                position=Span(start_pos=start, end_pos=start + len(text)),
                confidence=confidence,
            ),
        )
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def counter_factory() -> CounterPlaceholderFactory:
    """Deterministic placeholder factory used by most pipeline tests."""
    return CounterPlaceholderFactory()


@pytest.fixture
def memory_cache() -> SimpleMemoryCache:
    """Fresh in-memory aiocache instance per test (no cross-test leakage)."""
    return SimpleMemoryCache()


@pytest.fixture
def patrick_detector() -> ExactMatchDetector:
    """Common single-name detector used across pipeline/middleware tests."""
    return ExactMatchDetector([("Patrick", "PERSON")])


@pytest.fixture
def patrick_paris_detector() -> ExactMatchDetector:
    """Multi-entity detector for person + location scenarios."""
    return ExactMatchDetector([("Patrick", "PERSON"), ("Paris", "LOCATION")])


@pytest.fixture
def base_pipeline(
    patrick_paris_detector: ExactMatchDetector,
    counter_factory: CounterPlaceholderFactory,
    memory_cache: SimpleMemoryCache,
) -> AnonymizationPipeline:
    """Stateless pipeline backed by an isolated in-memory cache."""
    return AnonymizationPipeline(
        detector=patrick_paris_detector,
        anonymizer=Anonymizer(counter_factory),
        cache=memory_cache,
    )


@pytest.fixture
def thread_pipeline(
    patrick_paris_detector: ExactMatchDetector,
    counter_factory: CounterPlaceholderFactory,
) -> ThreadAnonymizationPipeline:
    """Conversation-aware pipeline with default in-memory cache."""
    return ThreadAnonymizationPipeline(
        detector=patrick_paris_detector,
        anonymizer=Anonymizer(counter_factory),
    )
