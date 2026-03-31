"""Tests for SpacyDetector using mock spaCy models."""

from __future__ import annotations

from dataclasses import dataclass

import pytest


# ---------------------------------------------------------------------------
# Lightweight fakes that mimic spaCy's Doc / Span / Language interfaces
# so we don't need spaCy installed to run these tests.
# ---------------------------------------------------------------------------


@dataclass
class FakeSpan:
    text: str
    label_: str
    start_char: int
    end_char: int


@dataclass
class FakeDoc:
    ents: tuple[FakeSpan, ...]


class FakeLanguage:
    """Mimics ``spacy.language.Language.__call__``."""

    def __init__(self, entities: list[FakeSpan]) -> None:
        self._entities = tuple(entities)

    def __call__(self, text: str) -> FakeDoc:
        return FakeDoc(ents=self._entities)


# ---------------------------------------------------------------------------
# Import helper – patches importlib so the guard in spacy.py passes even
# when spaCy is not installed.
# ---------------------------------------------------------------------------


@pytest.fixture
def _patch_spacy(monkeypatch):
    """Make ``importlib.util.find_spec("spacy")`` return a truthy value
    and inject a fake ``spacy`` module so the detector can be imported."""
    import types

    fake_spacy = types.ModuleType("spacy")
    fake_language = types.ModuleType("spacy.language")
    fake_language.Language = FakeLanguage  # type: ignore[attr-defined]
    fake_spacy.language = fake_language  # type: ignore[attr-defined]

    import sys

    monkeypatch.setitem(sys.modules, "spacy", fake_spacy)
    monkeypatch.setitem(sys.modules, "spacy.language", fake_language)

    original = __import__("importlib.util").util.find_spec

    def patched_find_spec(name, *args, **kwargs):
        if name == "spacy":
            return True  # truthy sentinel
        return original(name, *args, **kwargs)

    monkeypatch.setattr("importlib.util.find_spec", patched_find_spec)


def _get_detector_class():
    """Import SpacyDetector (must be called inside a test with _patch_spacy)."""
    import importlib
    import sys

    # Remove cached module so re-import picks up the patched spacy
    sys.modules.pop("piighost.detector.spacy", None)
    mod = importlib.import_module("piighost.detector.spacy")
    return mod.SpacyDetector


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBasicMatching:
    @pytest.mark.asyncio
    async def test_single_entity(self, _patch_spacy):
        SpacyDetector = _get_detector_class()
        model = FakeLanguage([FakeSpan("Patrick", "PER", 0, 7)])
        detector = SpacyDetector(model=model)

        detections = await detector.detect("Patrick habite à Paris")
        assert len(detections) == 1
        assert detections[0].text == "Patrick"
        assert detections[0].label == "PER"

    @pytest.mark.asyncio
    async def test_multiple_entities(self, _patch_spacy):
        SpacyDetector = _get_detector_class()
        model = FakeLanguage(
            [
                FakeSpan("Patrick", "PER", 0, 7),
                FakeSpan("Paris", "LOC", 18, 23),
            ]
        )
        detector = SpacyDetector(model=model)

        detections = await detector.detect("Patrick habite à Paris")
        assert len(detections) == 2

    @pytest.mark.asyncio
    async def test_no_entities(self, _patch_spacy):
        SpacyDetector = _get_detector_class()
        model = FakeLanguage([])
        detector = SpacyDetector(model=model)

        detections = await detector.detect("Bonjour le monde")
        assert detections == []

    @pytest.mark.asyncio
    async def test_empty_text(self, _patch_spacy):
        SpacyDetector = _get_detector_class()
        model = FakeLanguage([])
        detector = SpacyDetector(model=model)

        detections = await detector.detect("")
        assert detections == []


class TestLabelFiltering:
    @pytest.mark.asyncio
    async def test_filters_by_label(self, _patch_spacy):
        SpacyDetector = _get_detector_class()
        model = FakeLanguage(
            [
                FakeSpan("Patrick", "PER", 0, 7),
                FakeSpan("Paris", "LOC", 18, 23),
            ]
        )
        detector = SpacyDetector(model=model, labels=["PER"])

        detections = await detector.detect("Patrick habite à Paris")
        assert len(detections) == 1
        assert detections[0].label == "PER"

    @pytest.mark.asyncio
    async def test_no_label_filter_keeps_all(self, _patch_spacy):
        SpacyDetector = _get_detector_class()
        model = FakeLanguage(
            [
                FakeSpan("Patrick", "PER", 0, 7),
                FakeSpan("Paris", "LOC", 18, 23),
            ]
        )
        detector = SpacyDetector(model=model, labels=None)

        detections = await detector.detect("Patrick habite à Paris")
        assert len(detections) == 2


class TestDetectionAttributes:
    @pytest.mark.asyncio
    async def test_confidence_is_one(self, _patch_spacy):
        SpacyDetector = _get_detector_class()
        model = FakeLanguage([FakeSpan("Patrick", "PER", 0, 7)])
        detector = SpacyDetector(model=model)

        detections = await detector.detect("Patrick")
        assert detections[0].confidence == 1.0

    @pytest.mark.asyncio
    async def test_positions_are_correct(self, _patch_spacy):
        SpacyDetector = _get_detector_class()
        model = FakeLanguage([FakeSpan("Paris", "LOC", 18, 23)])
        detector = SpacyDetector(model=model)

        detections = await detector.detect("Patrick habite à Paris")
        assert detections[0].position.start_pos == 18
        assert detections[0].position.end_pos == 23
