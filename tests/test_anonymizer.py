"""Tests for the anonymization pipeline.

Uses a fake detector to avoid loading a real GLiNER model in CI.
"""

from typing import Sequence


from piighost.anonymizer.anonymizer import Anonymizer
from piighost.anonymizer.detector import CompositeDetector, RegexDetector
from piighost.anonymizer.models import Entity
from piighost.anonymizer.occurrence import RegexOccurrenceFinder
from piighost.anonymizer.placeholder import (
    CounterPlaceholderFactory,
    HashPlaceholderFactory,
)


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

    def detect(
        self, text: str, active_labels: Sequence[str] | None = None
    ) -> list[Entity]:
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
# HashPlaceholderFactory
# ---------------------------------------------------------------------------


class TestHashPlaceholderFactory:
    """Unit tests for ``HashPlaceholderFactory``."""

    def test_format(self) -> None:
        factory = HashPlaceholderFactory()
        p = factory.get_or_create("Patrick", "PERSON")
        assert p.replacement.startswith("<PERSON:")
        assert p.replacement.endswith(">")
        # "<PERSON:" (8) + 8 hex chars + ">" (1) = 17
        assert len(p.replacement) == 8 + 8 + 1

    def test_deterministic(self) -> None:
        factory = HashPlaceholderFactory()
        p1 = factory.get_or_create("Patrick", "PERSON")
        p2 = factory.get_or_create("Patrick", "PERSON")
        assert p1 is p2

    def test_different_originals_different_hash(self) -> None:
        factory = HashPlaceholderFactory()
        p1 = factory.get_or_create("Patrick", "PERSON")
        p2 = factory.get_or_create("Marie", "PERSON")
        assert p1.replacement != p2.replacement

    def test_same_text_different_label_different_replacement(self) -> None:
        factory = HashPlaceholderFactory()
        p1 = factory.get_or_create("Paris", "PERSON")
        p2 = factory.get_or_create("Paris", "LOCATION")
        assert p1.replacement != p2.replacement

    def test_reset_clears_cache(self) -> None:
        factory = HashPlaceholderFactory()
        p1 = factory.get_or_create("Patrick", "PERSON")
        factory.reset()
        p2 = factory.get_or_create("Patrick", "PERSON")
        assert p1 is not p2
        assert p1.replacement == p2.replacement  # same hash, different object

    def test_custom_digest_length(self) -> None:
        factory = HashPlaceholderFactory(digest_length=16)
        p = factory.get_or_create("Patrick", "PERSON")
        digest_part = p.replacement.split(":")[1].rstrip(">")
        assert len(digest_part) == 16

    def test_custom_template(self) -> None:
        factory = HashPlaceholderFactory(template="[[{label}:{digest}]]")
        p = factory.get_or_create("Patrick", "PERSON")
        assert p.replacement.startswith("[[PERSON:")
        assert p.replacement.endswith("]]")


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
            active_labels=["PERSON"],
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

        result = anonymizer.anonymize(text, active_labels=["PERSON"])

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

        result = anonymizer.anonymize(text, active_labels=["PERSON", "LOCATION"])

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

        result = anonymizer.anonymize(text, active_labels=["PERSON", "LOCATION"])
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

        result = anonymizer.anonymize(text, active_labels=["PERSON"])
        restored = anonymizer.deanonymize(result)

        assert restored == text

    def test_no_entities_returns_original(self) -> None:
        detector = FakeDetector([])
        anonymizer = Anonymizer(detector=detector)
        text = "Rien de spécial ici."

        result = anonymizer.anonymize(text, active_labels=["PERSON"])

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

        result = anonymizer.anonymize(text, active_labels=["PERSON"])

        assert "APatrick" in result.anonymized_text
        assert result.anonymized_text.count("<<PERSON_1>>") == 1


# ---------------------------------------------------------------------------
# RegexDetector
# ---------------------------------------------------------------------------


