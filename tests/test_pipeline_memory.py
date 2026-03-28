"""Tests for ``ThreadAnonymizationPipeline``."""

import pytest

from piighost.anonymizer import Anonymizer
from piighost.pipeline.thread import (
    ThreadAnonymizationPipeline,
    ConversationMemory,
)
from piighost.detector import ExactMatchDetector
from piighost.linker.entity import ExactEntityLinker
from piighost.resolver.entity import (
    FuzzyEntityConflictResolver,
    MergeEntityConflictResolver,
)
from piighost.placeholder import CounterPlaceholderFactory, AnyPlaceholderFactory
from piighost.resolver.span import ConfidenceSpanConflictResolver


from piighost.resolver.entity import AnyEntityConflictResolver

pytestmark = pytest.mark.asyncio


def _pipeline(
    words: list[tuple[str, str]],
    memory: ConversationMemory | None = None,
    factory: AnyPlaceholderFactory | None = None,
    entity_resolver: AnyEntityConflictResolver | None = None,
) -> ThreadAnonymizationPipeline:
    """Build a conversation pipeline for testing."""
    return ThreadAnonymizationPipeline(
        detector=ExactMatchDetector(words),
        span_resolver=ConfidenceSpanConflictResolver(),
        entity_linker=ExactEntityLinker(),
        entity_resolver=entity_resolver or MergeEntityConflictResolver(),
        anonymizer=Anonymizer(factory or CounterPlaceholderFactory()),
        memory=memory or ConversationMemory(),
    )


# ---------------------------------------------------------------------------
# deanonymize_with_ent token → original via str.replace
# ---------------------------------------------------------------------------


class TestDeanonymizeWithEnt:
    """deanonymize_with_ent() replaces tokens with originals using memory."""

    async def test_deanonymize_text_never_anonymized(self) -> None:
        """LLM-generated text containing tokens can be deanonymized."""
        pipeline = _pipeline([("Patrick", "PERSON"), ("Paris", "LOCATION")])
        await pipeline.anonymize("Patrick habite à Paris")

        # LLM generates a new sentence with known tokens
        llm_output = "Il fait beau à <<LOCATION_1>>"
        result = await pipeline.deanonymize_with_ent(llm_output)
        assert result == "Il fait beau à Paris"

    async def test_deanonymize_single_token(self) -> None:
        """Tool argument containing a single token."""
        pipeline = _pipeline([("Patrick", "PERSON")])
        await pipeline.anonymize("Bonjour Patrick")

        result = await pipeline.deanonymize_with_ent("<<PERSON_1>>")
        assert result == "Patrick"

    async def test_deanonymize_no_tokens_unchanged(self) -> None:
        pipeline = _pipeline([("Patrick", "PERSON")])
        await pipeline.anonymize("Bonjour Patrick")

        result = await pipeline.deanonymize_with_ent("Pas de tokens ici")
        assert result == "Pas de tokens ici"

    async def test_deanonymize_empty_memory(self) -> None:
        pipeline = _pipeline([("Patrick", "PERSON")])
        result = await pipeline.deanonymize_with_ent("<<PERSON_1>>")
        assert result == "<<PERSON_1>>"

    async def test_deanonymize_multiple_tokens(self) -> None:
        pipeline = _pipeline([("Patrick", "PERSON"), ("Paris", "LOCATION")])
        await pipeline.anonymize("Patrick habite à Paris")

        result = await pipeline.deanonymize_with_ent(
            "<<PERSON_1>> est à <<LOCATION_1>>"
        )
        assert result == "Patrick est à Paris"


# ---------------------------------------------------------------------------
# anonymize_with_ent original → token via str.replace
# ---------------------------------------------------------------------------


class TestAnonymizeWithEnt:
    """anonymize_with_ent() replaces known originals with tokens."""

    async def test_reanonymize_known_values(self) -> None:
        pipeline = _pipeline([("Patrick", "PERSON")])
        await pipeline.anonymize("Bonjour Patrick")

        result = pipeline.anonymize_with_ent("Patrick est revenu")
        assert result == "<<PERSON_1>> est revenu"

    async def test_reanonymize_all_spelling_variants(self) -> None:
        """All detected forms of an entity are replaced, not just canonical."""
        pipeline = _pipeline([("Patrick", "PERSON"), ("patric", "PERSON")])
        await pipeline.anonymize("Patrick et patric sont amis")

        result = pipeline.anonymize_with_ent("patric est là, Patrick aussi")
        assert "patric" not in result
        assert "Patrick" not in result
        assert "<<PERSON_1>>" in result

    async def test_reanonymize_no_known_values_unchanged(self) -> None:
        pipeline = _pipeline([("Patrick", "PERSON")])
        await pipeline.anonymize("Bonjour Patrick")

        result = pipeline.anonymize_with_ent("Rien de sensible")
        assert result == "Rien de sensible"

    async def test_reanonymize_empty_memory(self) -> None:
        pipeline = _pipeline([("Patrick", "PERSON")])
        result = pipeline.anonymize_with_ent("Patrick est là")
        assert result == "Patrick est là"


