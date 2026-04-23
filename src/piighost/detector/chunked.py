"""Chunked detector for texts that exceed NER model context windows."""

import asyncio
from dataclasses import dataclass

from piighost.detector.base import AnyDetector
from piighost.models import Detection, Span


@dataclass
class ChunkedDetector:
    """Wrapper that splits long texts into overlapping chunks before detection.

    When a text exceeds ``chunk_size`` characters, it is split into
    overlapping chunks and the inner detector is called on each chunk.
    Detection positions are adjusted back to original-text coordinates
    and deduplicated in overlap regions.

    For texts shorter than or equal to ``chunk_size``, the inner detector
    is called directly with no splitting overhead.

    Args:
        detector: The inner detector to wrap.
        chunk_size: Maximum number of characters per chunk.
        overlap: Number of overlapping characters between consecutive chunks.

    Example:
        >>> from piighost.detector import ExactMatchDetector
        >>> inner = ExactMatchDetector([("Patrick", "PERSON")])
        >>> chunked = ChunkedDetector(detector=inner, chunk_size=50, overlap=10)
        >>> detections = await chunked.detect("long text " * 20)
    """

    detector: AnyDetector
    chunk_size: int = 512
    overlap: int = 128

    def __post_init__(self) -> None:
        if self.chunk_size <= 0:
            raise ValueError(f"chunk_size must be positive, got {self.chunk_size}")
        if self.overlap < 0:
            raise ValueError(f"overlap must be non-negative, got {self.overlap}")
        if self.overlap >= self.chunk_size:
            raise ValueError(
                f"overlap ({self.overlap}) must be less than chunk_size ({self.chunk_size})"
            )

    async def detect(self, text: str) -> list[Detection]:
        """Detect entities, splitting into chunks if text exceeds chunk_size.

        Args:
            text: The input text to analyze for entities.

        Returns:
            A list of ``Detection`` objects with positions relative to
            the original text.
        """
        if len(text) <= self.chunk_size:
            return await self.detector.detect(text)

        chunks = self._compute_chunks(len(text))
        chunk_results = await asyncio.gather(
            *(self.detector.detect(text[start:end]) for start, end in chunks)
        )

        all_detections: list[Detection] = []
        for (chunk_start, _), chunk_detections in zip(chunks, chunk_results):
            all_detections.extend(
                self._shift_detections(chunk_detections, chunk_start, text)
            )

        return self._deduplicate(all_detections)

    def _compute_chunks(self, text_length: int) -> list[tuple[int, int]]:
        """Compute (start, end) offsets for each chunk.

        Uses a sliding window with stride = ``chunk_size - overlap``.

        Args:
            text_length: Total length of the text to split.

        Returns:
            A list of ``(start, end)`` tuples (end is exclusive).
        """
        stride = self.chunk_size - self.overlap
        chunks: list[tuple[int, int]] = []
        start = 0

        while start < text_length:
            end = min(start + self.chunk_size, text_length)
            chunks.append((start, end))
            if end == text_length:
                break
            start += stride

        return chunks

    @staticmethod
    def _shift_detections(
        detections: list[Detection],
        offset: int,
        text: str,
    ) -> list[Detection]:
        """Shift detection positions by the chunk's offset in the original text.

        Args:
            detections: Detections from a single chunk (chunk-local positions).
            offset: The chunk's start position in the original text.
            text: The original full text.

        Returns:
            New ``Detection`` objects with positions in original-text coordinates.
        """
        if offset == 0:
            return detections

        return [
            Detection(
                text=text[d.position.start_pos + offset : d.position.end_pos + offset],
                label=d.label,
                position=Span(
                    start_pos=d.position.start_pos + offset,
                    end_pos=d.position.end_pos + offset,
                ),
                confidence=d.confidence,
            )
            for d in detections
        ]

    @staticmethod
    def _deduplicate(detections: list[Detection]) -> list[Detection]:
        """Remove duplicate detections from overlap regions.

        Groups detections by ``(start_pos, end_pos, label)`` and keeps
        the one with the highest confidence in each group.

        Args:
            detections: All detections from all chunks (already shifted).

        Returns:
            Deduplicated detections sorted by ``start_pos``.
        """
        best: dict[tuple[int, int, str], Detection] = {}

        for d in detections:
            key = (d.position.start_pos, d.position.end_pos, d.label)
            if key not in best or d.confidence > best[key].confidence:
                best[key] = d

        return sorted(best.values(), key=lambda d: d.position.start_pos)
