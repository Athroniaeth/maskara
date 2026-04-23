"""Tests for ``ChunkedDetector``."""

import pytest

from piighost.detector import ChunkedDetector, ExactMatchDetector
from piighost.models import Span


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    """``__post_init__`` rejects invalid parameters."""

    def test_overlap_gte_chunk_size_raises(self) -> None:
        with pytest.raises(ValueError, match="overlap.*must be less than chunk_size"):
            ChunkedDetector(
                detector=ExactMatchDetector([]),
                chunk_size=100,
                overlap=100,
            )

    def test_overlap_greater_than_chunk_size_raises(self) -> None:
        with pytest.raises(ValueError, match="overlap.*must be less than chunk_size"):
            ChunkedDetector(
                detector=ExactMatchDetector([]),
                chunk_size=100,
                overlap=200,
            )

    def test_negative_chunk_size_raises(self) -> None:
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            ChunkedDetector(
                detector=ExactMatchDetector([]),
                chunk_size=-1,
                overlap=0,
            )

    def test_zero_chunk_size_raises(self) -> None:
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            ChunkedDetector(
                detector=ExactMatchDetector([]),
                chunk_size=0,
                overlap=0,
            )

    def test_negative_overlap_raises(self) -> None:
        with pytest.raises(ValueError, match="overlap must be non-negative"):
            ChunkedDetector(
                detector=ExactMatchDetector([]),
                chunk_size=100,
                overlap=-1,
            )

    def test_valid_params_no_error(self) -> None:
        ChunkedDetector(
            detector=ExactMatchDetector([]),
            chunk_size=100,
            overlap=0,
        )


# ---------------------------------------------------------------------------
# Short-circuit
# ---------------------------------------------------------------------------


class TestShortCircuit:
    """Texts shorter than or equal to ``chunk_size`` bypass chunking."""

    async def test_short_text_no_splitting(self) -> None:
        inner = ExactMatchDetector([("Patrick", "PERSON")])
        chunked = ChunkedDetector(detector=inner, chunk_size=100, overlap=10)

        result = await chunked.detect("Bonjour Patrick")
        assert len(result) == 1
        assert result[0].text == "Patrick"
        assert result[0].position == Span(8, 15)

    async def test_text_exactly_chunk_size(self) -> None:
        text = "x" * 50
        inner = ExactMatchDetector([])
        chunked = ChunkedDetector(detector=inner, chunk_size=50, overlap=10)

        result = await chunked.detect(text)
        assert result == []

    async def test_empty_text(self) -> None:
        inner = ExactMatchDetector([("Patrick", "PERSON")])
        chunked = ChunkedDetector(detector=inner, chunk_size=100, overlap=10)

        result = await chunked.detect("")
        assert result == []


# ---------------------------------------------------------------------------
# Chunking algorithm
# ---------------------------------------------------------------------------


class TestChunking:
    """``_compute_chunks`` produces correct offsets."""

    def _make_detector(self, chunk_size: int, overlap: int) -> ChunkedDetector:
        return ChunkedDetector(
            detector=ExactMatchDetector([]),
            chunk_size=chunk_size,
            overlap=overlap,
        )

    def test_two_chunks(self) -> None:
        d = self._make_detector(chunk_size=100, overlap=20)
        chunks = d._compute_chunks(150)
        assert chunks == [(0, 100), (80, 150)]

    def test_three_chunks(self) -> None:
        d = self._make_detector(chunk_size=100, overlap=20)
        chunks = d._compute_chunks(250)
        assert chunks == [(0, 100), (80, 180), (160, 250)]

    def test_no_overlap(self) -> None:
        d = self._make_detector(chunk_size=100, overlap=0)
        chunks = d._compute_chunks(250)
        assert chunks == [(0, 100), (100, 200), (200, 250)]

    def test_last_chunk_shorter(self) -> None:
        d = self._make_detector(chunk_size=100, overlap=20)
        chunks = d._compute_chunks(110)
        # stride=80, so second chunk starts at 80
        assert chunks == [(0, 100), (80, 110)]

    def test_single_chunk_when_text_equals_chunk_size(self) -> None:
        d = self._make_detector(chunk_size=100, overlap=20)
        chunks = d._compute_chunks(100)
        assert chunks == [(0, 100)]

    def test_full_coverage(self) -> None:
        """Every character position is covered by at least one chunk."""
        d = self._make_detector(chunk_size=100, overlap=30)
        text_length = 350
        chunks = d._compute_chunks(text_length)

        covered = set()
        for start, end in chunks:
            covered.update(range(start, end))

        assert covered == set(range(text_length))


# ---------------------------------------------------------------------------
# Offset adjustment
# ---------------------------------------------------------------------------


