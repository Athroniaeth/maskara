"""Tests for ``CompositeDetector``."""

import pytest

from piighost.detector import CompositeDetector, ExactMatchDetector, RegexDetector
from piighost.models import Detection

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _labels(detections: list[Detection]) -> list[str]:
    return [d.label for d in detections]


# ---------------------------------------------------------------------------
# Basic behaviour
# ---------------------------------------------------------------------------


class TestBasicBehaviour:
    """CompositeDetector merges results from child detectors."""

    async def test_combines_two_detectors(self) -> None:
        detector = CompositeDetector(detectors=[
            ExactMatchDetector([("Patrick", "PERSON")]),
            RegexDetector(patterns={"EMAIL": r"\S+@\S+"}),
        ])
        result = await detector.detect("Patrick envoie un mail à alice@example.com")
        assert set(_labels(result)) == {"PERSON", "EMAIL"}

    async def test_empty_detectors_returns_empty(self) -> None:
        detector = CompositeDetector(detectors=[])
        assert await detector.detect("Patrick alice@example.com") == []

    async def test_single_detector_passthrough(self) -> None:
        inner = ExactMatchDetector([("Patrick", "PERSON")])
        detector = CompositeDetector(detectors=[inner])
        result = await detector.detect("Bonjour Patrick")
        assert len(result) == 1
        assert result[0].label == "PERSON"

    async def test_overlapping_detections_are_kept(self) -> None:
        """CompositeDetector does NOT deduplicate — that's the span resolver's job."""
        detector = CompositeDetector(detectors=[
            ExactMatchDetector([("06 12", "PHONE_FRAGMENT")]),
            RegexDetector(patterns={"FR_PHONE": r"\b0[1-9](?:[\s.\-]?\d{2}){4}\b"}),
        ])
        result = await detector.detect("Appelez le 06 12 34 56 78")
        # Both detectors should find something in the same area
        assert len(result) >= 2

    async def test_multiple_regex_detectors(self) -> None:
        detector = CompositeDetector(detectors=[
            RegexDetector(patterns={"EMAIL": r"\S+@\S+"}),
            RegexDetector(patterns={"IP_V4": r"\b(?:\d{1,3}\.){3}\d{1,3}\b"}),
        ])
        result = await detector.detect("alice@example.com sur 10.0.0.1")
        assert set(_labels(result)) == {"EMAIL", "IP_V4"}

    async def test_no_match_from_any_detector(self) -> None:
        detector = CompositeDetector(detectors=[
            ExactMatchDetector([("Patrick", "PERSON")]),
            RegexDetector(patterns={"EMAIL": r"\S+@\S+"}),
        ])
        assert await detector.detect("Rien à voir") == []

    async def test_preserves_detection_order(self) -> None:
        """Detections from first detector come before second detector's."""
        detector = CompositeDetector(detectors=[
            ExactMatchDetector([("Patrick", "PERSON")]),
            RegexDetector(patterns={"EMAIL": r"\S+@\S+"}),
        ])
        result = await detector.detect("alice@example.com et Patrick")
        assert result[0].label == "PERSON"
        assert result[1].label == "EMAIL"