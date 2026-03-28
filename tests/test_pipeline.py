"""Tests for ``AnonymizationPipeline``."""

import pytest
from aiocache import Cache, BaseCache

from piighost.anonymizer import Anonymizer
from piighost.detector import ExactMatchDetector
from piighost.exceptions import CacheMissError
from piighost.linker.entity import ExactEntityLinker
from piighost.pipeline.base import AnonymizationPipeline
from piighost.placeholder import (
    CounterPlaceholderFactory,
    RedactPlaceholderFactory,
    AnyPlaceholderFactory,
)
from piighost.resolver.entity import MergeEntityConflictResolver
from piighost.resolver.span import ConfidenceSpanConflictResolver

pytestmark = pytest.mark.asyncio


def _pipeline(
    words: list[tuple[str, str]],
    cache: BaseCache | None = None,
    factory: AnyPlaceholderFactory | None = None,
) -> AnonymizationPipeline:
    """Build a pipeline with ExactMatchDetector for testing."""
    return AnonymizationPipeline(
        detector=ExactMatchDetector(words),
        span_resolver=ConfidenceSpanConflictResolver(),
        entity_linker=ExactEntityLinker(),
        entity_resolver=MergeEntityConflictResolver(),
        anonymizer=Anonymizer(factory or CounterPlaceholderFactory()),
        cache=cache,
    )


# ---------------------------------------------------------------------------
# End-to-end anonymization
# ---------------------------------------------------------------------------


class TestAnonymize:
    """Full pipeline: detect → resolve → link → resolve → anonymize."""

    async def test_single_entity(self) -> None:
        pipeline = _pipeline([("Patrick", "PERSON")])
        result, _ = await pipeline.anonymize("Bonjour Patrick")
        assert result == "Bonjour <<PERSON_1>>"

    async def test_multiple_entities(self) -> None:
        pipeline = _pipeline([("Patrick", "PERSON"), ("Paris", "LOCATION")])
        result, _ = await pipeline.anonymize("Patrick habite à Paris")
        assert "<<PERSON_1>>" in result
        assert "<<LOCATION_1>>" in result
        assert "Patrick" not in result
        assert "Paris" not in result

    async def test_expands_to_all_occurrences(self) -> None:
        pipeline = _pipeline([("Patrick", "PERSON")])
        result, _ = await pipeline.anonymize("Patrick est gentil. Patrick habite ici.")
        assert result.count("<<PERSON_1>>") == 2

    async def test_no_match_returns_unchanged(self) -> None:
        pipeline = _pipeline([("Patrick", "PERSON")])
        result, _ = await pipeline.anonymize("Rien à voir ici")
        assert result == "Rien à voir ici"

    async def test_with_redact_factory(self) -> None:
        pipeline = _pipeline(
            [("Patrick", "PERSON"), ("Henri", "PERSON")],
            factory=RedactPlaceholderFactory(),
        )
        result, _ = await pipeline.anonymize("Patrick et Henri")
        assert result == "<PERSON> et <PERSON>"


# ---------------------------------------------------------------------------
# Deanonymize
# ---------------------------------------------------------------------------


class TestDeanonymize:
    """deanonymize() restores text using stored mappings in cache."""

    async def test_deanonymize_from_anonymized_text(self) -> None:
        pipeline = _pipeline([("Patrick", "PERSON")], cache=Cache(Cache.MEMORY))
        text = "Bonjour Patrick"
        anonymized, _ = await pipeline.anonymize(text)
        restored, _ = await pipeline.deanonymize(anonymized)
        assert restored == text

    async def test_deanonymize_multiple_entities(self) -> None:
        pipeline = _pipeline(
            [("Patrick", "PERSON"), ("Paris", "LOCATION")], cache=Cache(Cache.MEMORY)
        )
        text = "Patrick habite à Paris"
        anonymized, _ = await pipeline.anonymize(text)
        restored, _ = await pipeline.deanonymize(anonymized)
        assert restored == text

    async def test_deanonymize_unknown_text_raises(self) -> None:
        pipeline = _pipeline([("Patrick", "PERSON")], cache=Cache(Cache.MEMORY))
        with pytest.raises(CacheMissError):
            await pipeline.deanonymize("unknown text")

    async def test_deanonymize_with_spelling_variants(self) -> None:
        pipeline = _pipeline(
            [("Patrick", "PERSON"), ("patric", "PERSON")], cache=Cache(Cache.MEMORY)
        )
        text = "Patrick et patric sont amis"
        anonymized, _ = await pipeline.anonymize(text)
        restored, _ = await pipeline.deanonymize(anonymized)
        assert restored == text

    async def test_deanonymize_with_default_cache(self) -> None:
        pipeline = _pipeline([("Patrick", "PERSON")], cache=None)
        text = "Bonjour Patrick"
        anonymized, _ = await pipeline.anonymize(text)
        restored, _ = await pipeline.deanonymize(anonymized)
        assert restored == text


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


class TestCache:
    """Detector results are cached via aiocache."""

    async def test_cache_avoids_second_detection(self) -> None:
        cache = Cache(Cache.MEMORY)
        pipeline = _pipeline([("Patrick", "PERSON")], cache=cache)

        # First call detector runs.
        result1, _ = await pipeline.anonymize("Bonjour Patrick")
        assert result1 == "Bonjour <<PERSON_1>>"

        # Spy on the detector to check it's not called again.
        original_detect = pipeline._detector.detect
        call_count = 0

        async def counting_detect(text):
            nonlocal call_count
            call_count += 1
            return await original_detect(text)

        pipeline._detector.detect = counting_detect  # type: ignore

        # Second call same text, should use cache.
        result2, _ = await pipeline.anonymize("Bonjour Patrick")
        assert result2 == "Bonjour <<PERSON_1>>"
        assert call_count == 0

    async def test_different_text_not_cached(self) -> None:
        cache = Cache(Cache.MEMORY)
        pipeline = _pipeline([("Patrick", "PERSON")], cache=cache)

        await pipeline.anonymize("Bonjour Patrick")
        result, _ = await pipeline.anonymize("Salut Patrick")
        assert "<<PERSON_1>>" in result

    async def test_no_cache_still_works(self) -> None:
        pipeline = _pipeline([("Patrick", "PERSON")], cache=None)
        result, _ = await pipeline.anonymize("Bonjour Patrick")
        assert result == "Bonjour <<PERSON_1>>"
