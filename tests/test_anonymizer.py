"""Tests for ``Anonymizer``."""

import pytest

from piighost.anonymizer import Anonymizer
from piighost.exceptions import DeanonymizationError
from piighost.models import Detection, Entity, Span
from piighost.placeholder import (
    LabelCounterPlaceholderFactory,
    LabelHashPlaceholderFactory,
    LabelPlaceholderFactory,
)


def _det(
    text: str, label: str, start: int, end: int, confidence: float = 0.9
) -> Detection:
    return Detection(
        text=text, label=label, position=Span(start, end), confidence=confidence
    )


# ---------------------------------------------------------------------------
# Anonymize
# ---------------------------------------------------------------------------


class TestAnonymize:
    """anonymize() replaces detections with tokens."""

    def test_single_entity_single_detection(self) -> None:
        entities = [Entity(detections=(_det("Patrick", "PERSON", 0, 7),))]
        result = Anonymizer(LabelCounterPlaceholderFactory()).anonymize(
            "Patrick est gentil",
            entities,
        )
        assert result == "<<PERSON:1>> est gentil"

    def test_single_entity_multiple_detections(self) -> None:
        entities = [
            Entity(
                detections=(
                    _det("Patrick", "PERSON", 0, 7),
                    _det("Patrick", "PERSON", 20, 27),
                )
            )
        ]
        text = "Patrick est gentil. Patrick habite ici."
        result = Anonymizer(LabelCounterPlaceholderFactory()).anonymize(text, entities)
        assert result == "<<PERSON:1>> est gentil. <<PERSON:1>> habite ici."

    def test_multiple_entities(self) -> None:
        entities = [
            Entity(detections=(_det("Patrick", "PERSON", 0, 7),)),
            Entity(detections=(_det("Paris", "LOCATION", 17, 22),)),
        ]
        result = Anonymizer(LabelCounterPlaceholderFactory()).anonymize(
            "Patrick habite à Paris",
            entities,
        )
        assert "<<PERSON:1>>" in result
        assert "<<LOCATION:1>>" in result
        assert "Patrick" not in result
        assert "Paris" not in result

    def test_no_entities_returns_unchanged(self) -> None:
        result = Anonymizer(LabelCounterPlaceholderFactory()).anonymize(
            "Hello world", []
        )
        assert result == "Hello world"

    def test_with_hash_factory(self) -> None:
        entities = [Entity(detections=(_det("Patrick", "PERSON", 0, 7),))]
        result = Anonymizer(LabelHashPlaceholderFactory()).anonymize(
            "Patrick est gentil",
            entities,
        )
        assert result.startswith("<<PERSON:")
        assert "Patrick" not in result

    def test_with_redact_factory(self) -> None:
        entities = [
            Entity(detections=(_det("Patrick", "PERSON", 0, 7),)),
            Entity(detections=(_det("Henri", "PERSON", 11, 16),)),
        ]
        result = Anonymizer(LabelPlaceholderFactory()).anonymize(
            "Patrick et Henri sont amis",
            entities,
        )
        assert result == "<<PERSON>> et <<PERSON>> sont amis"


# ---------------------------------------------------------------------------
# Deanonymize
# ---------------------------------------------------------------------------


