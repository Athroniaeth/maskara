"""Tests for ``ConfidenceSpanConflictResolver``."""

from piighost.models import Detection, Span
from piighost.resolver.span import ConfidenceSpanConflictResolver


def _make(
    label: str, start: int, end: int, confidence: float, text: str = ""
) -> Detection:
    return Detection(
        text=text, label=label, position=Span(start, end), confidence=confidence
    )


# ---------------------------------------------------------------------------
# No conflicts
# ---------------------------------------------------------------------------


class TestNoConflict:
    """When there are no overlapping spans, all detections are kept."""

    def test_empty_list(self) -> None:
        assert ConfidenceSpanConflictResolver().resolve([]) == []

    def test_single_detection(self) -> None:
        d = _make("PERSON", 0, 7, 0.9)
        assert ConfidenceSpanConflictResolver().resolve([d]) == [d]

    def test_non_overlapping_detections(self) -> None:
        detections = [
            _make("PERSON", 0, 7, 0.9),
            _make("LOCATION", 20, 26, 0.8),
        ]
        result = ConfidenceSpanConflictResolver().resolve(detections)
        assert len(result) == 2

    def test_adjacent_spans_are_not_conflicts(self) -> None:
        detections = [
            _make("PERSON", 0, 5, 0.9),
            _make("LOCATION", 5, 10, 0.8),
        ]
        result = ConfidenceSpanConflictResolver().resolve(detections)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Overlap resolution
# ---------------------------------------------------------------------------


class TestOverlapResolution:
    """Overlapping spans are resolved by keeping the highest confidence."""

    def test_two_overlapping_keeps_higher_confidence(self) -> None:
        detections = [
            _make("PERSON", 17, 24, 0.91),
            _make("PERSON", 17, 22, 0.51),
        ]
        result = ConfidenceSpanConflictResolver().resolve(detections)
        assert len(result) == 1
        assert result[0].confidence == 0.91

    def test_three_detections_one_overlap(self) -> None:
        detections = [
            _make("PERSON", 17, 24, 0.91),
            _make("PERSON", 17, 22, 0.51),
            _make("LOCATION", 45, 51, 1.0),
        ]
        result = ConfidenceSpanConflictResolver().resolve(detections)
        assert len(result) == 2
        assert result[0].confidence == 0.91
        assert result[1].confidence == 1.0

    def test_partial_overlap(self) -> None:
        detections = [
            _make("PERSON", 0, 10, 0.7),
            _make("LOCATION", 8, 15, 0.9),
        ]
        result = ConfidenceSpanConflictResolver().resolve(detections)
        assert len(result) == 1
        assert result[0].label == "LOCATION"

    def test_contained_span(self) -> None:
        detections = [
            _make("PERSON", 5, 20, 0.85),
            _make("MISC", 8, 12, 0.95),
        ]
        result = ConfidenceSpanConflictResolver().resolve(detections)
        assert len(result) == 1
        assert result[0].label == "MISC"

    def test_chain_of_overlaps(self) -> None:
        # A overlaps B, B overlaps C, but A does not overlap C
        detections = [
            _make("A", 0, 10, 0.5),
            _make("B", 8, 18, 0.9),
            _make("C", 16, 25, 0.6),
        ]
        result = ConfidenceSpanConflictResolver().resolve(detections)
        # B wins (highest), then A and C both overlap B → discarded
        assert len(result) == 1
        assert result[0].label == "B"

    def test_equal_confidence_keeps_first_encountered(self) -> None:
        detections = [
            _make("PERSON", 0, 10, 0.9),
            _make("LOCATION", 5, 15, 0.9),
        ]
        result = ConfidenceSpanConflictResolver().resolve(detections)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Output ordering
# ---------------------------------------------------------------------------


class TestOutputOrdering:
    """Results are sorted by start position."""

    def test_result_sorted_by_start_pos(self) -> None:
        detections = [
            _make("LOCATION", 30, 36, 1.0),
            _make("PERSON", 0, 7, 0.9),
            _make("DATE", 15, 25, 0.8),
        ]
        result = ConfidenceSpanConflictResolver().resolve(detections)
        positions = [d.position.start_pos for d in result]
        assert positions == sorted(positions)
