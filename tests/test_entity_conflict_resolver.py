"""Tests for ``MergeEntityConflictResolver`` and ``FuzzyEntityConflictResolver``."""

from piighost.entity_resolver import (
    FuzzyEntityConflictResolver,
    MergeEntityConflictResolver,
)
from piighost.models import Detection, Entity, Span
from piighost.similarity import levenshtein_similarity


def _det(
    text: str, label: str, start: int, end: int, confidence: float = 0.9
) -> Detection:
    return Detection(
        text=text, label=label, position=Span(start, end), confidence=confidence
    )


# ---------------------------------------------------------------------------
# have_conflict
# ---------------------------------------------------------------------------


class TestHaveConflict:
    """Two entities conflict when they share at least one detection."""

    def test_shared_detection_is_conflict(self) -> None:
        shared = _det("Patrick", "PERSON", 20, 27)
        entity_a = Entity(
            detections=(
                _det("Patrick", "PERSON", 0, 7),
                shared,
            )
        )
        entity_b = Entity(
            detections=(
                shared,
                _det("patric", "PERSON", 30, 36),
            )
        )

        assert MergeEntityConflictResolver().have_conflict(entity_a, entity_b)

    def test_no_shared_detection_no_conflict(self) -> None:
        entity_a = Entity(detections=(_det("Patrick", "PERSON", 0, 7),))
        entity_b = Entity(detections=(_det("Paris", "LOCATION", 20, 25),))

        assert not MergeEntityConflictResolver().have_conflict(entity_a, entity_b)

    def test_same_text_different_position_no_conflict(self) -> None:
        entity_a = Entity(detections=(_det("Patrick", "PERSON", 0, 7),))
        entity_b = Entity(detections=(_det("Patrick", "PERSON", 20, 27),))

        assert not MergeEntityConflictResolver().have_conflict(entity_a, entity_b)


# ---------------------------------------------------------------------------
# resolve no conflicts
# ---------------------------------------------------------------------------


class TestNoConflict:
    """When no entities share detections, all are kept as-is."""

    def test_empty_list(self) -> None:
        assert MergeEntityConflictResolver().resolve([]) == []

    def test_single_entity(self) -> None:
        entity = Entity(detections=(_det("Patrick", "PERSON", 0, 7),))
        result = MergeEntityConflictResolver().resolve([entity])
        assert len(result) == 1
        assert len(result[0].detections) == 1

    def test_no_conflicts_keeps_all(self) -> None:
        entities = [
            Entity(detections=(_det("Patrick", "PERSON", 0, 7),)),
            Entity(detections=(_det("Paris", "LOCATION", 20, 25),)),
        ]
        result = MergeEntityConflictResolver().resolve(entities)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# resolve merging
# ---------------------------------------------------------------------------


class TestMerging:
    """Entities that share detections are merged."""

    def test_two_entities_sharing_one_detection_merged(self) -> None:
        shared = _det("Patrick", "PERSON", 20, 27)
        d_a = _det("Patrick", "PERSON", 0, 7)
        d_c = _det("patric", "PERSON", 30, 36, confidence=0.8)

        entities = [
            Entity(
                detections=(
                    d_a,
                    shared,
                )
            ),
            Entity(
                detections=(
                    shared,
                    d_c,
                )
            ),
        ]
        result = MergeEntityConflictResolver().resolve(entities)

        assert len(result) == 1
        assert len(result[0].detections) == 3

    def test_shared_detection_not_duplicated(self) -> None:
        shared = _det("Patrick", "PERSON", 20, 27)
        entities = [
            Entity(
                detections=(
                    shared,
                    _det("Patrick", "PERSON", 0, 7),
                )
            ),
            Entity(detections=(shared,)),
        ]
        result = MergeEntityConflictResolver().resolve(entities)

        assert len(result) == 1
        detections = result[0].detections
        assert len(detections) == 2  # shared counted once

    def test_transitive_merge(self) -> None:
        # A shares d1 with B, B shares d2 with C → all three merge
        d1 = _det("Patrick", "PERSON", 0, 7)
        d2 = _det("Patrick", "PERSON", 20, 27)
        d3 = _det("patric", "PERSON", 30, 36, confidence=0.8)
        d4 = _det("pat", "PERSON", 40, 43, confidence=0.7)

        entities = [
            Entity(detections=(d1,)),  # A
            Entity(
                detections=(
                    d1,
                    d2,
                )
            ),  # B (shares d1 with A, d2 with C)
            Entity(
                detections=(
                    d2,
                    d3,
                    d4,
                )
            ),  # C
        ]
        result = MergeEntityConflictResolver().resolve(entities)

        assert len(result) == 1
        assert len(result[0].detections) == 4

    def test_partial_merge_keeps_unrelated(self) -> None:
        shared = _det("Patrick", "PERSON", 0, 7)
        entities = [
            Entity(
                detections=(
                    shared,
                    _det("Patrick", "PERSON", 20, 27),
                )
            ),
            Entity(
                detections=(
                    shared,
                    _det("patric", "PERSON", 30, 36),
                )
            ),
            Entity(detections=(_det("Paris", "LOCATION", 50, 55),)),  # unrelated
        ]
        result = MergeEntityConflictResolver().resolve(entities)

        assert len(result) == 2
        labels = {e.label for e in result}
        assert labels == {"PERSON", "LOCATION"}


