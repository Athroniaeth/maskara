"""Tests for ``SQLAlchemyCache`` exercised against in-memory aiosqlite."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from piighost.cache.sqlalchemy import SQLAlchemyCache


pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def cache() -> AsyncIterator[SQLAlchemyCache]:
    """Provide a fresh in-memory aiosqlite cache per test.

    A unique table name keeps SQLAlchemy's metadata cache from
    leaking schema between tests when they run in the same process.
    """
    backend = SQLAlchemyCache(
        url="sqlite+aiosqlite:///:memory:",
        table_name=f"cache_{id(asyncio.current_task())}",
    )
    await backend.create_schema()
    try:
        yield backend
    finally:
        await backend.close()


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    """The constructor enforces the url-or-engine invariant."""

    async def test_requires_url_or_engine(self) -> None:
        with pytest.raises(ValueError, match="exactly one of"):
            SQLAlchemyCache()

    async def test_rejects_both_url_and_engine(self) -> None:
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            with pytest.raises(ValueError, match="exactly one of"):
                SQLAlchemyCache(url="sqlite+aiosqlite:///:memory:", engine=engine)
        finally:
            await engine.dispose()


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """Set / get / delete behave like the in-memory backend."""

    async def test_set_then_get(self, cache: SQLAlchemyCache) -> None:
        await cache.set("k", {"v": 1, "nested": [1, 2]})
        assert await cache.get("k") == {"v": 1, "nested": [1, 2]}

    async def test_get_unknown_key(self, cache: SQLAlchemyCache) -> None:
        assert await cache.get("nope") is None

    async def test_overwrite_with_set(self, cache: SQLAlchemyCache) -> None:
        await cache.set("k", "first")
        await cache.set("k", "second")
        assert await cache.get("k") == "second"

    async def test_delete(self, cache: SQLAlchemyCache) -> None:
        await cache.set("k", "v")
        assert await cache.delete("k") == 1
        assert await cache.get("k") is None

    async def test_delete_unknown_key(self, cache: SQLAlchemyCache) -> None:
        assert await cache.delete("nope") == 0

    async def test_exists(self, cache: SQLAlchemyCache) -> None:
        await cache.set("k", "v")
        assert await cache.exists("k") is True
        assert await cache.exists("nope") is False


# ---------------------------------------------------------------------------
# Multi-* operations
# ---------------------------------------------------------------------------


class TestMultiOps:
    async def test_multi_set_then_multi_get(self, cache: SQLAlchemyCache) -> None:
        await cache.multi_set([("a", 1), ("b", 2), ("c", 3)])
        assert await cache.multi_get(["a", "b", "c"]) == [1, 2, 3]

    async def test_multi_get_with_unknown_keys(self, cache: SQLAlchemyCache) -> None:
        await cache.set("a", 1)
        assert await cache.multi_get(["a", "missing"]) == [1, None]


# ---------------------------------------------------------------------------
# Add (insert-only)
# ---------------------------------------------------------------------------


class TestAdd:
    async def test_add_new_key(self, cache: SQLAlchemyCache) -> None:
        assert await cache.add("k", "v") is True
        assert await cache.get("k") == "v"

    async def test_add_existing_key_raises(self, cache: SQLAlchemyCache) -> None:
        await cache.set("k", "v")
        with pytest.raises(ValueError, match="already exists"):
            await cache.add("k", "other")


# ---------------------------------------------------------------------------
# TTL & expiry
# ---------------------------------------------------------------------------


class TestTTL:
    async def test_ttl_set_then_get_within_window(self, cache: SQLAlchemyCache) -> None:
        await cache.set("k", "v", ttl=60)
        assert await cache.get("k") == "v"

    async def test_expired_entry_is_purged_lazily(self, cache: SQLAlchemyCache) -> None:
        # ttl=0.01 makes the entry expire almost immediately; the read
        # path must drop the row and return None.
        await cache.set("k", "v", ttl=0.01)
        await asyncio.sleep(0.05)
        assert await cache.get("k") is None

    async def test_expire_existing_key(self, cache: SQLAlchemyCache) -> None:
        await cache.set("k", "v")
        assert await cache.expire("k", ttl=0.01) is True
        await asyncio.sleep(0.05)
        assert await cache.get("k") is None

    async def test_expire_unknown_key(self, cache: SQLAlchemyCache) -> None:
        assert await cache.expire("nope", ttl=10) is False


# ---------------------------------------------------------------------------
# Clear & namespace
# ---------------------------------------------------------------------------


class TestClear:
    async def test_clear_all(self, cache: SQLAlchemyCache) -> None:
        await cache.set("a", 1)
        await cache.set("b", 2)
        await cache.clear()
        assert await cache.get("a") is None
        assert await cache.get("b") is None

    async def test_clear_namespace_only_drops_matching_keys(
        self, cache: SQLAlchemyCache
    ) -> None:
        await cache.set("user-a:msg", 1)
        await cache.set("user-a:meta", 2)
        await cache.set("user-b:msg", 3)
        await cache.clear(namespace="user-a:")
        assert await cache.get("user-a:msg") is None
        assert await cache.get("user-a:meta") is None
        assert await cache.get("user-b:msg") == 3


# ---------------------------------------------------------------------------
# Pipeline integration smoke-test
# ---------------------------------------------------------------------------


class TestPipelineIntegration:
    """The pipeline accepts SQLAlchemyCache as a drop-in cache."""

    async def test_anonymize_round_trip(self, cache: SQLAlchemyCache) -> None:
        from piighost.anonymizer import Anonymizer
        from piighost.detector.base import ExactMatchDetector
        from piighost.pipeline import AnonymizationPipeline
        from piighost.placeholder import LabelCounterPlaceholderFactory

        pipeline = AnonymizationPipeline(
            detector=ExactMatchDetector(
                [("Patrick", "PERSON"), ("Paris", "LOCATION")],
            ),
            anonymizer=Anonymizer(LabelCounterPlaceholderFactory()),
            cache=cache,
        )
        anonymized, _ = await pipeline.anonymize("Patrick lives in Paris.")
        assert anonymized == "<<PERSON:1>> lives in <<LOCATION:1>>."

        original, _ = await pipeline.deanonymize(anonymized)
        assert original == "Patrick lives in Paris."

    async def test_thread_pipeline_persists_across_instances(self) -> None:
        """A fresh ThreadAnonymizationPipeline pointing at the same DB
        sees the mappings written by the previous one."""
        from piighost.anonymizer import Anonymizer
        from piighost.detector.base import ExactMatchDetector
        from piighost.pipeline.thread import ThreadAnonymizationPipeline
        from piighost.placeholder import LabelCounterPlaceholderFactory

        # Shared file would be ideal for a real persistence test, but
        # in-memory aiosqlite gives the same guarantees as long as the
        # engine stays alive between the two pipelines.
        backend = SQLAlchemyCache(
            url="sqlite+aiosqlite:///:memory:",
            table_name="shared_thread_cache",
        )
        await backend.create_schema()
        try:
            first = ThreadAnonymizationPipeline(
                detector=ExactMatchDetector([("Patrick", "PERSON")]),
                anonymizer=Anonymizer(LabelCounterPlaceholderFactory()),
                cache=backend,
            )
            await first.anonymize("Patrick is here.", thread_id="user-A")

            second = ThreadAnonymizationPipeline(
                detector=ExactMatchDetector([("Patrick", "PERSON")]),
                anonymizer=Anonymizer(LabelCounterPlaceholderFactory()),
                cache=backend,
            )
            restored, _ = await second.deanonymize(
                "<<PERSON:1>> is here.", thread_id="user-A"
            )
            assert restored == "Patrick is here."
        finally:
            await backend.close()
