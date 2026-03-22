"""Immutable data models for span-based text replacement."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Span:
    """A text slice defined by indices, paired with its replacement string.

    Attributes:
        start: Inclusive start index in the source text.
        end: Exclusive end index in the source text.
        replacement: The string that will replace ``text[start:end]``.
    """

    start: int
    end: int
    replacement: str

    @property
    def length(self) -> int:
        """Length of the original slice (end - start)."""
        return self.end - self.start

    def extract(self, text: str) -> str:
        """Return the substring this span covers in *text*.

        Args:
            text: The source string to slice.

        Returns:
            The substring ``text[start:end]``.
        """
        return text[self.start : self.end]


@dataclass(frozen=True)
class ReplacementResult:
    """Output of a replacement pass: the new text and spans to undo it.

    Attributes:
        text: The text after all replacements have been applied.
        reverse_spans: Spans that, when applied to *text*, restore the
            original string.
    """

    text: str
    reverse_spans: tuple[Span, ...]
