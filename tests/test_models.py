"""Tests for :mod:`piighost.models`, focused on PII-safe representations."""

from __future__ import annotations

from piighost.models import Detection, Entity, Span


class TestDetectionRepr:
    """Detection.__repr__ must never leak the raw PII surface form."""

    def _make(self, text: str = "Patrick Durand") -> Detection:
        return Detection(
            text=text,
            label="PERSON",
            position=Span(start_pos=0, end_pos=len(text)),
            confidence=0.99,
        )

    def test_repr_does_not_contain_raw_text(self) -> None:
        detection = self._make("Patrick Durand")
        rendered = repr(detection)
        assert "Patrick" not in rendered
        assert "Durand" not in rendered

    def test_repr_reports_length_only(self) -> None:
        detection = self._make("Patrick")
        assert "<redacted:7>" in repr(detection)

    def test_str_also_masks(self) -> None:
        # str() falls back to __repr__ on dataclasses by default.
        detection = self._make("sensitive@example.com")
        assert "sensitive" not in str(detection)
        assert "example.com" not in str(detection)

    def test_format_string_masks(self) -> None:
        detection = self._make("Paris")
        assert "Paris" not in f"{detection}"
        assert "Paris" not in f"{detection!r}"

    def test_repr_preserves_safe_metadata(self) -> None:
        detection = self._make("Patrick")
        rendered = repr(detection)
        assert "'PERSON'" in rendered
        assert "0.99" in rendered
        assert "Span(start_pos=0, end_pos=7)" in rendered

    def test_raw_text_still_accessible_via_attribute(self) -> None:
        detection = self._make("Patrick")
        assert detection.text == "Patrick"

    def test_hash_still_uses_raw_text(self) -> None:
        # hash property relies on the raw text; it is an internal identifier,
        # not user-facing output, and must not be affected by the repr mask.
        detection = self._make("Patrick")
        assert detection.hash.startswith("Patrick:PERSON:")


class TestEntityRepr:
    """Entity must inherit masking from its nested Detections."""

    def test_entity_repr_does_not_leak_nested_text(self) -> None:
        detection = Detection(
            text="Patrick",
            label="PERSON",
            position=Span(0, 7),
            confidence=1.0,
        )
        entity = Entity(detections=(detection,))
        rendered = repr(entity)
        assert "Patrick" not in rendered
        assert "<redacted:7>" in rendered

    def test_entity_with_multiple_detections_masks_all(self) -> None:
        entity = Entity(
            detections=(
                Detection(
                    text="Patrick", label="PERSON", position=Span(0, 7), confidence=0.9
                ),
                Detection(
                    text="Patrice",
                    label="PERSON",
                    position=Span(20, 27),
                    confidence=0.8,
                ),
            )
        )
        rendered = repr(entity)
        assert "Patrick" not in rendered
        assert "Patrice" not in rendered
        assert rendered.count("<redacted:7>") == 2


class TestSpanRepr:
    """Span contains only positional metadata, not PII; repr stays verbose."""

    def test_span_repr_shows_positions(self) -> None:
        span = Span(start_pos=5, end_pos=12)
        assert repr(span) == "Span(start_pos=5, end_pos=12)"