class TestOffsetAdjustment:
    """Detections from non-first chunks have correct absolute positions."""

    async def test_detection_in_second_chunk(self) -> None:
        # "Patrick" placed so it only appears in the second chunk's territory
        # chunk_size=30, overlap=10, stride=20
        # Chunk 0: [0, 30), Chunk 1: [20, 50)
        text = "." * 35 + "Patrick" + "." * 8  # length = 50
        inner = ExactMatchDetector([("Patrick", "PERSON")])
        chunked = ChunkedDetector(detector=inner, chunk_size=30, overlap=10)

        result = await chunked.detect(text)
        assert len(result) == 1
        assert result[0].text == "Patrick"
        assert result[0].position == Span(35, 42)

    async def test_detection_text_matches_original(self) -> None:
        text = "Hello world, " + "." * 40 + " Patrick is here"
        inner = ExactMatchDetector([("Patrick", "PERSON")])
        chunked = ChunkedDetector(detector=inner, chunk_size=30, overlap=10)

        result = await chunked.detect(text)
        assert len(result) == 1

        d = result[0]
        assert text[d.position.start_pos : d.position.end_pos] == "Patrick"

    async def test_first_chunk_no_shift(self) -> None:
        text = "Patrick " + "." * 50
        inner = ExactMatchDetector([("Patrick", "PERSON")])
        chunked = ChunkedDetector(detector=inner, chunk_size=30, overlap=10)

        result = await chunked.detect(text)
        assert any(d.position == Span(0, 7) and d.text == "Patrick" for d in result)


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


class TestDeduplication:
    """Same entity in overlap region appears once."""

    async def test_entity_in_overlap_deduplicated(self) -> None:
        # Place "Patrick" in the overlap zone so both chunks see it.
        # chunk_size=30, overlap=15, stride=15
        # Chunk 0: [0, 30), Chunk 1: [15, 45)
        # "Patrick" at position 19-26 is in both chunks
        text = "." * 19 + "Patrick " + "." * 18  # length = 45
        inner = ExactMatchDetector([("Patrick", "PERSON")])
        chunked = ChunkedDetector(detector=inner, chunk_size=30, overlap=15)

        result = await chunked.detect(text)
        # Should appear exactly once despite being in the overlap
        patrick_detections = [d for d in result if d.text == "Patrick"]
        assert len(patrick_detections) == 1
        assert patrick_detections[0].position == Span(19, 26)

    async def test_multiple_entities_across_chunks(self) -> None:
        # chunk_size=30, overlap=10, stride=20
        # Place two distinct entities in different chunks
        text = "Patrick " + "." * 32 + " Alice " + "." * 13  # length = 60
        inner = ExactMatchDetector([("Patrick", "PERSON"), ("Alice", "PERSON")])
        chunked = ChunkedDetector(detector=inner, chunk_size=30, overlap=10)

        result = await chunked.detect(text)
        names = {d.text for d in result}
        assert names == {"Patrick", "Alice"}

    async def test_sorted_by_position(self) -> None:
        # Ensure output is sorted by start_pos regardless of detection order
        text = "." * 10 + " Alice " + "." * 8 + " Patrick " + "." * 28
        inner = ExactMatchDetector([("Patrick", "PERSON"), ("Alice", "PERSON")])
        chunked = ChunkedDetector(detector=inner, chunk_size=30, overlap=10)

        result = await chunked.detect(text)
        positions = [d.position.start_pos for d in result]
        assert positions == sorted(positions)


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------


class TestIntegration:
    """End-to-end tests with realistic scenarios."""

    async def test_long_text_with_many_entities(self) -> None:
        # Build a 500-char text with entities spread throughout
        parts = [
            "Patrick habite à Paris. ",  # 24 chars
            "x" * 100,
            " Alice travaille à Lyon. ",  # 25 chars
            "y" * 100,
            " Bob est né à Marseille. ",  # 25 chars
            "z" * 100,
        ]
        text = "".join(parts)

        inner = ExactMatchDetector(
            [
                ("Patrick", "PERSON"),
                ("Paris", "LOCATION"),
                ("Alice", "PERSON"),
                ("Lyon", "LOCATION"),
                ("Bob", "PERSON"),
                ("Marseille", "LOCATION"),
            ]
        )
        chunked = ChunkedDetector(detector=inner, chunk_size=80, overlap=30)

        result = await chunked.detect(text)
        labels = {d.text for d in result}
        assert labels == {"Patrick", "Paris", "Alice", "Lyon", "Bob", "Marseille"}

        # All positions match the original text
        for d in result:
            assert text[d.position.start_pos : d.position.end_pos] == d.text

    async def test_with_zero_overlap(self) -> None:
        # Entities not near boundaries should be detected fine
        text = "Patrick " + "." * 42 + " Alice " + "." * 43  # length = 100
        inner = ExactMatchDetector([("Patrick", "PERSON"), ("Alice", "PERSON")])
        chunked = ChunkedDetector(detector=inner, chunk_size=50, overlap=0)

        result = await chunked.detect(text)
        names = {d.text for d in result}
        assert "Patrick" in names
        assert "Alice" in names

    async def test_confidence_preserved(self) -> None:
        inner = ExactMatchDetector([("Patrick", "PERSON")])
        chunked = ChunkedDetector(detector=inner, chunk_size=20, overlap=5)

        text = "Hello Patrick world!!"  # length = 21, triggers chunking
        result = await chunked.detect(text)
        assert len(result) == 1
        assert result[0].confidence == 1.0
