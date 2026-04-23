"""Tests for ``ConversationMemory``."""

from piighost.pipeline.thread import ConversationMemory, _replace_longest_first
from piighost.models import Detection, Entity, Span


def _entity(text: str, label: str, start: int = 0) -> Entity:
    """Helper to build an entity with a single detection."""
    return Entity(
        detections=(
            Detection(
                text=text,
                label=label,
                position=Span(start_pos=start, end_pos=start + len(text)),
                confidence=1.0,
            ),
        )
    )


class TestRecord:
    """ConversationMemory.record() stores entities and deduplicates."""

    def test_record_stores_entities_by_hash(self) -> None:
        memory = ConversationMemory()
        entity = _entity("Patrick", "PERSON")
        memory.record("hash1", [entity])
        assert "hash1" in memory.entities_by_hash
        assert memory.entities_by_hash["hash1"] == [entity]

    def test_record_deduplicates_same_canonical(self) -> None:
        memory = ConversationMemory()
        e1 = _entity("Patrick", "PERSON", start=0)
        e2 = _entity("Patrick", "PERSON", start=20)
        memory.record("hash1", [e1])
        memory.record("hash2", [e2])
        assert len(memory.all_entities) == 1

    def test_record_deduplicates_case_insensitive(self) -> None:
        memory = ConversationMemory()
        e1 = _entity("Patrick", "PERSON")
        e2 = _entity("patrick", "PERSON")
        memory.record("hash1", [e1])
        memory.record("hash2", [e2])
        assert len(memory.all_entities) == 1

    def test_record_keeps_different_labels(self) -> None:
        memory = ConversationMemory()
        e1 = _entity("Paris", "LOCATION")
        e2 = _entity("Paris", "ORGANIZATION")
        memory.record("hash1", [e1])
        memory.record("hash2", [e2])
        assert len(memory.all_entities) == 2

    def test_record_keeps_different_texts(self) -> None:
        memory = ConversationMemory()
        e1 = _entity("Patrick", "PERSON")
        e2 = _entity("Marie", "PERSON")
        memory.record("hash1", [e1])
        memory.record("hash2", [e2])
        assert len(memory.all_entities) == 2

    def test_record_same_hash_extends(self) -> None:
        memory = ConversationMemory()
        e1 = _entity("Patrick", "PERSON")
        e2 = _entity("Marie", "PERSON")
        memory.record("hash1", [e1])
        memory.record("hash1", [e2])
        assert len(memory.entities_by_hash["hash1"]) == 2


class TestAllEntities:
    """ConversationMemory.all_entities property."""

    def test_empty_memory(self) -> None:
        memory = ConversationMemory()
        assert memory.all_entities == []

    def test_preserves_insertion_order(self) -> None:
        memory = ConversationMemory()
        e1 = _entity("Patrick", "PERSON")
        e2 = _entity("Paris", "LOCATION")
        e3 = _entity("Marie", "PERSON")
        memory.record("hash1", [e1, e2])
        memory.record("hash2", [e3])
        assert memory.all_entities == [e1, e2, e3]

    def test_is_append_only_across_messages(self) -> None:
        """Entities from earlier messages always come first."""
        memory = ConversationMemory()
        e1 = _entity("Patrick", "PERSON")
        e2 = _entity("Marie", "PERSON")
        memory.record("hash1", [e1])
        memory.record("hash2", [e2])
        all_ent = memory.all_entities
        assert all_ent[0] == e1
        assert all_ent[1] == e2


class TestCanonicalIndex:
    """The canonical index keeps lookups O(1) and stays consistent on merges."""

    def test_index_points_to_slot(self) -> None:
        memory = ConversationMemory()
        e1 = _entity("Patrick", "PERSON")
        memory.record("hash1", [e1])
        assert memory._canonical_index[("patrick", "PERSON")] == ("hash1", 0)

    def test_case_variant_merges_into_existing_slot(self) -> None:
        memory = ConversationMemory()
        memory.record("h1", [_entity("Patrick", "PERSON")])
        memory.record("h2", [_entity("patrick", "PERSON")])
        # The variant must land in the *original* slot, not spawn a new entity.
        assert memory._canonical_index[("patrick", "PERSON")] == ("h1", 0)
        stored = memory.entities_by_hash["h1"][0]
        texts = {d.text for d in stored.detections}
        assert texts == {"Patrick", "patrick"}

    def test_variant_with_same_text_does_not_duplicate_detection(self) -> None:
        memory = ConversationMemory()
        memory.record("h1", [_entity("Patrick", "PERSON")])
        memory.record("h2", [_entity("Patrick", "PERSON")])
        stored = memory.entities_by_hash["h1"][0]
        assert len(stored.detections) == 1

    def test_index_keys_are_canonical_pairs(self) -> None:
        memory = ConversationMemory()
        memory.record("h1", [_entity("Patrick", "PERSON")])
        memory.record("h1", [_entity("Paris", "LOCATION")])
        assert set(memory._canonical_index) == {
            ("patrick", "PERSON"),
            ("paris", "LOCATION"),
        }


class TestReplaceLongestFirst:
    """Helper that performs a multi-token replacement in one regex pass."""

    def test_empty_pairs_returns_text_unchanged(self) -> None:
        assert _replace_longest_first("hello", []) == "hello"

    def test_basic_replacement(self) -> None:
        assert _replace_longest_first("Patrick", [("Patrick", "X")]) == "X"

    def test_longer_source_wins_over_prefix(self) -> None:
        """'Patrick Dupont' must beat 'Patrick' on the same input."""
        out = _replace_longest_first(
            "Patrick Dupont",
            [("Patrick", "A"), ("Patrick Dupont", "B")],
        )
        assert out == "B"

    def test_regex_metachars_escaped(self) -> None:
        out = _replace_longest_first("a.b and c.d", [("a.b", "X"), ("c.d", "Y")])
        assert out == "X and Y"

    def test_first_mapping_wins_on_duplicates(self) -> None:
        """Duplicate source keeps the earliest-seen target."""
        out = _replace_longest_first("hi", [("hi", "first"), ("hi", "second")])
        assert out == "first"

    def test_empty_source_skipped(self) -> None:
        """Empty source strings must not match everywhere."""
        out = _replace_longest_first("foo", [("", "BAD"), ("foo", "OK")])
        assert out == "OK"

    def test_single_pass_no_chain_replacement(self) -> None:
        """Replacing does not cascade into a just-written target."""
        out = _replace_longest_first("ab", [("a", "b"), ("b", "a")])
        assert out == "ba"
