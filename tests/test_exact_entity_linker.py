"""Tests for ``ExactEntityLinker``."""

from piighost.linker.entity import ExactEntityLinker
from piighost.models import Detection, Span


def _det(
    text: str, label: str, start: int, end: int, confidence: float = 0.9
) -> Detection:
    return Detection(
        text=text, label=label, position=Span(start, end), confidence=confidence
    )


# ---------------------------------------------------------------------------
# Expansion finding missed occurrences
# ---------------------------------------------------------------------------


class TestExpansion:
    """The linker creates new detections for occurrences missed by the detector."""

    def test_expands_single_detection_to_all_occurrences(self) -> None:
        text = "Patrick est gentil. Patrick habite ici."
        detections = [_det("Patrick", "PERSON", 0, 7)]
        entities = ExactEntityLinker().link(text, detections)

        assert len(entities) == 1
        assert len(entities[0].detections) == 2

    def test_expanded_detection_has_confidence_one(self) -> None:
        text = "Patrick est gentil. Patrick habite ici."
        detections = [_det("Patrick", "PERSON", 0, 7, confidence=0.85)]
        entities = ExactEntityLinker().link(text, detections)

        confidences = {d.confidence for d in entities[0].detections}
        assert 0.85 in confidences  # original preserved
        assert 1.0 in confidences  # expanded detection

    def test_no_duplicate_when_already_detected(self) -> None:
        text = "Patrick est gentil. Patrick habite ici."
        detections = [
            _det("Patrick", "PERSON", 0, 7),
            _det("Patrick", "PERSON", 20, 27),
        ]
        entities = ExactEntityLinker().link(text, detections)

        assert len(entities) == 1
        assert len(entities[0].detections) == 2

    def test_does_not_expand_partial_matches(self) -> None:
        text = "Patrick et APatrick"
        detections = [_det("Patrick", "PERSON", 0, 7)]
        entities = ExactEntityLinker().link(text, detections)

        assert len(entities) == 1
        assert len(entities[0].detections) == 1


# ---------------------------------------------------------------------------
# Grouping detections of the same PII become one Entity
# ---------------------------------------------------------------------------


class TestGrouping:
    """Detections referring to the same PII are grouped into one Entity."""

    def test_same_text_same_label_grouped(self) -> None:
        text = "Patrick a dit bonjour à Patrick"
        detections = [
            _det("Patrick", "PERSON", 0, 7),
            _det("Patrick", "PERSON", 24, 31),
        ]
        entities = ExactEntityLinker().link(text, detections)
        assert len(entities) == 1

    def test_different_labels_not_grouped(self) -> None:
        text = "Patrick habite à Paris"
        detections = [
            _det("Patrick", "PERSON", 0, 7),
            _det("Paris", "LOCATION", 17, 22),
        ]
        entities = ExactEntityLinker().link(text, detections)
        assert len(entities) == 2

    def test_case_insensitive_grouping(self) -> None:
        text = "Patrick dit bonjour. PATRICK est là."
        detections = [
            _det("Patrick", "PERSON", 0, 7),
            _det("PATRICK", "PERSON", 21, 28),
        ]
        entities = ExactEntityLinker().link(text, detections)
        assert len(entities) == 1
        assert len(entities[0].detections) == 2

    def test_entity_label_from_first_detection(self) -> None:
        text = "Patrick habite ici"
        detections = [_det("Patrick", "PERSON", 0, 7)]
        entities = ExactEntityLinker().link(text, detections)
        assert entities[0].label == "PERSON"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Boundary conditions."""

    def test_empty_detections_returns_empty(self) -> None:
        assert ExactEntityLinker().link("du texte ici", []) == []

    def test_original_confidence_preserved(self) -> None:
        text = "Patrick est là"
        detections = [_det("Patrick", "PERSON", 0, 7, confidence=0.73)]
        entities = ExactEntityLinker().link(text, detections)
        assert entities[0].detections[0].confidence == 0.73

    def test_entities_sorted_by_earliest_position(self) -> None:
        text = "Paris est belle. Patrick est gentil."
        detections = [
            _det("Patrick", "PERSON", 17, 24),
            _det("Paris", "LOCATION", 0, 5),
        ]
        entities = ExactEntityLinker().link(text, detections)
        assert entities[0].label == "LOCATION"
        assert entities[1].label == "PERSON"

    def test_multiple_entities_with_expansion(self) -> None:
        text = "Patrick habite à Paris. Patrick aime Paris."
        detections = [
            _det("Patrick", "PERSON", 0, 7),
            _det("Paris", "LOCATION", 17, 22),
        ]
        entities = ExactEntityLinker().link(text, detections)

        assert len(entities) == 2
        for entity in entities:
            assert len(entity.detections) == 2
