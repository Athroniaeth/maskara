"""Tests for ``RegexDetector``."""

import pytest

from piighost.detector import RegexDetector
from piighost.models import Detection

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _labels(detections: list[Detection]) -> list[str]:
    return [d.label for d in detections]


def _texts(detections: list[Detection]) -> list[str]:
    return [d.text for d in detections]


# ---------------------------------------------------------------------------
# Basic matching
# ---------------------------------------------------------------------------


class TestBasicMatching:
    """Core regex detection behaviour."""

    async def test_single_pattern_single_match(self) -> None:
        detector = RegexDetector(patterns={"EMAIL": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"})
        result = await detector.detect("Contactez alice@example.com svp")
        assert len(result) == 1
        assert result[0].label == "EMAIL"
        assert result[0].text == "alice@example.com"

    async def test_single_pattern_multiple_matches(self) -> None:
        detector = RegexDetector(patterns={"EMAIL": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"})
        result = await detector.detect("alice@example.com et bob@example.com")
        assert len(result) == 2
        assert _texts(result) == ["alice@example.com", "bob@example.com"]

    async def test_multiple_patterns(self) -> None:
        detector = RegexDetector(patterns={
            "EMAIL": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            "IP_V4": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        })
        result = await detector.detect("alice@example.com sur 192.168.1.1")
        assert set(_labels(result)) == {"EMAIL", "IP_V4"}

    async def test_no_match_returns_empty(self) -> None:
        detector = RegexDetector(patterns={"EMAIL": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"})
        assert await detector.detect("Rien à voir ici") == []

    async def test_empty_text_returns_empty(self) -> None:
        detector = RegexDetector(patterns={"EMAIL": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"})
        assert await detector.detect("") == []

    async def test_empty_patterns_returns_empty(self) -> None:
        detector = RegexDetector(patterns={})
        assert await detector.detect("alice@example.com") == []


# ---------------------------------------------------------------------------
# Detection attributes
# ---------------------------------------------------------------------------


class TestDetectionAttributes:
    """Verify Detection objects are well-formed."""

    async def test_confidence_is_always_one(self) -> None:
        detector = RegexDetector(patterns={"EMAIL": r"\S+@\S+"})
        result = await detector.detect("a@b.com c@d.com")
        assert all(d.confidence == 1.0 for d in result)

    async def test_positions_are_correct(self) -> None:
        text = "Mon IP: 10.0.0.1 voilà"
        detector = RegexDetector(patterns={"IP_V4": r"\b(?:\d{1,3}\.){3}\d{1,3}\b"})
        result = await detector.detect(text)
        assert len(result) == 1
        span = result[0].position
        assert text[span.start_pos:span.end_pos] == "10.0.0.1"

    async def test_hash_is_unique_per_match(self) -> None:
        detector = RegexDetector(patterns={"IP_V4": r"\b(?:\d{1,3}\.){3}\d{1,3}\b"})
        result = await detector.detect("10.0.0.1 et 10.0.0.2")
        assert len(result) == 2
        assert result[0].hash != result[1].hash


# ---------------------------------------------------------------------------
# Real-world patterns
# ---------------------------------------------------------------------------


class TestRealWorldPatterns:
    """Test with patterns from the examples."""

    async def test_french_phone(self) -> None:
        detector = RegexDetector(patterns={"FR_PHONE": r"\b(?:\+33|0)[1-9](?:[\s.\-]?\d{2}){4}\b"})
        result = await detector.detect("Appelez le 06 12 34 56 78 pour info")
        assert len(result) == 1
        assert result[0].label == "FR_PHONE"

    async def test_iban(self) -> None:
        detector = RegexDetector(patterns={"EU_IBAN": r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}[A-Z0-9]{0,16}\b"})
        result = await detector.detect("IBAN: FR7630006000011234567890189")
        assert len(result) == 1
        assert result[0].label == "EU_IBAN"

    async def test_openai_api_key(self) -> None:
        detector = RegexDetector(patterns={"OPENAI_API_KEY": r"sk-(?:proj-)?[A-Za-z0-9\-_]{20,}"})
        result = await detector.detect("key: sk-proj-abc123xyz456789ABCDEFGH")
        assert len(result) == 1
        assert result[0].label == "OPENAI_API_KEY"