# ---------------------------------------------------------------------------
# Output ordering
# ---------------------------------------------------------------------------


class TestOutputOrdering:
    """Merged entities are sorted by earliest start position."""

    def test_sorted_by_earliest_start_pos(self) -> None:
        entities = [
            Entity(detections=(_det("Paris", "LOCATION", 30, 35),)),
            Entity(detections=(_det("Patrick", "PERSON", 0, 7),)),
        ]
        result = MergeEntityConflictResolver().resolve(entities)
        positions = [min(d.position.start_pos for d in e.detections) for e in result]
        assert positions == sorted(positions)


# ---------------------------------------------------------------------------
# FuzzyEntityConflictResolver have_conflict
# ---------------------------------------------------------------------------


class TestFuzzyHaveConflict:
    """Two entities conflict when same label and similar canonical text."""

    def test_similar_text_same_label_is_conflict(self) -> None:
        entity_a = Entity(detections=(_det("Patrick", "PERSON", 0, 7),))
        entity_b = Entity(detections=(_det("patric", "PERSON", 20, 26),))

        assert FuzzyEntityConflictResolver().have_conflict(entity_a, entity_b)

    def test_different_label_no_conflict(self) -> None:
        entity_a = Entity(detections=(_det("Patrick", "PERSON", 0, 7),))
        entity_b = Entity(detections=(_det("Patrice", "LOCATION", 20, 27),))

        assert not FuzzyEntityConflictResolver().have_conflict(entity_a, entity_b)

    def test_very_different_text_same_label_no_conflict(self) -> None:
        entity_a = Entity(detections=(_det("Patrick", "PERSON", 0, 7),))
        entity_b = Entity(detections=(_det("Paris", "PERSON", 20, 25),))

        assert not FuzzyEntityConflictResolver().have_conflict(entity_a, entity_b)

    def test_identical_text_same_label_is_conflict(self) -> None:
        entity_a = Entity(detections=(_det("Patrick", "PERSON", 0, 7),))
        entity_b = Entity(detections=(_det("Patrick", "PERSON", 20, 27),))

        assert FuzzyEntityConflictResolver().have_conflict(entity_a, entity_b)

    def test_custom_threshold(self) -> None:
        entity_a = Entity(detections=(_det("Patrick", "PERSON", 0, 7),))
        entity_b = Entity(detections=(_det("patric", "PERSON", 20, 26),))

        # Very high threshold should reject a near-miss.
        resolver = FuzzyEntityConflictResolver(threshold=0.99)
        assert not resolver.have_conflict(entity_a, entity_b)

    def test_custom_similarity_fn(self) -> None:
        entity_a = Entity(detections=(_det("Patrick", "PERSON", 0, 7),))
        entity_b = Entity(detections=(_det("patric", "PERSON", 20, 26),))

        resolver = FuzzyEntityConflictResolver(similarity_fn=levenshtein_similarity)
        assert resolver.have_conflict(entity_a, entity_b)


# ---------------------------------------------------------------------------
# FuzzyEntityConflictResolver resolve
# ---------------------------------------------------------------------------


class TestFuzzyResolve:
    """Fuzzy resolver merges entities with similar canonical text."""

    def test_merges_similar_entities(self) -> None:
        entities = [
            Entity(detections=(_det("Patrick", "PERSON", 0, 7),)),
            Entity(detections=(_det("patric", "PERSON", 20, 26),)),
        ]
        result = FuzzyEntityConflictResolver().resolve(entities)

        assert len(result) == 1
        assert len(result[0].detections) == 2

    def test_does_not_merge_different_entities(self) -> None:
        entities = [
            Entity(detections=(_det("Patrick", "PERSON", 0, 7),)),
            Entity(detections=(_det("Paris", "LOCATION", 20, 25),)),
        ]
        result = FuzzyEntityConflictResolver().resolve(entities)

        assert len(result) == 2

    def test_transitive_fuzzy_merge(self) -> None:
        # "Patrick" ~ "Patrik" ~ "Patri" chain of similarity
        entities = [
            Entity(detections=(_det("Patrick", "PERSON", 0, 7),)),
            Entity(detections=(_det("Patrik", "PERSON", 20, 26),)),
            Entity(detections=(_det("Patri", "PERSON", 40, 45),)),
        ]
        result = FuzzyEntityConflictResolver().resolve(entities)

        assert len(result) == 1
        assert len(result[0].detections) == 3

    def test_with_levenshtein(self) -> None:
        entities = [
            Entity(detections=(_det("Patrick", "PERSON", 0, 7),)),
            Entity(detections=(_det("patric", "PERSON", 20, 26),)),
        ]
        resolver = FuzzyEntityConflictResolver(similarity_fn=levenshtein_similarity)
        result = resolver.resolve(entities)

        assert len(result) == 1
        assert len(result[0].detections) == 2

    def test_empty_list(self) -> None:
        assert FuzzyEntityConflictResolver().resolve([]) == []
