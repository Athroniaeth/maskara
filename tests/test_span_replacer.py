"""Tests for span_replacer uses DI to swap validator in tests."""

import pytest
from typing import Sequence

from piighost.span_replacer import (
    ReplacementResult,
    Span,
    SpanReplacer,
)


# ---------------------------------------------------------------------------
# Fixtures & DI helpers
# ---------------------------------------------------------------------------


class NoOpValidator:
    """A validator that accepts everything (for testing logic in isolation)."""

    def validate(self, text: str, spans: Sequence[Span]) -> None:
        pass


@pytest.fixture()
def replacer() -> SpanReplacer:
    """Default replacer with real validation."""
    return SpanReplacer()


@pytest.fixture()
def lenient_replacer() -> SpanReplacer:
    """Replacer with no-op validator (tests core logic only)."""
    return SpanReplacer(validator=NoOpValidator())


# ---------------------------------------------------------------------------
# User's exact scenario
# ---------------------------------------------------------------------------


class TestUserScenario:
    """The "Bonjour Patrick" example from the spec."""

    TEXT = (
        "Bonjour je m'appelle Patrick, j'ai 25 ans, c'est un beau prénom Patrick non ?"
    )
    SPANS = [
        Span(start=21, end=28, replacement="{name_1}"),
        Span(start=35, end=41, replacement="{age_1}"),
        Span(start=64, end=71, replacement="{name_1}"),
    ]
    EXPECTED = "Bonjour je m'appelle {name_1}, j'ai {age_1}, c'est un beau prénom {name_1} non ?"

    def test_apply_produces_expected_text(self, replacer: SpanReplacer) -> None:
        result = replacer.apply(self.TEXT, self.SPANS)
        assert result.text == self.EXPECTED

    def test_reverse_spans_count(self, replacer: SpanReplacer) -> None:
        result = replacer.apply(self.TEXT, self.SPANS)
        assert len(result.reverse_spans) == len(self.SPANS)

    def test_restore_gives_back_original(self, replacer: SpanReplacer) -> None:
        result = replacer.apply(self.TEXT, self.SPANS)
        assert replacer.restore(result) == self.TEXT

    def test_reverse_spans_extract_replacements(self, replacer: SpanReplacer) -> None:
        result = replacer.apply(self.TEXT, self.SPANS)
        extracted = [s.extract(result.text) for s in result.reverse_spans]
        assert extracted == ["{name_1}", "{age_1}", "{name_1}"]

    def test_reverse_spans_hold_originals(self, replacer: SpanReplacer) -> None:
        result = replacer.apply(self.TEXT, self.SPANS)
        originals = [s.replacement for s in result.reverse_spans]
        assert originals == ["Patrick", "25 ans", "Patrick"]


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


class TestApply:
    def test_single_replacement(self, replacer: SpanReplacer) -> None:
        result = replacer.apply("Hello World", [Span(6, 11, "Python")])
        assert result.text == "Hello Python"

    def test_replacement_shorter(self, replacer: SpanReplacer) -> None:
        result = replacer.apply("abcdef", [Span(2, 5, "X")])
        assert result.text == "abXf"

    def test_replacement_longer(self, replacer: SpanReplacer) -> None:
        result = replacer.apply("abcdef", [Span(2, 3, "XYZ")])
        assert result.text == "abXYZdef"

    def test_empty_spans_list(self, replacer: SpanReplacer) -> None:
        result = replacer.apply("unchanged", [])
        assert result.text == "unchanged"
        assert result.reverse_spans == ()

    def test_unordered_spans_are_sorted(self, replacer: SpanReplacer) -> None:
        spans = [Span(6, 11, "B"), Span(0, 5, "A")]
        result = replacer.apply("Hello World", spans)
        assert result.text == "A B"

    def test_adjacent_spans(self, replacer: SpanReplacer) -> None:
        spans = [Span(0, 3, "XX"), Span(3, 6, "YY")]
        result = replacer.apply("aaabbb", spans)
        assert result.text == "XXYY"


class TestRestore:
    def test_roundtrip_single(self, replacer: SpanReplacer) -> None:
        original = "foo bar baz"
        result = replacer.apply(original, [Span(4, 7, "QUX")])
        assert replacer.restore(result) == original

    def test_roundtrip_multiple(self, replacer: SpanReplacer) -> None:
        original = "aaa bbb ccc"
        spans = [Span(0, 3, "X"), Span(4, 7, "YYYY"), Span(8, 11, "ZZ")]
        result = replacer.apply(original, spans)
        assert replacer.restore(result) == original

    def test_roundtrip_empty(self, replacer: SpanReplacer) -> None:
        original = "nothing"
        result = replacer.apply(original, [])
        assert replacer.restore(result) == original


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_overlapping_raises(self, replacer: SpanReplacer) -> None:
        with pytest.raises(ValueError, match="Overlapping"):
            replacer.apply("abcdef", [Span(1, 4, "X"), Span(3, 5, "Y")])

    def test_out_of_bounds_raises(self, replacer: SpanReplacer) -> None:
        with pytest.raises(ValueError, match="out of bounds"):
            replacer.apply("abc", [Span(0, 10, "X")])

    def test_negative_start_raises(self, replacer: SpanReplacer) -> None:
        with pytest.raises(ValueError, match="out of bounds"):
            replacer.apply("abc", [Span(-1, 2, "X")])

    def test_empty_span_raises(self, replacer: SpanReplacer) -> None:
        with pytest.raises(ValueError, match="empty or reversed"):
            replacer.apply("abc", [Span(2, 2, "X")])

    def test_reversed_span_raises(self, replacer: SpanReplacer) -> None:
        with pytest.raises(ValueError, match="empty or reversed"):
            replacer.apply("abc", [Span(2, 1, "X")])


# ---------------------------------------------------------------------------
# DI: lenient validator skips checks
# ---------------------------------------------------------------------------


class TestDI:
    def test_noop_validator_allows_overlap(
        self, lenient_replacer: SpanReplacer
    ) -> None:
        """With NoOpValidator, overlapping spans don't raise."""
        result = lenient_replacer.apply("abcdef", [Span(1, 4, "X"), Span(3, 5, "Y")])
        assert isinstance(result, ReplacementResult)


# ---------------------------------------------------------------------------
# Span model
# ---------------------------------------------------------------------------


class TestSpanModel:
    def test_length(self) -> None:
        assert Span(3, 10, "x").length == 7

    def test_extract(self) -> None:
        assert Span(0, 5, "x").extract("Hello World") == "Hello"

    def test_frozen(self) -> None:
        span = Span(0, 1, "x")
        with pytest.raises(AttributeError):
            span.start = 5  # type: ignore[misc]
