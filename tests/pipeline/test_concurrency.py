"""Concurrency smoke tests for ThreadAnonymizationPipeline.

The pipeline is designed to be shared across coroutines as long as each
call passes its own ``thread_id``.  These tests drive the same instance
from several tasks to catch races on the canonical index, the thread-id
propagation, and the per-thread cache isolation.
"""

import asyncio

import pytest

from piighost.anonymizer import Anonymizer
from piighost.detector import ExactMatchDetector
from piighost.linker.entity import ExactEntityLinker
from piighost.pipeline.thread import ThreadAnonymizationPipeline
from piighost.placeholder import LabelCounterPlaceholderFactory
from piighost.resolver.entity import MergeEntityConflictResolver
from piighost.resolver.span import ConfidenceSpanConflictResolver

pytestmark = pytest.mark.asyncio


def _pipeline() -> ThreadAnonymizationPipeline:
    return ThreadAnonymizationPipeline(
        detector=ExactMatchDetector(
            [("Patrick", "PERSON"), ("Marie", "PERSON"), ("Paris", "LOCATION")]
        ),
        span_resolver=ConfidenceSpanConflictResolver(),
        entity_linker=ExactEntityLinker(),
        entity_resolver=MergeEntityConflictResolver(),
        anonymizer=Anonymizer(LabelCounterPlaceholderFactory()),
    )


class TestConcurrentAnonymize:
    async def test_two_threads_do_not_leak_entities(self) -> None:
        """Parallel anonymize() calls on different threads stay isolated."""
        pipeline = _pipeline()
        result_a, result_b = await asyncio.gather(
            pipeline.anonymize("Bonjour Patrick", thread_id="thread-a"),
            pipeline.anonymize("Bonjour Marie", thread_id="thread-b"),
        )
        # Each thread should only know about its own person.
        mem_a_texts = {
            d.text
            for e in pipeline.get_memory("thread-a").all_entities
            for d in e.detections
        }
        mem_b_texts = {
            d.text
            for e in pipeline.get_memory("thread-b").all_entities
            for d in e.detections
        }
        assert mem_a_texts == {"Patrick"}
        assert mem_b_texts == {"Marie"}
        assert "<<PERSON:1>>" in result_a[0]
        assert "<<PERSON:1>>" in result_b[0]

    async def test_cache_keys_stay_isolated_under_concurrency(self) -> None:
        """Concurrent anonymize() produces correct per-thread deanonymize lookups."""
        pipeline = _pipeline()
        (anon_a, _), (anon_b, _) = await asyncio.gather(
            pipeline.anonymize("Patrick habite à Paris", thread_id="A"),
            pipeline.anonymize("Marie habite à Paris", thread_id="B"),
        )
        original_a, _ = await pipeline.deanonymize(anon_a, thread_id="A")
        original_b, _ = await pipeline.deanonymize(anon_b, thread_id="B")
        assert original_a == "Patrick habite à Paris"
        assert original_b == "Marie habite à Paris"

    async def test_many_concurrent_threads(self) -> None:
        """Fan-out over many thread_ids without cross-contamination."""
        pipeline = _pipeline()
        tasks = [
            pipeline.anonymize(f"Bonjour Patrick {i}", thread_id=f"t{i}")
            for i in range(20)
        ]
        results = await asyncio.gather(*tasks)
        for i, (anon, _) in enumerate(results):
            assert "<<PERSON:1>>" in anon
            memory = pipeline.get_memory(f"t{i}")
            assert len(memory.all_entities) == 1
            assert memory.all_entities[0].detections[0].text == "Patrick"


class TestConcurrentRecord:
    """Sequential calls on the same memory instance stay deterministic.

    ConversationMemory is not designed for simultaneous writers on the
    same thread_id (that is a semantic race, not a bug), but repeated
    interleaved calls on *different* threads must not corrupt the
    canonical index of either.
    """

    async def test_interleaved_threads_do_not_swap_index_slots(self) -> None:
        pipeline = _pipeline()

        async def run(thread_id: str, text: str) -> None:
            for _ in range(10):
                await pipeline.anonymize(text, thread_id=thread_id)

        await asyncio.gather(
            run("x", "Bonjour Patrick"),
            run("y", "Bonjour Marie"),
        )

        ent_x = pipeline.get_memory("x").all_entities
        ent_y = pipeline.get_memory("y").all_entities
        assert len(ent_x) == 1 and ent_x[0].detections[0].text == "Patrick"
        assert len(ent_y) == 1 and ent_y[0].detections[0].text == "Marie"
