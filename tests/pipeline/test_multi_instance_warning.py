"""Tests for the multi-instance configuration warning."""

from __future__ import annotations

import warnings
from collections.abc import Iterator

import pytest
from aiocache import SimpleMemoryCache

from piighost.anonymizer import Anonymizer
from piighost.exceptions import PIIGhostConfigWarning
from piighost.detector import ExactMatchDetector
from piighost.pipeline import thread as thread_module
from piighost.pipeline.thread import ThreadAnonymizationPipeline
from piighost.placeholder import LabelCounterPlaceholderFactory


@pytest.fixture(autouse=True)
def _reset_warning_flag() -> Iterator[None]:
    """Each test starts with a fresh per-process flag."""
    thread_module._multi_instance_warning_emitted = False
    yield


@pytest.fixture(scope="module", autouse=True)
def _seal_flag_after_module() -> Iterator[None]:
    """Mark the warning as emitted once this file is done so subsequent
    test files are not polluted by the per-test resets above."""
    yield
    thread_module._multi_instance_warning_emitted = True


def _build(cache: SimpleMemoryCache | None = None) -> ThreadAnonymizationPipeline:
    return ThreadAnonymizationPipeline(
        detector=ExactMatchDetector([("Patrick", "PERSON")]),
        anonymizer=Anonymizer(LabelCounterPlaceholderFactory()),
        cache=cache,
    )


class TestMultiInstanceWarning:
    """Process-local cache should warn about cross-worker correctness."""

    def test_warns_when_cache_defaults_to_in_memory(self) -> None:
        with pytest.warns(PIIGhostConfigWarning, match="multi-instance"):
            _build()

    def test_warns_when_explicit_simple_memory_cache(self) -> None:
        with pytest.warns(PIIGhostConfigWarning):
            _build(cache=SimpleMemoryCache())

    def test_emits_only_once_per_process(self) -> None:
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always", PIIGhostConfigWarning)
            _build()
            _build()
            _build()
        config_warnings = [w for w in captured if w.category is PIIGhostConfigWarning]
        assert len(config_warnings) == 1

    def test_no_warning_for_non_in_memory_backend(self) -> None:
        class FakeRedisCache(SimpleMemoryCache.__bases__[0]):  # type: ignore[misc]
            """Subclass of BaseCache that is *not* a SimpleMemoryCache."""

            async def _get(self, key, encoding="utf-8", _conn=None):  # noqa: ANN001
                return None

            async def _set(self, key, value, ttl=None, _cas_token=None, _conn=None):  # noqa: ANN001
                return True

            async def _multi_get(self, keys, encoding="utf-8", _conn=None):  # noqa: ANN001
                return [None for _ in keys]

            async def _multi_set(self, pairs, ttl=None, _conn=None):  # noqa: ANN001
                return True

            async def _delete(self, key, _conn=None):  # noqa: ANN001
                return 1

            async def _exists(self, key, _conn=None):  # noqa: ANN001
                return False

            async def _increment(self, key, delta, _conn=None):  # noqa: ANN001
                return delta

            async def _expire(self, key, ttl, _conn=None):  # noqa: ANN001
                return True

            async def _clear(self, namespace=None, _conn=None):  # noqa: ANN001
                return True

            async def _raw(self, command, *args, _conn=None, **kwargs):  # noqa: ANN001
                return None

            async def _redlock_release(self, key, value):  # noqa: ANN001
                return 1

        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always", PIIGhostConfigWarning)
            _build(cache=FakeRedisCache())
        config_warnings = [w for w in captured if w.category is PIIGhostConfigWarning]
        assert config_warnings == []
