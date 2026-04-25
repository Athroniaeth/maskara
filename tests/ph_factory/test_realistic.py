"""Tests for RealisticHashPlaceholderFactory."""

import pytest

from piighost.models import Detection, Entity, Span
from piighost.ph_factory.realistic import (
    RealisticHashPlaceholderFactory,
    hashed_email,
    hashed_template,
    hashed_with_prefix,
)


def _entity(text: str, label: str, start: int = 0) -> Entity:
    end = start + len(text)
    return Entity(
        detections=(
            Detection(
                text=text, label=label, position=Span(start, end), confidence=0.9
            ),
        )
    )


# ---------------------------------------------------------------------------
# Helper strategies
# ---------------------------------------------------------------------------


class TestHashedHelpers:
    """The pre-built strategy helpers behave as documented."""

    def test_hashed_email_default_domain(self) -> None:
        assert hashed_email()("a1b2c3d4") == "a1b2c3d4@anonymized.local"

    def test_hashed_email_custom_domain(self) -> None:
        assert hashed_email("example.com")("deadbeef") == "deadbeef@example.com"

    def test_hashed_with_prefix(self) -> None:
        assert hashed_with_prefix("Patient")("a1b2c3d4") == "Patient_a1b2c3d4"

    def test_hashed_template(self) -> None:
        fn = hashed_template("user-{hash}@example.com")
        assert fn("abcd1234") == "user-abcd1234@example.com"


# ---------------------------------------------------------------------------
# RealisticHashPlaceholderFactory
# ---------------------------------------------------------------------------


class TestRealisticHashPlaceholderFactory:
    """Strategies-based realistic hashed placeholders, no fallback."""

    def test_email_strategy(self) -> None:
        factory = RealisticHashPlaceholderFactory(
            strategies={"email": hashed_email("anonymized.local")},
        )
        e = _entity("patrick@mail.com", "EMAIL")
        token = factory.create([e])[e]
        assert token.endswith("@anonymized.local")

    def test_person_strategy(self) -> None:
        factory = RealisticHashPlaceholderFactory(
            strategies={"person": hashed_with_prefix("Patient")},
        )
        e = _entity("Patrick", "PERSON")
        token = factory.create([e])[e]
        assert token.startswith("Patient_")

    def test_label_match_is_case_insensitive(self) -> None:
        factory = RealisticHashPlaceholderFactory(
            strategies={"email": hashed_email()},
        )
        # Detector emits upper-case label, strategies were registered lower.
        e = _entity("a@b.com", "EMAIL")
        assert factory.create([e])[e].endswith("@anonymized.local")

    def test_deterministic_per_entity(self) -> None:
        factory = RealisticHashPlaceholderFactory(
            strategies={"person": hashed_with_prefix("X")},
        )
        e = _entity("Patrick", "PERSON")
        t1 = factory.create([e])[e]
        t2 = factory.create([e])[e]
        assert t1 == t2

    def test_different_entities_different_tokens(self) -> None:
        factory = RealisticHashPlaceholderFactory(
            strategies={"person": hashed_with_prefix("X")},
        )
        e1 = _entity("Patrick", "PERSON")
        e2 = _entity("Henri", "PERSON", start=20)
        result = factory.create([e1, e2])
        assert result[e1] != result[e2]

    def test_unknown_label_raises_value_error(self) -> None:
        factory = RealisticHashPlaceholderFactory(
            strategies={"email": hashed_email()},
        )
        e = _entity("Patrick", "PERSON")
        with pytest.raises(ValueError, match="No strategy registered"):
            factory.create([e])

    def test_error_message_lists_known_labels(self) -> None:
        factory = RealisticHashPlaceholderFactory(
            strategies={
                "email": hashed_email(),
                "person": hashed_with_prefix("X"),
            },
        )
        e = _entity("Paris", "LOCATION")
        with pytest.raises(ValueError, match=r"Known labels: email, person"):
            factory.create([e])

    def test_empty_strategies_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            RealisticHashPlaceholderFactory(strategies={})

    def test_custom_hash_length(self) -> None:
        factory = RealisticHashPlaceholderFactory(
            strategies={"person": hashed_with_prefix("X")},
            hash_length=4,
        )
        e = _entity("Patrick", "PERSON")
        token = factory.create([e])[e]
        # "X_" prefix + 4 hash chars
        assert len(token) == len("X_") + 4

    def test_empty_entity_list(self) -> None:
        factory = RealisticHashPlaceholderFactory(
            strategies={"person": hashed_with_prefix("X")},
        )
        assert factory.create([]) == {}

    def test_preservation_tag(self) -> None:
        from piighost.placeholder_tags import (
            PreservesIdentity,
            PreservesLabeledIdentity,
            PreservesLabeledIdentityHashed,
            get_preservation_tag,
        )

        factory = RealisticHashPlaceholderFactory(
            strategies={"person": hashed_with_prefix("X")},
        )
        tag = get_preservation_tag(factory)
        assert tag is PreservesLabeledIdentityHashed
        assert issubclass(tag, PreservesLabeledIdentity)
        assert issubclass(tag, PreservesIdentity)
