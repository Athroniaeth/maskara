"""Tests for ``ExactMatchDetector``."""

import re

import pytest

from v2.detector import ExactMatchDetector

pytestmark = pytest.mark.asyncio
from v2.models import Detection


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _labels(detections: list[Detection]) -> list[str]:
    return [d.label for d in detections]


def _positions(detections: list[Detection]) -> list[tuple[int, int]]:
    return [(d.position.start_pos, d.position.end_pos) for d in detections]


# ---------------------------------------------------------------------------
# Basic matching
# ---------------------------------------------------------------------------


class TestBasicMatching:
    """Core exact-match behaviour."""

    async def test_single_word_single_occurrence(self) -> None:
        detector = ExactMatchDetector([("Patrick", "PERSON")])
        result = await detector.detect("Bonjour Patrick")
        assert len(result) == 1
        assert result[0].label == "PERSON"
        assert result[0].position.start_pos == 8
        assert result[0].position.end_pos == 15

    async def test_single_word_multiple_occurrences(self) -> None:
        detector = ExactMatchDetector([("Patrick", "PERSON")])
        result = await detector.detect("Patrick a dit bonjour à Patrick")
        assert _positions(result) == [(0, 7), (24, 31)]

    async def test_multiple_words_in_bag(self) -> None:
        detector = ExactMatchDetector([("Patrick", "PERSON"), ("Paris", "LOCATION")])
        result = await detector.detect("Patrick habite à Paris")
        assert set(_labels(result)) == {"PERSON", "LOCATION"}
        assert len(result) == 2

    async def test_no_match_returns_empty_list(self) -> None:
        detector = ExactMatchDetector([("Patrick", "PERSON")])
        assert await detector.detect("Rien à voir ici") == []

    async def test_empty_text_returns_empty_list(self) -> None:
        detector = ExactMatchDetector([("Patrick", "PERSON")])
        assert await detector.detect("") == []

    async def test_empty_bag_of_words_returns_empty_list(self) -> None:
        detector = ExactMatchDetector([])
        assert await detector.detect("Patrick habite à Paris") == []


# ---------------------------------------------------------------------------
# Word-boundary behaviour
# ---------------------------------------------------------------------------


class TestWordBoundary:
    """Word-boundary regex prevents partial matches inside longer words."""

    async def test_ignores_partial_match_prefix(self) -> None:
        detector = ExactMatchDetector([("Patrick", "PERSON")])
        result = await detector.detect("APatrick ne compte pas")
        assert result == []

    async def test_ignores_partial_match_suffix(self) -> None:
        detector = ExactMatchDetector([("Patrick", "PERSON")])
        result = await detector.detect("Patrickou ne compte pas")
        assert result == []

    async def test_ignores_partial_match_infix(self) -> None:
        detector = ExactMatchDetector([("art", "MISC")])
        result = await detector.detect("Patrick ne compte pas")
        assert result == []

    async def test_matches_surrounded_by_punctuation(self) -> None:
        detector = ExactMatchDetector([("Patrick", "PERSON")])
        result = await detector.detect("(Patrick), dit-il")
        assert len(result) == 1
        assert result[0].position.start_pos == 1
        assert result[0].position.end_pos == 8

    async def test_matches_at_start_and_end_of_text(self) -> None:
        detector = ExactMatchDetector([("Patrick", "PERSON")])
        result = await detector.detect("Patrick")
        assert _positions(result) == [(0, 7)]


# ---------------------------------------------------------------------------
# Case sensitivity
# ---------------------------------------------------------------------------


class TestCaseSensitivity:
    """Case-insensitive by default, configurable via flags."""

    async def test_case_insensitive_by_default(self) -> None:
        detector = ExactMatchDetector([("paris", "LOCATION")])
        result = await detector.detect("Paris et PARIS et paris")
        assert len(result) == 3

    async def test_case_sensitive_when_no_ignorecase(self) -> None:
        detector = ExactMatchDetector([("Paris", "LOCATION")], flags=re.RegexFlag(0))
        result = await detector.detect("Paris et paris et PARIS")
        assert len(result) == 1
        assert result[0].position.start_pos == 0


# ---------------------------------------------------------------------------
# Special characters
# ---------------------------------------------------------------------------


class TestSpecialCharacters:
    """Words containing regex-special or non-alphanumeric characters."""

    async def test_word_with_dot(self) -> None:
        detector = ExactMatchDetector([("M. Dupont", "PERSON")])
        result = await detector.detect("Bonjour M. Dupont, comment allez-vous ?")
        assert len(result) == 1

    async def test_word_with_hyphen(self) -> None:
        detector = ExactMatchDetector([("Saint-Denis", "LOCATION")])
        result = await detector.detect("Il vit à Saint-Denis depuis 2020")
        assert len(result) == 1

    async def test_phone_number_with_plus(self) -> None:
        detector = ExactMatchDetector([("+33612345678", "PHONE")])
        result = await detector.detect("Appelez le +33612345678 pour info")
        assert len(result) == 1

    async def test_email_address(self) -> None:
        detector = ExactMatchDetector([("user@example.com", "EMAIL")])
        result = await detector.detect("Contactez user@example.com svp")
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Detection attributes
# ---------------------------------------------------------------------------


class TestDetectionAttributes:
    """Verify the Detection objects returned are well-formed."""

    async def test_confidence_is_always_one(self) -> None:
        detector = ExactMatchDetector([("Patrick", "PERSON"), ("Paris", "LOCATION")])
        result = await detector.detect("Patrick à Paris")
        assert all(d.confidence == 1.0 for d in result)

    async def test_label_matches_bag_of_words(self) -> None:
        detector = ExactMatchDetector([("Patrick", "PERSON"), ("Paris", "LOCATION")])
        result = await detector.detect("Patrick à Paris")
        labels = {d.label for d in result}
        assert labels == {"PERSON", "LOCATION"}

    async def test_span_extracts_correct_substring(self) -> None:
        text = "Bonjour Patrick à Paris"
        detector = ExactMatchDetector([("Patrick", "PERSON")])
        result = await detector.detect(text)
        assert len(result) == 1
        span = result[0].position
        assert text[span.start_pos : span.end_pos] == "Patrick"

    async def test_hash_is_unique_per_occurrence(self) -> None:
        detector = ExactMatchDetector([("Patrick", "PERSON")])
        result = await detector.detect("Patrick et Patrick")
        assert len(result) == 2
        assert result[0].hash != result[1].hash
