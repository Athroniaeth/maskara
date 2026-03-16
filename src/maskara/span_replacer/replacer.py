"""Core replacement engine: apply spans forward, restore backward."""

from __future__ import annotations

from typing import Sequence

from span_replacer.models import ReplacementResult, Span
from span_replacer.validator import DefaultSpanValidator, SpanValidator


class SpanReplacer:
    """Apply span-based replacements on a text and compute reverse mappings.

    Args:
        validator: Strategy used to validate spans before applying them.
            Defaults to ``DefaultSpanValidator`` when *None*.

    Example:
        >>> replacer = SpanReplacer()
        >>> result = replacer.apply("Hello World", [Span(6, 11, "Python")])
        >>> result.text
        'Hello Python'
        >>> replacer.restore(result)
        'Hello World'
    """

    def __init__(self, validator: SpanValidator | None = None) -> None:
        self._validator: SpanValidator = validator or DefaultSpanValidator()

    def apply(self, text: str, spans: Sequence[Span]) -> ReplacementResult:
        """Replace every span in *text* and return reverse mappings.

        Spans are processed left-to-right. Each reverse span records the
        position of the replacement **in the new text** together with the
        original fragment, so that ``restore`` can undo the operation.

        Args:
            text: The source string.
            spans: Non-overlapping spans to apply (any order).

        Returns:
            A ``ReplacementResult`` holding the transformed text and the
            reverse spans needed to get back to the original.

        Raises:
            ValueError: Propagated from the validator on bad spans.
        """
        # Check that span are valid for text
        self._validator.validate(text, spans)

        # Get list spans ordered by span start
        sorted_spans = sorted(spans, key=lambda s: s.start)
        reverse_spans: list[Span] = []
        result_text = text
        offset = 0

        for span in sorted_spans:
            # Get original text who will be replaced by span text
            adj_start = span.start + offset
            adj_end = span.end + offset
            original_fragment = result_text[adj_start:adj_end]

            # Replace original text by span text
            result_text = (
                result_text[:adj_start]
                + span.replacement
                + result_text[adj_end:]
            )

            # We know the beginning of the span; now we need the end (after modification)
            rev_end = adj_start + len(span.replacement)
            rev_span = Span(start=adj_start, end=rev_end, replacement=original_fragment)
            reverse_spans.append(rev_span)

            # Calculate the offset between the coordinates of the span (the original text)
            # and the new coordinates (after replacing the original text with the text in the span)
            offset += len(span.replacement) - span.length

        return ReplacementResult(
            text=result_text,
            reverse_spans=tuple(reverse_spans),
        )

    def restore(self, result: ReplacementResult) -> str:
        """Undo a previous ``apply`` by re-applying the reverse spans.

        Args:
            result: The ``ReplacementResult`` returned by ``apply``.

        Returns:
            The original text before replacement.
        """
        return self.apply(result.text, result.reverse_spans).text