class TestRegexDetector:
    """Unit tests for ``RegexDetector``."""

    OPENAI_PATTERN = r"sk-(?:proj-)?[A-Za-z0-9\-_]{20,}"

    def test_detects_matching_pattern(self) -> None:
        detector = RegexDetector(patterns={"OPENAI_API_KEY": self.OPENAI_PATTERN})
        key = "sk-proj-abc123xyz456789ABCDEF"
        entities = detector.detect(f"My key is {key}")
        assert len(entities) == 1
        assert entities[0].text == key
        assert entities[0].label == "OPENAI_API_KEY"
        assert entities[0].score == 1.0

    def test_returns_correct_span(self) -> None:
        detector = RegexDetector(patterns={"OPENAI_API_KEY": self.OPENAI_PATTERN})
        text = "key: sk-abc123xyz456789ABCDEF end"
        entities = detector.detect(text)
        assert len(entities) == 1
        start, end = entities[0].start, entities[0].end
        assert text[start:end] == entities[0].text

    def test_active_labels_filter_excludes_unconfigured(self) -> None:
        detector = RegexDetector(patterns={"OPENAI_API_KEY": self.OPENAI_PATTERN})
        entities = detector.detect(
            "sk-proj-abc123xyz456789ABCDEF", active_labels=["PERSON"]
        )
        assert entities == []

    def test_no_filter_runs_all_configured_patterns(self) -> None:
        detector = RegexDetector(
            patterns={
                "OPENAI_API_KEY": self.OPENAI_PATTERN,
                "EMAIL": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            }
        )
        text = "key=sk-abc123xyz456789ABCDEF mail=user@example.com"
        entities = detector.detect(text)  # no filter both patterns run
        labels = {e.label for e in entities}
        assert labels == {"OPENAI_API_KEY", "EMAIL"}

    def test_multiple_matches_in_text(self) -> None:
        detector = RegexDetector(patterns={"OPENAI_API_KEY": self.OPENAI_PATTERN})
        text = "k1=sk-abc123xyz456789ABCDEF k2=sk-proj-zyxwvu987654321fedcba"
        entities = detector.detect(text)
        assert len(entities) == 2

    def test_no_match_returns_empty(self) -> None:
        detector = RegexDetector(patterns={"OPENAI_API_KEY": self.OPENAI_PATTERN})
        entities = detector.detect("no key here")
        assert entities == []

    def test_integration_with_anonymizer_no_filter(self) -> None:
        detector = RegexDetector(patterns={"OPENAI_API_KEY": self.OPENAI_PATTERN})
        anonymizer = Anonymizer(detector=detector)
        text = "My API key is sk-proj-secretkey1234567890abcdef here."
        result = anonymizer.anonymize(text)  # labels configured at init
        assert "sk-proj-secretkey1234567890abcdef" not in result.anonymized_text
        assert "<<OPENAI_API_KEY_1>>" in result.anonymized_text


# ---------------------------------------------------------------------------
# CompositeDetector
# ---------------------------------------------------------------------------


class TestCompositeDetector:
    """Unit tests for ``CompositeDetector``."""

    def test_merges_results_from_all_detectors(self) -> None:
        person_entity = Entity(
            text="Patrick", label="PERSON", start=0, end=7, score=0.9
        )
        key_entity = Entity(
            text="sk-abc123", label="OPENAI_API_KEY", start=10, end=19, score=1.0
        )
        composite = CompositeDetector(
            detectors=[
                FakeDetector([person_entity]),
                FakeDetector([key_entity]),
            ]
        )
        entities = composite.detect("Patrick - sk-abc123")
        assert person_entity in entities
        assert key_entity in entities

    def test_empty_detectors_returns_empty(self) -> None:
        composite = CompositeDetector(detectors=[])
        assert composite.detect("some text") == []

    def test_active_labels_filter_forwarded_to_children(self) -> None:
        regex_detector = RegexDetector(
            patterns={"OPENAI_API_KEY": r"sk-[A-Za-z0-9\-_]{20,}"}
        )
        composite = CompositeDetector(detectors=[regex_detector])
        # Filter excludes OPENAI_API_KEY regex_detector should skip it
        entities = composite.detect("sk-abc123xyz456789ABCDE", active_labels=["PERSON"])
        assert entities == []

    def test_integration_gliner_and_regex_no_filter(self) -> None:
        person_entity = Entity(
            text="Patrick", label="PERSON", start=0, end=7, score=0.9
        )
        composite = CompositeDetector(
            detectors=[
                FakeDetector([person_entity]),
                RegexDetector(
                    patterns={"OPENAI_API_KEY": r"sk-(?:proj-)?[A-Za-z0-9\-_]{20,}"}
                ),
            ]
        )
        anonymizer = Anonymizer(detector=composite)
        text = "Patrick a utilisé la clé sk-proj-mysecretkey12345678abcd"
        result = anonymizer.anonymize(
            text
        )  # no filter each detector uses its own labels
        assert "Patrick" not in result.anonymized_text
        assert "sk-proj-mysecretkey12345678abcd" not in result.anonymized_text
        assert "<<PERSON_1>>" in result.anonymized_text
        assert "<<OPENAI_API_KEY_1>>" in result.anonymized_text
