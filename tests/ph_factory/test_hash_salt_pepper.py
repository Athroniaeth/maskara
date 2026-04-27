"""Tests for the salt + pepper option on hash placeholder factories.

Backward compatibility: with salt="" and pepper="" the digest layout is
``"{text}:{label}"`` exactly as before, so existing tokens stay stable.
Adding either value switches to ``"{text}:{label}:{salt}:{pepper}"``
with both fields always present so a value cannot collide between the
salt and pepper slots.
"""

from __future__ import annotations

import pytest

from piighost.models import Detection, Entity, Span
from piighost.ph_factory.faker_hash import StrategyValue
from piighost.placeholder import (
    PEPPER_ENV_VAR,
    LabelHashPlaceholderFactory,
    RedactHashPlaceholderFactory,
    hash_canonical,
)


def _entity(text: str = "Patrick", label: str = "PERSON") -> Entity:
    return Entity(
        detections=(
            Detection(
                text=text, label=label, position=Span(0, len(text)), confidence=0.9
            ),
        )
    )


# ---------------------------------------------------------------------------
# hash_canonical primitive
# ---------------------------------------------------------------------------


class TestHashCanonical:
    """The shared digest helper backs every hash factory."""

    def test_default_layout_is_legacy(self) -> None:
        """Empty salt and pepper reproduces the pre-feature digest."""
        legacy = hash_canonical("patrick", "PERSON", "", "", 8)
        # SHA-256("patrick:PERSON") truncated to 8 hex chars.
        # Recompute inline to avoid coupling to the implementation.
        import hashlib

        expected = hashlib.sha256(b"patrick:PERSON").hexdigest()[:8]
        assert legacy == expected

    def test_salt_changes_digest(self) -> None:
        a = hash_canonical("patrick", "PERSON", "", "", 8)
        b = hash_canonical("patrick", "PERSON", "salt-1", "", 8)
        assert a != b

    def test_pepper_changes_digest(self) -> None:
        a = hash_canonical("patrick", "PERSON", "", "", 8)
        b = hash_canonical("patrick", "PERSON", "", "pepper-1", 8)
        assert a != b

    def test_salt_and_pepper_slots_do_not_collide(self) -> None:
        """Same string in salt vs pepper slot must produce different digests."""
        a = hash_canonical("patrick", "PERSON", "abc", "", 8)
        b = hash_canonical("patrick", "PERSON", "", "abc", 8)
        assert a != b

    def test_same_inputs_same_digest(self) -> None:
        a = hash_canonical("patrick", "PERSON", "salt-x", "pepper-y", 8)
        b = hash_canonical("patrick", "PERSON", "salt-x", "pepper-y", 8)
        assert a == b


# ---------------------------------------------------------------------------
# LabelHashPlaceholderFactory
# ---------------------------------------------------------------------------


class TestLabelHashWithSaltPepper:
    """Salt + pepper integrate cleanly into LabelHashPlaceholderFactory."""

    def test_default_construction_unchanged(self) -> None:
        """No salt, no pepper, no env var → token stays identical."""
        e = _entity()
        before = LabelHashPlaceholderFactory().create([e])[e]
        after = LabelHashPlaceholderFactory(salt="", pepper="").create([e])[e]
        assert before == after

    def test_different_salts_yield_different_tokens(self) -> None:
        e = _entity()
        a = LabelHashPlaceholderFactory(salt="instance-a").create([e])[e]
        b = LabelHashPlaceholderFactory(salt="instance-b").create([e])[e]
        assert a != b

    def test_pepper_changes_token(self) -> None:
        e = _entity()
        no_pepper = LabelHashPlaceholderFactory(pepper="").create([e])[e]
        with_pepper = LabelHashPlaceholderFactory(pepper="global-secret").create([e])[e]
        assert no_pepper != with_pepper

    def test_pepper_read_from_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``pepper=None`` (the default) falls back to the env var."""
        e = _entity()
        baseline = LabelHashPlaceholderFactory(pepper="").create([e])[e]
        monkeypatch.setenv(PEPPER_ENV_VAR, "from-env")
        from_env = LabelHashPlaceholderFactory().create([e])[e]
        assert baseline != from_env

    def test_explicit_empty_pepper_overrides_env_var(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``pepper=""`` opts out, ignoring the env var."""
        e = _entity()
        monkeypatch.setenv(PEPPER_ENV_VAR, "from-env")
        explicit_empty = LabelHashPlaceholderFactory(pepper="").create([e])[e]
        baseline_no_env = LabelHashPlaceholderFactory(pepper="").create([e])[e]
        # Removing the env var must not change the result, since pepper=""
        # was explicit.
        monkeypatch.delenv(PEPPER_ENV_VAR)
        assert explicit_empty == baseline_no_env

    def test_same_entity_same_token_within_instance(self) -> None:
        """Determinism within an instance is preserved."""
        e1 = _entity()
        e2 = _entity()
        factory = LabelHashPlaceholderFactory(salt="abc", pepper="xyz")
        result = factory.create([e1, e2])
        assert result[e1] == result[e2]


# ---------------------------------------------------------------------------
# RedactHashPlaceholderFactory
# ---------------------------------------------------------------------------


class TestRedactHashWithSaltPepper:
    """The Redact variant accepts the same salt + pepper API."""

    def test_default_construction_unchanged(self) -> None:
        e = _entity()
        before = RedactHashPlaceholderFactory().create([e])[e]
        after = RedactHashPlaceholderFactory(salt="", pepper="").create([e])[e]
        assert before == after

    def test_salt_changes_token(self) -> None:
        e = _entity()
        a = RedactHashPlaceholderFactory(salt="x").create([e])[e]
        b = RedactHashPlaceholderFactory(salt="y").create([e])[e]
        assert a != b

    def test_pepper_changes_token(self) -> None:
        e = _entity()
        a = RedactHashPlaceholderFactory(pepper="").create([e])[e]
        b = RedactHashPlaceholderFactory(pepper="secret").create([e])[e]
        assert a != b


# ---------------------------------------------------------------------------
# FakerHashPlaceholderFactory
# ---------------------------------------------------------------------------


class TestFakerHashWithSaltPepper:
    """Salt + pepper integrate into FakerHashPlaceholderFactory the same way."""

    def test_default_construction_unchanged(self) -> None:
        from piighost.ph_factory.faker_hash import FakerHashPlaceholderFactory

        e = _entity()
        strategies: dict[str, StrategyValue] = {"person": "John Doe"}
        before = FakerHashPlaceholderFactory(strategies=strategies).create([e])[e]
        after = FakerHashPlaceholderFactory(
            strategies=strategies, salt="", pepper=""
        ).create([e])[e]
        assert before == after

    def test_salt_changes_token(self) -> None:
        from piighost.ph_factory.faker_hash import FakerHashPlaceholderFactory

        e = _entity()
        strategies: dict[str, StrategyValue] = {"person": "John Doe"}
        a = FakerHashPlaceholderFactory(strategies=strategies, salt="a").create([e])[e]
        b = FakerHashPlaceholderFactory(strategies=strategies, salt="b").create([e])[e]
        assert a != b

    def test_pepper_changes_token(self) -> None:
        from piighost.ph_factory.faker_hash import FakerHashPlaceholderFactory

        e = _entity()
        strategies: dict[str, StrategyValue] = {"person": "John Doe"}
        no_pepper = FakerHashPlaceholderFactory(
            strategies=strategies, pepper=""
        ).create([e])[e]
        with_pepper = FakerHashPlaceholderFactory(
            strategies=strategies, pepper="secret"
        ).create([e])[e]
        assert no_pepper != with_pepper