# ---------------------------------------------------------------------------
# Cross-message consistency
# ---------------------------------------------------------------------------


class TestCrossMessageConsistency:
    """Tokens stay stable across multiple anonymize() calls."""

    async def test_same_entity_same_token_across_messages(self) -> None:
        pipeline = _pipeline([("Patrick", "PERSON")])
        r1, _ = await pipeline.anonymize("Bonjour Patrick")
        r2, _ = await pipeline.anonymize("Au revoir Patrick")
        assert "<<PERSON_1>>" in r1
        assert "<<PERSON_1>>" in r2

    async def test_new_entity_gets_next_counter(self) -> None:
        pipeline = _pipeline([("Patrick", "PERSON"), ("Marie", "PERSON")])
        await pipeline.anonymize("Bonjour Patrick")
        r2, _ = await pipeline.anonymize("Bonjour Marie")
        assert "<<PERSON_2>>" in r2

    async def test_mixed_labels_stable(self) -> None:
        pipeline = _pipeline(
            [("Patrick", "PERSON"), ("Paris", "LOCATION"), ("Marie", "PERSON")]
        )
        await pipeline.anonymize("Patrick habite à Paris")
        r2, _ = await pipeline.anonymize("Marie habite à Paris")
        # Marie is the 2nd PERSON, Paris stays LOCATION_1
        assert "<<PERSON_2>>" in r2
        assert "<<LOCATION_1>>" in r2

    async def test_memory_records_entities(self) -> None:
        memory = ConversationMemory()
        pipeline = _pipeline([("Patrick", "PERSON")], memory=memory)
        await pipeline.anonymize("Bonjour Patrick")
        assert len(memory.all_entities) == 1
        assert memory.all_entities[0].label == "PERSON"


# ---------------------------------------------------------------------------
# Cross-message fuzzy entity resolution
# ---------------------------------------------------------------------------


class TestFuzzyEntityResolution:
    """FuzzyEntityConflictResolver merges similar entities across messages."""

    async def test_fuzzy_merges_similar_names(self) -> None:
        pipeline = _pipeline(
            [("Patrick", "PERSON"), ("patric", "PERSON")],
            entity_resolver=FuzzyEntityConflictResolver(),
        )
        r1, _ = await pipeline.anonymize("Bonjour Patrick")
        r2, _ = await pipeline.anonymize("Bonjour patric")

        assert "<<PERSON_1>>" in r1
        assert "<<PERSON_1>>" in r2

    async def test_without_fuzzy_keeps_separate(self) -> None:
        pipeline = _pipeline([("Patrick", "PERSON"), ("patric", "PERSON")])
        r1, _ = await pipeline.anonymize("Bonjour Patrick")
        r2, _ = await pipeline.anonymize("Bonjour patric")

        assert "<<PERSON_1>>" in r1
        assert "<<PERSON_2>>" in r2

    async def test_fuzzy_does_not_merge_different_labels(self) -> None:
        pipeline = _pipeline(
            [("Patrick", "PERSON"), ("patric", "LOCATION")],
            entity_resolver=FuzzyEntityConflictResolver(),
        )
        await pipeline.anonymize("Bonjour Patrick")
        r2, _ = await pipeline.anonymize("A patric")

        assert "<<LOCATION_1>>" in r2

    async def test_fuzzy_deanonymize_with_ent(self) -> None:
        pipeline = _pipeline(
            [("Patrick", "PERSON"), ("patric", "PERSON")],
            entity_resolver=FuzzyEntityConflictResolver(),
        )
        await pipeline.anonymize("Bonjour Patrick")
        await pipeline.anonymize("Bonjour patric")

        result = await pipeline.deanonymize_with_ent("<<PERSON_1>> est là")
        assert result == "Patrick est là"

    async def test_fuzzy_anonymize_with_ent_replaces_all_variants(self) -> None:
        pipeline = _pipeline(
            [("Patrick", "PERSON"), ("patric", "PERSON")],
            entity_resolver=FuzzyEntityConflictResolver(),
        )
        await pipeline.anonymize("Bonjour Patrick")
        await pipeline.anonymize("Bonjour patric")

        result = pipeline.anonymize_with_ent("patric et Patrick")
        assert "patric" not in result
        assert "Patrick" not in result
        assert "<<PERSON_1>>" in result
