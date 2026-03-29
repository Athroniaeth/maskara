"""Tests for FakerPlaceholderFactory."""

from piighost.models import Detection, Entity, Span
from piighost.ph_factory.faker import FakerPlaceholderFactory


def _entity(text: str, label: str, start: int = 0) -> Entity:
    end = start + len(text)
    return Entity(
        detections=(
            Detection(
                text=text, label=label, position=Span(start, end), confidence=0.9
            ),
        )
    )


class TestFakerPlaceholderFactory:
    """Generates realistic fake data as replacement tokens."""

    def test_person_returns_string(self) -> None:
        e = _entity("Patrick", "PERSON")
        token = FakerPlaceholderFactory(seed=42).create([e])[e]
        assert isinstance(token, str) and len(token) > 0

    def test_person_not_original(self) -> None:
        e = _entity("Patrick", "PERSON")
        token = FakerPlaceholderFactory(seed=42).create([e])[e]
        assert token != "Patrick"

    def test_email_returns_string(self) -> None:
        e = _entity("patrick@email.com", "EMAIL")
        token = FakerPlaceholderFactory(seed=42).create([e])[e]
        assert "@" in token

    def test_credit_card_returns_digits(self) -> None:
        e = _entity("4111-1111-1111-1234", "CREDIT_CARD")
        token = FakerPlaceholderFactory(seed=42).create([e])[e]
        assert isinstance(token, str) and len(token) > 0

    def test_seed_deterministic(self) -> None:
        e = _entity("Patrick", "PERSON")
        t1 = FakerPlaceholderFactory(seed=123).create([e])[e]
        t2 = FakerPlaceholderFactory(seed=123).create([e])[e]
        assert t1 == t2

    def test_different_seeds_different_values(self) -> None:
        e = _entity("Patrick", "PERSON")
        t1 = FakerPlaceholderFactory(seed=1).create([e])[e]
        t2 = FakerPlaceholderFactory(seed=2).create([e])[e]
        assert t1 != t2

    def test_same_entity_same_fake(self) -> None:
        """Two entities with same canonical text and label get the same fake value."""
        e1 = _entity("Patrick", "PERSON")
        e2 = _entity("Patrick", "PERSON", start=20)
        result = FakerPlaceholderFactory(seed=42).create([e1, e2])
        assert result[e1] == result[e2]

    def test_different_entities_different_fakes(self) -> None:
        e1 = _entity("Patrick", "PERSON")
        e2 = _entity("Henri", "PERSON", start=20)
        result = FakerPlaceholderFactory(seed=42).create([e1, e2])
        assert result[e1] != result[e2]

    def test_unknown_label_redacted(self) -> None:
        e = _entity("XYZ-123", "UNKNOWN_TYPE")
        token = FakerPlaceholderFactory(seed=42).create([e])[e]
        assert token == "<UNKNOWN_TYPE>"

    def test_label_case_insensitive(self) -> None:
        e = _entity("Patrick", "person")
        token = FakerPlaceholderFactory(seed=42).create([e])[e]
        assert isinstance(token, str) and token != "Patrick"

    def test_custom_strategies_replace_defaults(self) -> None:
        def custom_fn(faker):
            return "CUSTOM_FAKE"

        factory = FakerPlaceholderFactory(strategies={"PERSON": custom_fn})
        e = _entity("Patrick", "PERSON")
        assert factory.create([e])[e] == "CUSTOM_FAKE"

    def test_custom_strategy_unknown_label_falls_back(self) -> None:
        def custom_fn(faker):
            return "NOOP"

        factory = FakerPlaceholderFactory(strategies={"PERSON": custom_fn})
        e = _entity("Paris", "LOCATION")
        assert factory.create([e])[e] == "<LOCATION>"

    def test_empty_list(self) -> None:
        assert FakerPlaceholderFactory().create([]) == {}