class TestDeanonymize:
    """deanonymize() restores the original text."""

    def test_roundtrip_single_entity(self) -> None:
        entities = [Entity(detections=(_det("Patrick", "PERSON", 0, 7),))]
        text = "Patrick est gentil"
        anon = Anonymizer(LabelCounterPlaceholderFactory())
        anonymized = anon.anonymize(text, entities)
        restored = anon.deanonymize(anonymized, entities)
        assert restored == text

    def test_roundtrip_multiple_entities(self) -> None:
        entities = [
            Entity(detections=(_det("Patrick", "PERSON", 0, 7),)),
            Entity(detections=(_det("Paris", "LOCATION", 17, 22),)),
        ]
        text = "Patrick habite à Paris"
        anon = Anonymizer(LabelCounterPlaceholderFactory())
        anonymized = anon.anonymize(text, entities)
        restored = anon.deanonymize(anonymized, entities)
        assert restored == text

    def test_roundtrip_multiple_detections(self) -> None:
        entities = [
            Entity(
                detections=(
                    _det("Patrick", "PERSON", 0, 7),
                    _det("Patrick", "PERSON", 20, 27),
                )
            )
        ]
        text = "Patrick est gentil. Patrick habite ici."
        ph_factory = LabelCounterPlaceholderFactory()
        anon = Anonymizer(ph_factory=ph_factory)
        anonymized = anon.anonymize(text, entities)
        assert anonymized == "<<PERSON:1>> est gentil. <<PERSON:1>> habite ici."

        restored = anon.deanonymize(anonymized, entities)
        assert restored == text

    def test_roundtrip_spelling_variants(self) -> None:
        # Same entity but different spellings both must be restored correctly.
        entities = [
            Entity(
                detections=(
                    _det("Patrick", "PERSON", 0, 7),
                    _det("patric", "PERSON", 20, 26),
                )
            )
        ]
        text = "Patrick est gentil. patric habite ici."
        ph_factory = LabelCounterPlaceholderFactory()
        anon = Anonymizer(ph_factory=ph_factory)

        anonymized = anon.anonymize(text, entities)
        assert anonymized.count("<<PERSON:1>>") == 2

        restored = anon.deanonymize(anonymized, entities)
        assert restored == text

    def test_roundtrip_with_redact(self) -> None:
        entities = [Entity(detections=(_det("Patrick", "PERSON", 0, 7),))]
        text = "Patrick est gentil"
        ph_factory = LabelPlaceholderFactory()
        anon = Anonymizer(ph_factory=ph_factory)

        anonymized = anon.anonymize(text, entities)
        assert anonymized == "<<PERSON>> est gentil"

        restored = anon.deanonymize(anonymized, entities)
        assert restored == text

    def test_roundtrip_redact_multiple_same_label(self) -> None:
        entities = [
            Entity(detections=(_det("Patrick", "PERSON", 0, 7),)),
            Entity(detections=(_det("Henri", "PERSON", 11, 16),)),
        ]
        text = "Patrick et Henri sont amis"
        ph_factory = LabelPlaceholderFactory()
        anon = Anonymizer(ph_factory=ph_factory)
        anonymized = anon.anonymize(text, entities)
        restored = anon.deanonymize(anonymized, entities)
        assert restored == text

    def test_roundtrip_with_hash(self) -> None:
        entities = [Entity(detections=(_det("Patrick", "PERSON", 0, 7),))]
        text = "Patrick est gentil"
        ph_factory = LabelHashPlaceholderFactory()
        anon = Anonymizer(ph_factory=ph_factory)
        anonymized = anon.anonymize(text, entities)
        restored = anon.deanonymize(anonymized, entities)
        assert restored == text

    def test_roundtrip_token_shorter_than_text(self) -> None:
        """Token (<<PER:1>> = 9 chars) shorter than original (Jean Dupont = 11 chars)."""
        text = "Jean Dupont et Bob habitent à Lyon."
        entities = [
            Entity(detections=(_det("Jean Dupont", "PER", 0, 11),)),
            Entity(detections=(_det("Bob", "PER", 15, 18),)),
            Entity(detections=(_det("Lyon", "LOC", 30, 34),)),
        ]
        anon = Anonymizer(LabelCounterPlaceholderFactory())
        anonymized = anon.anonymize(text, entities)
        restored = anon.deanonymize(anonymized, entities)
        assert restored == text

    def test_roundtrip_token_longer_than_text(self) -> None:
        """Token (<<PERSON:1>> = 12 chars) longer than original (Bob = 3 chars)."""
        #        0  3    8    13
        text = "Bob aime Lyon, Bob y vit."
        entities = [
            Entity(
                detections=(
                    _det("Bob", "PERSON", 0, 3),
                    _det("Bob", "PERSON", 15, 18),
                )
            ),
            Entity(detections=(_det("Lyon", "LOCATION", 9, 13),)),
        ]
        anon = Anonymizer(LabelCounterPlaceholderFactory())
        anonymized = anon.anonymize(text, entities)
        restored = anon.deanonymize(anonymized, entities)
        assert restored == text

    def test_roundtrip_token_same_length_as_text(self) -> None:
        """Token and original text have the same length."""
        text = "Charlotte et Marseille sont amis."
        entities = [
            Entity(detections=(_det("Charlotte", "PER", 0, 9),)),
            Entity(detections=(_det("Marseille", "LOC", 13, 22),)),
        ]
        anon = Anonymizer(LabelCounterPlaceholderFactory())
        anonymized = anon.anonymize(text, entities)
        assert len("<<PER:1>>") == len("Charlotte")
        restored = anon.deanonymize(anonymized, entities)
        assert restored == text

    def test_deanonymize_missing_token_raises(self) -> None:
        """DeanonymizationError is raised with partial_text when a token is missing."""
        entities = [
            Entity(detections=(_det("Patrick", "PERSON", 0, 7),)),
            Entity(detections=(_det("Paris", "LOCATION", 17, 22),)),
        ]
        # Text that doesn't contain the expected tokens
        anon = Anonymizer(LabelCounterPlaceholderFactory())
        with pytest.raises(DeanonymizationError) as exc_info:
            anon.deanonymize("texte sans aucun placeholder", entities)
        assert isinstance(exc_info.value.partial_text, str)
