"""Validation logic for spans, separated behind a Protocol for DI."""

from __future__ import annotations

from typing import Protocol, Sequence

from span_replacer.models import Span


class SpanValidator(Protocol):
    """Interface for span validation (dependency-injection point)."""

    def validate(self, text: str, spans: Sequence[Span]) -> None:
        """Raise ``ValueError`` if *spans* are invalid for *text*.

        Args:
            text: The source string the spans refer to.
            spans: Spans to validate (any order).

        Raises:
            ValueError: On out-of-bounds, empty, or overlapping spans.
        """
        ...  # pragma: no cover


class DefaultSpanValidator:
    """Production validator: bounds check, non-empty, no overlaps."""

    def validate(self, text: str, spans: Sequence[Span]) -> None:
        """Validate that every span is in bounds, non-empty, and non-overlapping.

        Args:
            text: The source string the spans refer to.
            spans: Spans to validate (any order).

        Raises:
            ValueError: On out-of-bounds, empty, or overlapping spans.
        """
        for span in spans:
            self._check_bounds(span, len(text))

        # Get list spans ordered by span_start
        sorted_spans = sorted(spans, key=lambda s: s.start)

        # Check if have any incoherence between consecutive spans (overlaps)
        for prev, curr in zip(sorted_spans, sorted_spans[1:]):
            if curr.start < prev.end:
                raise ValueError(
                    f"Overlapping spans: {prev} and {curr}"
                )

    @staticmethod
    def _check_bounds(span: Span, text_length: int) -> None:
        """Raise if a single span is out of bounds or empty.

        Args:
            span: The span to check.
            text_length: Length of the source text.

        Raises:
            ValueError: If indices are negative, reversed, or exceed text length.
        """
        if span.start < 0 or span.end > text_length:
            raise ValueError(
                f"Span {span} out of bounds for text of length {text_length}"
            )
        if span.start >= span.end:
            raise ValueError(
                f"Span {span} is empty or reversed (start >= end)"
            )
