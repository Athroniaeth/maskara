"""Tests for ``ThreadAnonymizationPipeline``."""

import re

import pytest

from piighost.anonymizer import Anonymizer
from piighost.pipeline.thread import (
    ThreadAnonymizationPipeline,
)
from piighost.detector import ExactMatchDetector
from piighost.linker.entity import ExactEntityLinker
from piighost.resolver.entity import (
    AnyEntityConflictResolver,
    FuzzyEntityConflictResolver,
    MergeEntityConflictResolver,
)
from piighost.placeholder import CounterPlaceholderFactory, AnyPlaceholderFactory
from piighost.resolver.span import ConfidenceSpanConflictResolver

pytestmark = pytest.mark.asyncio


def _pipeline(
    words: list[tuple[str, str]],
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
        pipeline = _pipeline([("Patrick", "PERSON")])
        await pipeline.anonymize("Bonjour Patrick")
        assert len(pipeline.get_memory().all_entities) == 1
        assert pipeline.get_memory().all_entities[0].label == "PERSON"


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


# ---------------------------------------------------------------------------
# Cross-message entity linking
# ---------------------------------------------------------------------------


class TestCrossMessageEntityLinking:
    """Entities from previous messages are found in new messages via memory."""

    async def test_case_variant_across_messages(self) -> None:
        """'france' in msg2 gets the same token as 'France' in msg1."""
        pipeline = _pipeline([("France", "LOCATION")])
        r1, _ = await pipeline.anonymize("J'habite en France")
        r2, _ = await pipeline.anonymize("donne moi la meteo en france")

        assert "<<LOCATION_1>>" in r1
        assert "<<LOCATION_1>>" in r2
        assert "france" not in r2

    async def test_uppercase_variant_across_messages(self) -> None:
        """'FRANCE' in msg2 gets the same token as 'France' in msg1."""
        pipeline = _pipeline([("France", "LOCATION")])
        await pipeline.anonymize("J'habite en France")
        r2, _ = await pipeline.anonymize("je pars en FRANCE demain")

        assert "FRANCE" not in r2
        assert "<<LOCATION_1>>" in r2

    async def test_anonymize_with_ent_uses_variants(self) -> None:
        """anonymize_with_ent replaces case variants accumulated in memory."""
        pipeline = _pipeline([("Patrick", "PERSON")])
        await pipeline.anonymize("Bonjour Patrick")
        await pipeline.anonymize("bonjour patrick")

        result = pipeline.anonymize_with_ent("patrick est revenu")
        assert "patrick" not in result
        assert "<<PERSON_1>>" in result

    async def test_cross_message_respects_word_boundaries(self) -> None:
        """Memory-based expansion does not create partial matches."""
        pipeline = _pipeline([("France", "LOCATION")])
        await pipeline.anonymize("J'habite en France")
        r2, _ = await pipeline.anonymize("la francette est jolie")

        assert "francette" in r2

    async def test_memory_accumulates_variants(self) -> None:
        """Memory entity gains new text variants across messages."""
        pipeline = _pipeline([("France", "LOCATION")])
        await pipeline.anonymize("J'habite en France")
        await pipeline.anonymize("donne moi la meteo en france")

        entities = pipeline.get_memory().all_entities
        assert len(entities) == 1
        texts = {d.text for d in entities[0].detections}
        assert "France" in texts
        assert "france" in texts

    async def test_person_case_variant_linked_not_new_placeholder(self) -> None:
        """'patrick' in msg2 is linked to 'Patrick' from msg1, not a new entity."""
        pipeline = _pipeline([("Patrick", "PERSON")])
        r1, _ = await pipeline.anonymize("Bonjour je m'appelle Patrick")
        r2, _ = await pipeline.anonymize("Quel est la premiere lettre de patrick")

        assert "<<PERSON_1>>" in r1
        assert "<<PERSON_1>>" in r2
        assert "<<PERSON_2>>" not in r2

    async def test_gliner_detects_lowercase_variant(self) -> None:
        """GLiNER detects both 'Patrick' and 'patrick' → same PERSON_1."""
        pipeline = _pipeline([("Patrick", "PERSON"), ("patrick", "PERSON")])
        r1, _ = await pipeline.anonymize("Bonjour je m'appelle Patrick")
        r2, _ = await pipeline.anonymize("Quel est la premiere lettre de patrick")

        assert "<<PERSON_1>>" in r1
        assert "<<PERSON_1>>" in r2
        assert "<<PERSON_2>>" not in r2

    async def test_gliner_misses_lowercase_variant(self) -> None:
        """GLiNER only detects 'Patrick', not 'patrick' → not anonymized.

        When the detector misses a variant entirely, link_entities
        has nothing to link.  The str.replace fallback in
        anonymize_with_ent still catches it because memory has the
        known text form.
        """
        pipeline = ThreadAnonymizationPipeline(
            detector=ExactMatchDetector([("Patrick", "PERSON")], flags=re.RegexFlag(0)),
            span_resolver=ConfidenceSpanConflictResolver(),
            entity_linker=ExactEntityLinker(),
            entity_resolver=MergeEntityConflictResolver(),
            anonymizer=Anonymizer(CounterPlaceholderFactory()),
        )
        r1, _ = await pipeline.anonymize("Bonjour je m'appelle Patrick")
        r2, _ = await pipeline.anonymize("Quel est la premiere lettre de patrick")

        assert "<<PERSON_1>>" in r1
        # Detector missed "patrick" → link_entities gets [] → no linking
        # anonymize_with_ent only has "Patrick" variant → str.replace misses
        assert "patrick" in r2

    async def test_middleware_reprocessing_keeps_stable_tokens(self) -> None:
        """Simulates abefore_model re-anonymizing all messages each turn.

        The middleware deanonymizes after the LLM responds, then
        re-anonymizes everything on the next turn.  Tokens must stay
        stable across reprocessing cycles.
        """
        pipeline = _pipeline([("Patrick", "PERSON"), ("France", "LOCATION")])

        # --- Turn 1: abefore_model anonymizes msg1 ---
        r1, _ = await pipeline.anonymize(
            "Bonjour, je m'appelle Patrick, j'habite en France"
        )
        assert "<<PERSON_1>>" in r1
        assert "<<LOCATION_1>>" in r1

        # aafter_model deanonymizes → state has original text again
        # LLM produces a response containing the original names

        # --- Turn 2: abefore_model re-anonymizes ALL messages ---
        # Re-anonymize msg1 (same text, already in memory)
        r1_again, _ = await pipeline.anonymize(
            "Bonjour, je m'appelle Patrick, j'habite en France"
        )
        assert "<<PERSON_1>>" in r1_again
        assert "<<LOCATION_1>>" in r1_again

        # Anonymize AI response (contains deanonymized names)
        ai_anon, _ = await pipeline.anonymize(
            "Bonjour Patrick ! Vous habitez en France, tres bien."
        )
        assert "<<PERSON_1>>" in ai_anon
        assert "<<LOCATION_1>>" in ai_anon

        # Anonymize new user message with lowercase variant
        r3, _ = await pipeline.anonymize("Quel est la premiere lettre de patrick")
        assert "<<PERSON_1>>" in r3
        assert "<<PERSON_2>>" not in r3


# ---------------------------------------------------------------------------
# Thread isolation
# ---------------------------------------------------------------------------


class TestThreadIsolation:
    """Memory and cache are isolated per thread_id."""

    async def test_default_thread_id(self) -> None:
        """Without passing thread_id, everything uses 'default'."""
        pipeline = _pipeline([("Patrick", "PERSON")])
        r, _ = await pipeline.anonymize("Bonjour Patrick")
        assert "<<PERSON_1>>" in r
        assert len(pipeline.get_memory().all_entities) == 1

    async def test_different_threads_have_isolated_memory(self) -> None:
        """Thread A sees Patrick; thread B does not."""
        pipeline = _pipeline([("Patrick", "PERSON"), ("Marie", "PERSON")])

        await pipeline.anonymize("Bonjour Patrick", thread_id="thread-a")

        assert pipeline.get_memory("thread-b").all_entities == []

        r, _ = await pipeline.anonymize("Bonjour Marie", thread_id="thread-b")
        assert "<<PERSON_1>>" in r  # Marie is PERSON_1 in thread-b

    async def test_switching_threads_preserves_memory(self) -> None:
        """Going back to thread A still finds Patrick."""
        pipeline = _pipeline([("Patrick", "PERSON"), ("Marie", "PERSON")])

        await pipeline.anonymize("Bonjour Patrick", thread_id="thread-a")
        await pipeline.anonymize("Bonjour Marie", thread_id="thread-b")

        memory_a = pipeline.get_memory("thread-a")
        assert len(memory_a.all_entities) == 1
        assert memory_a.all_entities[0].detections[0].text == "Patrick"

    async def test_cache_isolated_per_thread(self) -> None:
        """Same anonymized text in two threads → deanonymize returns the right original."""
        pipeline = _pipeline([("Patrick", "PERSON"), ("Marie", "PERSON")])

        ra, _ = await pipeline.anonymize("Bonjour Patrick", thread_id="thread-a")
        assert "<<PERSON_1>>" in ra

        rb, _ = await pipeline.anonymize("Bonjour Marie", thread_id="thread-b")
        assert "<<PERSON_1>>" in rb

        original_a, _ = await pipeline.deanonymize(ra, thread_id="thread-a")
        assert original_a == "Bonjour Patrick"

        original_b, _ = await pipeline.deanonymize(rb, thread_id="thread-b")
        assert original_b == "Bonjour Marie"
