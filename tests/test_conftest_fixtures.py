"""Smoke tests for the shared fixtures exposed by tests/conftest.py."""

from aiocache import SimpleMemoryCache

from piighost.anonymizer import Anonymizer
from piighost.detector import ExactMatchDetector
from piighost.pipeline.base import AnonymizationPipeline
from piighost.pipeline.thread import ThreadAnonymizationPipeline
from piighost.placeholder import CounterPlaceholderFactory
from tests.conftest import make_entity


class TestHelpers:
    def test_make_entity_shapes_span_correctly(self) -> None:
        entity = make_entity("Patrick", "PERSON", start=3)
        det = entity.detections[0]
        assert det.text == "Patrick"
        assert det.position.start_pos == 3
        assert det.position.end_pos == 10
        assert det.confidence == 1.0


class TestFixtureTypes:
    """Each fixture hands back the expected concrete type."""

    def test_counter_factory(self, counter_factory: CounterPlaceholderFactory) -> None:
        assert isinstance(counter_factory, CounterPlaceholderFactory)

    def test_memory_cache(self, memory_cache: SimpleMemoryCache) -> None:
        assert memory_cache is not None

    def test_patrick_detector(self, patrick_detector: ExactMatchDetector) -> None:
        assert isinstance(patrick_detector, ExactMatchDetector)

    def test_base_pipeline(self, base_pipeline: AnonymizationPipeline) -> None:
        assert isinstance(base_pipeline, AnonymizationPipeline)

    def test_thread_pipeline(
        self, thread_pipeline: ThreadAnonymizationPipeline
    ) -> None:
        assert isinstance(thread_pipeline, ThreadAnonymizationPipeline)


class TestFixturesWorkEndToEnd:
    async def test_base_pipeline_anonymizes(
        self, base_pipeline: AnonymizationPipeline
    ) -> None:
        result, _ = await base_pipeline.anonymize("Bonjour Patrick à Paris")
        assert "<<PERSON_" in result
        assert "<<LOCATION_" in result

    async def test_thread_pipeline_anonymizes(
        self, thread_pipeline: ThreadAnonymizationPipeline
    ) -> None:
        result, _ = await thread_pipeline.anonymize("Bonjour Patrick", thread_id="t1")
        assert "<<PERSON_1>>" in result

    async def test_memory_cache_is_fresh_per_test_part_1(
        self, memory_cache: SimpleMemoryCache
    ) -> None:
        await memory_cache.set("k", "v1")
        assert await memory_cache.get("k") == "v1"

    async def test_memory_cache_is_fresh_per_test_part_2(
        self, memory_cache: SimpleMemoryCache
    ) -> None:
        # The fixture must be a new instance: no leftover from part_1.
        assert await memory_cache.get("k") is None

    async def test_factory_rebuilt_for_isolation(
        self,
        counter_factory: CounterPlaceholderFactory,
        patrick_detector: ExactMatchDetector,
        memory_cache: SimpleMemoryCache,
    ) -> None:
        # Building two pipelines from the same factory would collide in
        # token numbering; the fixture returns a fresh one each test.
        pipe = AnonymizationPipeline(
            detector=patrick_detector,
            anonymizer=Anonymizer(counter_factory),
            cache=memory_cache,
        )
        out, _ = await pipe.anonymize("Bonjour Patrick")
        assert "<<PERSON_1>>" in out
