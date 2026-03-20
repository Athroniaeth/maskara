"""Tests for the anonymization pipeline.

Uses a fake detector to avoid loading a real GLiNER model in CI.
"""

from typing import Sequence


from maskara.anonymizer.anonymizer import Anonymizer
from maskara.anonymizer.models import Entity
from maskara.anonymizer.occurrence import RegexOccurrenceFinder
from maskara.anonymizer.placeholder import CounterPlaceholderFactory


# ---------------------------------------------------------------------------
# Fakes / stubs
# ---------------------------------------------------------------------------


class FakeDetector:
    """Deterministic detector that returns pre-configured entities.

    Args:
        entities: The entities to return for every call to ``detect``.
    """

    def __init__(self, entities: list[Entity]) -> None:
        self._entities = entities

    def detect(self, text: str, labels: Sequence[str]) -> list[Entity]:
        """Return pre-configured entities regardless of input."""
        return self._entities


# ---------------------------------------------------------------------------
# OccurrenceFinder
# ---------------------------------------------------------------------------


class TestRegexOccurrenceFinder:
    """Unit tests for ``RegexOccurrenceFinder``."""

    def test_finds_exact_word_boundary_match(self) -> None:
        finder = RegexOccurrenceFinder()
        result = finder.find_all("Bonjour Patrick, comment va Patrick ?", "Patrick")
        assert result == [(8, 15), (28, 35)]

    def test_ignores_partial_match_inside_word(self) -> None:
        finder = RegexOccurrenceFinder()
        result = finder.find_all("Salut Patrick, APatrick ne compte pas", "Patrick")
        assert result == [(6, 13)]

    def test_case_insensitive_by_default(self) -> None:
        finder = RegexOccurrenceFinder()
        result = finder.find_all("paris et PARIS", "Paris")
        assert len(result) == 2

    def test_no_match_returns_empty(self) -> None:
        finder = RegexOccurrenceFinder()
        assert finder.find_all("Rien à voir", "Patrick") == []


# ---------------------------------------------------------------------------
# CounterPlaceholderFactory
# ---------------------------------------------------------------------------


class TestCounterPlaceholderFactory:
    """Unit tests for ``CounterPlaceholderFactory``."""

    def test_increments_per_label(self) -> None:
        factory = CounterPlaceholderFactory()
        p1 = factory.get_or_create("Patrick", "PERSON")
        p2 = factory.get_or_create("Marie", "PERSON")
        assert p1.replacement == "<<PERSON_1>>"
        assert p2.replacement == "<<PERSON_2>>"

    def test_same_pair_returns_cached(self) -> None:
        factory = CounterPlaceholderFactory()
        p1 = factory.get_or_create("Paris", "LOCATION")
        p2 = factory.get_or_create("Paris", "LOCATION")
        assert p1 is p2

    def test_different_labels_get_own_counter(self) -> None:
        factory = CounterPlaceholderFactory()
        p1 = factory.get_or_create("Patrick", "PERSON")
        p2 = factory.get_or_create("Paris", "LOCATION")
        assert p1.replacement == "<<PERSON_1>>"
        assert p2.replacement == "<<LOCATION_1>>"

    def test_reset_clears_state(self) -> None:
        factory = CounterPlaceholderFactory()
        factory.get_or_create("Patrick", "PERSON")
        factory.reset()
        p = factory.get_or_create("Marie", "PERSON")
        assert p.replacement == "<<PERSON_1>>"


# ---------------------------------------------------------------------------
# Anonymizer (integration with fakes)
# ---------------------------------------------------------------------------


class TestAnonymizer:
    """Integration tests for the full anonymization pipeline."""

    def test_single_entity_single_occurrence(self) -> None:
        detector = FakeDetector(
            [
                Entity(text="Patrick", label="PERSON", start=10, end=17, score=0.95),
            ]
        )
        anonymizer = Anonymizer(detector=detector)

        result = anonymizer.anonymize(
            "Bonjour, Patrick !",
            labels=["PERSON"],
        )

        assert "Patrick" not in result.anonymized_text
        assert "<<PERSON_1>>" in result.anonymized_text
        assert len(result.placeholders) == 1

    def test_expands_to_all_occurrences(self) -> None:
        # NER only finds the first "Patrick" but the pipeline should
        # replace *both*.
        detector = FakeDetector(
            [
                Entity(text="Patrick", label="PERSON", start=0, end=7, score=0.9),
            ]
        )
        anonymizer = Anonymizer(detector=detector)
        text = "Patrick est gentil. Patrick habite ici."

        result = anonymizer.anonymize(text, labels=["PERSON"])

        assert result.anonymized_text.count("<<PERSON_1>>") == 2
        assert "Patrick" not in result.anonymized_text

    def test_multiple_entity_types(self) -> None:
        detector = FakeDetector(
            [
                Entity(text="Patrick", label="PERSON", start=0, end=7, score=0.9),
                Entity(text="Paris", label="LOCATION", start=18, end=23, score=0.85),
            ]
        )
        anonymizer = Anonymizer(detector=detector)
        text = "Patrick habite à Paris."

        result = anonymizer.anonymize(text, labels=["PERSON", "LOCATION"])

        assert "<<PERSON_1>>" in result.anonymized_text
        assert "<<LOCATION_1>>" in result.anonymized_text
        assert "Patrick" not in result.anonymized_text
        assert "Paris" not in result.anonymized_text

    def test_deanonymize_restores_original(self) -> None:
        detector = FakeDetector(
            [
                Entity(text="Patrick", label="PERSON", start=0, end=7, score=0.9),
                Entity(text="Paris", label="LOCATION", start=18, end=23, score=0.85),
            ]
        )
        anonymizer = Anonymizer(detector=detector)
        text = "Patrick habite à Paris."

        result = anonymizer.anonymize(text, labels=["PERSON", "LOCATION"])
        restored = anonymizer.deanonymize(result)

        assert restored == text

    def test_deanonymize_with_expanded_occurrences(self) -> None:
        detector = FakeDetector(
            [
                Entity(text="Patrick", label="PERSON", start=0, end=7, score=0.9),
            ]
        )
        anonymizer = Anonymizer(detector=detector)
        text = "Patrick aime Patrick."

        result = anonymizer.anonymize(text, labels=["PERSON"])
        restored = anonymizer.deanonymize(result)

        assert restored == text

    def test_no_entities_returns_original(self) -> None:
        detector = FakeDetector([])
        anonymizer = Anonymizer(detector=detector)
        text = "Rien de spécial ici."

        result = anonymizer.anonymize(text, labels=["PERSON"])

        assert result.anonymized_text == text
        assert result.placeholders == ()

    def test_partial_word_not_replaced(self) -> None:
        # "APatrick" should NOT be touched.
        detector = FakeDetector(
            [
                Entity(text="Patrick", label="PERSON", start=6, end=13, score=0.9),
            ]
        )
        anonymizer = Anonymizer(detector=detector)
        text = "Salut Patrick, APatrick ne compte pas."

        result = anonymizer.anonymize(text, labels=["PERSON"])

        assert "APatrick" in result.anonymized_text
        assert result.anonymized_text.count("<<PERSON_1>>") == 1
