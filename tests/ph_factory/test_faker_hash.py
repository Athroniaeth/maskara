"""Tests for FakerCounter / FakerHash placeholder factories."""

import pytest

from piighost.models import Detection, Entity, Span
from piighost.ph_factory.faker_hash import (
    FakerCounterPlaceholderFactory,
    FakerHashPlaceholderFactory,
    fake_ip,
    fake_phone,
    fake_with_seed,
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
# FakerHashPlaceholderFactory: 3-mode dispatch
# ---------------------------------------------------------------------------


class TestFakerHashDispatchModes:
    """Strategy can be: bare base (str), template (str with {hash}), callable."""

    def test_base_mode_appends_colon_hash(self) -> None:
        factory = FakerHashPlaceholderFactory(strategies={"person": "John Doe"})
        e = _entity("Patrick", "PERSON")
        token = factory.create([e])[e]
        assert token.startswith("John Doe:")
        assert len(token) > len("John Doe:")

    def test_template_mode_substitutes_hash(self) -> None:
        factory = FakerHashPlaceholderFactory(
            strategies={"email": "{hash}@example.com"}
        )
        e = _entity("alice@mail.com", "EMAIL")
        token = factory.create([e])[e]
        assert token.endswith("@example.com")
        assert "{hash}" not in token

    def test_template_mode_inline(self) -> None:
        factory = FakerHashPlaceholderFactory(
            strategies={"phone": "+33 6 12 34 56 {hash}"}
        )
        e = _entity("0612345678", "PHONE")
        token = factory.create([e])[e]
        assert token.startswith("+33 6 12 34 56 ")

    def test_callable_mode(self) -> None:
        factory = FakerHashPlaceholderFactory(
            strategies={"person": lambda h: f"FN<{h}>"}
        )
        e = _entity("Patrick", "PERSON")
        token = factory.create([e])[e]
        assert token.startswith("FN<")
        assert token.endswith(">")


# ---------------------------------------------------------------------------
# FakerHashPlaceholderFactory: behaviour
# ---------------------------------------------------------------------------


class TestFakerHashBehaviour:
    """Hash determinism, label scoping, and error reporting."""

    def test_label_match_is_case_insensitive(self) -> None:
        factory = FakerHashPlaceholderFactory(
            strategies={"email": "{hash}@anonymized.local"},
        )
        e = _entity("a@b.com", "EMAIL")
        assert factory.create([e])[e].endswith("@anonymized.local")

    def test_deterministic_per_entity(self) -> None:
        factory = FakerHashPlaceholderFactory(strategies={"person": "John Doe"})
        e = _entity("Patrick", "PERSON")
        assert factory.create([e])[e] == factory.create([e])[e]

    def test_different_entities_different_tokens(self) -> None:
        factory = FakerHashPlaceholderFactory(strategies={"person": "John Doe"})
        e1 = _entity("Patrick", "PERSON")
        e2 = _entity("Henri", "PERSON", start=20)
        result = factory.create([e1, e2])
        assert result[e1] != result[e2]

    def test_unknown_label_raises_value_error(self) -> None:
        factory = FakerHashPlaceholderFactory(strategies={"email": "{hash}@x.io"})
        e = _entity("Patrick", "PERSON")
        with pytest.raises(ValueError, match="No strategy registered"):
            factory.create([e])

    def test_error_message_lists_known_labels(self) -> None:
        factory = FakerHashPlaceholderFactory(
            strategies={"email": "{hash}@x.io", "person": "John Doe"},
        )
        e = _entity("Paris", "LOCATION")
        with pytest.raises(ValueError, match=r"Known labels: email, person"):
            factory.create([e])

    def test_empty_strategies_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            FakerHashPlaceholderFactory(strategies={})

    def test_custom_hash_length(self) -> None:
        factory = FakerHashPlaceholderFactory(
            strategies={"person": "John Doe"}, hash_length=4
        )
        e = _entity("Patrick", "PERSON")
        token = factory.create([e])[e]
        assert len(token) == len("John Doe:") + 4

    def test_default_strategies_used_when_none(self) -> None:
        factory = FakerHashPlaceholderFactory()
        e = _entity("Patrick", "PERSON")
        assert factory.create([e])[e].startswith("John Doe:")

    def test_empty_entity_list(self) -> None:
        factory = FakerHashPlaceholderFactory(strategies={"person": "John Doe"})
        assert factory.create([]) == {}

    def test_preservation_tag(self) -> None:
        from piighost.placeholder_tags import (
            PreservesIdentity,
            PreservesLabeledIdentity,
            PreservesLabeledIdentityHashed,
            get_preservation_tag,
        )

        factory = FakerHashPlaceholderFactory(strategies={"person": "John Doe"})
        tag = get_preservation_tag(factory)
        assert tag is PreservesLabeledIdentityHashed
        assert issubclass(tag, PreservesLabeledIdentity)
        assert issubclass(tag, PreservesIdentity)


# ---------------------------------------------------------------------------
# FakerCounterPlaceholderFactory
# ---------------------------------------------------------------------------


class TestFakerCounter:
    """Sequential counter per label, same 3-mode dispatch as FakerHash."""

    def test_base_mode_counter(self) -> None:
        factory = FakerCounterPlaceholderFactory(strategies={"person": "John Doe"})
        e1 = _entity("Patrick", "PERSON")
        e2 = _entity("Henri", "PERSON", start=20)
        result = factory.create([e1, e2])
        assert result[e1] == "John Doe:1"
        assert result[e2] == "John Doe:2"

    def test_template_mode_counter(self) -> None:
        factory = FakerCounterPlaceholderFactory(
            strategies={"email": "{counter}@example.com"}
        )
        e1 = _entity("a@b.com", "EMAIL")
        e2 = _entity("c@d.com", "EMAIL", start=20)
        result = factory.create([e1, e2])
        assert result[e1] == "1@example.com"
        assert result[e2] == "2@example.com"

    def test_per_label_counters(self) -> None:
        factory = FakerCounterPlaceholderFactory(
            strategies={"person": "John Doe", "location": "Paris"},
        )
        e1 = _entity("Patrick", "PERSON")
        e2 = _entity("Lyon", "LOCATION", start=20)
        e3 = _entity("Henri", "PERSON", start=30)
        result = factory.create([e1, e2, e3])
        assert result[e1] == "John Doe:1"
        assert result[e2] == "Paris:1"
        assert result[e3] == "John Doe:2"

    def test_callable_strategy_receives_counter_str(self) -> None:
        seen = []

        def callable_strategy(counter: str) -> str:
            seen.append(counter)
            return f"X:{counter}"

        factory = FakerCounterPlaceholderFactory(
            strategies={"person": callable_strategy},
        )
        e1 = _entity("Patrick", "PERSON")
        e2 = _entity("Henri", "PERSON", start=20)
        factory.create([e1, e2])
        assert seen == ["1", "2"]

    def test_unknown_label_raises_value_error(self) -> None:
        factory = FakerCounterPlaceholderFactory(strategies={"email": "x"})
        e = _entity("Patrick", "PERSON")
        with pytest.raises(ValueError, match="No strategy registered"):
            factory.create([e])

    def test_default_strategies(self) -> None:
        factory = FakerCounterPlaceholderFactory()
        e = _entity("Patrick", "PERSON")
        assert factory.create([e])[e] == "John Doe:1"


# ---------------------------------------------------------------------------
# Seed-Faker helpers
# ---------------------------------------------------------------------------


class TestSeedFakerHelpers:
    """fake_* helpers produce deterministic Faker output from the hash."""

    def test_fake_ip_is_deterministic(self) -> None:
        strategy = fake_ip()
        assert strategy("a1b2c3d4") == strategy("a1b2c3d4")

    def test_fake_ip_returns_dotted_quad(self) -> None:
        strategy = fake_ip()
        ip = strategy("deadbeef")
        parts = ip.split(".")
        assert len(parts) == 4
        for part in parts:
            assert 0 <= int(part) <= 255

    def test_fake_phone_returns_string(self) -> None:
        strategy = fake_phone()
        assert isinstance(strategy("a1b2c3d4"), str)

    def test_fake_with_seed_custom_method(self) -> None:
        strategy = fake_with_seed("ipv4")
        assert strategy("a1b2c3d4") == strategy("a1b2c3d4")

    def test_helper_used_in_factory(self) -> None:
        factory = FakerHashPlaceholderFactory(strategies={"ip_address": fake_ip()})
        e = _entity("192.168.0.1", "IP_ADDRESS")
        token = factory.create([e])[e]
        parts = token.split(".")
        assert len(parts) == 4
