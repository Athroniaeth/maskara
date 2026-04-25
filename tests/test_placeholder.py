"""Tests for placeholder factories."""

from piighost.models import Detection, Entity, Span
from piighost.placeholder import (
    LabelCounterPlaceholderFactory,
    LabelHashPlaceholderFactory,
    LabelPlaceholderFactory,
    MaskPlaceholderFactory,
    RedactCounterPlaceholderFactory,
    RedactHashPlaceholderFactory,
    RedactPlaceholderFactory,
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
# LabelCounterPlaceholderFactory
# ---------------------------------------------------------------------------


class TestLabelCounterPlaceholderFactory:
    """Generates <<LABEL:N>> tokens with per-label counters."""

    def test_first_entity_gets_counter_one(self) -> None:
        e = _entity("Patrick", "PERSON")
        result = LabelCounterPlaceholderFactory().create([e])
        assert result[e] == "<<PERSON:1>>"

    def test_second_entity_same_label_gets_counter_two(self) -> None:
        e1 = _entity("Patrick", "PERSON")
        e2 = _entity("Henri", "PERSON", start=20)
        result = LabelCounterPlaceholderFactory().create([e1, e2])
        assert result[e1] == "<<PERSON:1>>"
        assert result[e2] == "<<PERSON:2>>"

    def test_different_labels_have_separate_counters(self) -> None:
        e1 = _entity("Patrick", "PERSON")
        e2 = _entity("Paris", "LOCATION")
        result = LabelCounterPlaceholderFactory().create([e1, e2])
        assert result[e1] == "<<PERSON:1>>"
        assert result[e2] == "<<LOCATION:1>>"

    def test_empty_list(self) -> None:
        assert LabelCounterPlaceholderFactory().create([]) == {}


# ---------------------------------------------------------------------------
# LabelHashPlaceholderFactory
# ---------------------------------------------------------------------------


class TestLabelHashPlaceholderFactory:
    """Generates <<LABEL:hash>> tokens using SHA-256."""

    def test_token_format(self) -> None:
        e = _entity("Patrick", "PERSON")
        token = LabelHashPlaceholderFactory().create([e])[e]
        assert token.startswith("<<PERSON:")
        assert token.endswith(">>")

    def test_deterministic(self) -> None:
        e = _entity("Patrick", "PERSON")
        t1 = LabelHashPlaceholderFactory().create([e])[e]
        t2 = LabelHashPlaceholderFactory().create([e])[e]
        assert t1 == t2

    def test_different_entities_different_hashes(self) -> None:
        e1 = _entity("Patrick", "PERSON")
        e2 = _entity("Henri", "PERSON", start=20)
        result = LabelHashPlaceholderFactory().create([e1, e2])
        assert result[e1] != result[e2]

    def test_same_text_different_label_different_hash(self) -> None:
        e1 = _entity("Paris", "LOCATION")
        e2 = _entity("Paris", "PERSON")
        result = LabelHashPlaceholderFactory().create([e1, e2])
        assert result[e1] != result[e2]

    def test_custom_hash_length(self) -> None:
        e = _entity("Patrick", "PERSON")
        token = LabelHashPlaceholderFactory(hash_length=4).create([e])[e]
        hash_part = token.split(":")[1].rstrip(">")
        assert len(hash_part) == 4

    def test_double_angle_brackets(self) -> None:
        e = _entity("Patrick", "PERSON")
        token = LabelHashPlaceholderFactory().create([e])[e]
        assert token.startswith("<<") and token.endswith(">>")

    def test_empty_list(self) -> None:
        assert LabelHashPlaceholderFactory().create([]) == {}


# ---------------------------------------------------------------------------
# LabelPlaceholderFactory
# ---------------------------------------------------------------------------


class TestLabelPlaceholderFactory:
    """Generates <<LABEL>> tokens no discrimination between entities."""

    def test_token_format(self) -> None:
        e = _entity("Patrick", "PERSON")
        assert LabelPlaceholderFactory().create([e])[e] == "<<PERSON>>"

    def test_same_label_same_token(self) -> None:
        e1 = _entity("Patrick", "PERSON")
        e2 = _entity("Henri", "PERSON", start=20)
        result = LabelPlaceholderFactory().create([e1, e2])
        assert result[e1] == result[e2] == "<<PERSON>>"

    def test_different_labels_different_tokens(self) -> None:
        e1 = _entity("Patrick", "PERSON")
        e2 = _entity("Paris", "LOCATION")
        result = LabelPlaceholderFactory().create([e1, e2])
        assert result[e1] != result[e2]

    def test_empty_list(self) -> None:
        assert LabelPlaceholderFactory().create([]) == {}


# ---------------------------------------------------------------------------
# MaskPlaceholderFactory
# ---------------------------------------------------------------------------


class TestMaskPlaceholderFactory:
    """Generates partially masked tokens preserving some original characters."""

    # -- Email masking --

    def test_email_masks_local_part(self) -> None:
        e = _entity("patrick@email.com", "EMAIL")
        assert MaskPlaceholderFactory().create([e])[e] == "p******@email.com"

    def test_email_single_char_local(self) -> None:
        e = _entity("j@example.org", "EMAIL")
        assert MaskPlaceholderFactory().create([e])[e] == "j@example.org"

    def test_email_label_case_insensitive(self) -> None:
        e = _entity("alice@test.io", "email")
        assert MaskPlaceholderFactory().create([e])[e] == "a****@test.io"

    # -- Numeric masking --

    def test_credit_card_keeps_last_four(self) -> None:
        e = _entity("4111-1111-1111-1234", "CREDIT_CARD")
        assert MaskPlaceholderFactory().create([e])[e] == "************1234"

    def test_phone_keeps_last_four(self) -> None:
        e = _entity("+33 6 12 34 56 78", "PHONE_INTERNATIONAL")
        assert MaskPlaceholderFactory().create([e])[e] == "*******5678"

    def test_ssn_keeps_last_four(self) -> None:
        e = _entity("123-45-6789", "US_SSN")
        assert MaskPlaceholderFactory().create([e])[e] == "*****6789"

    def test_numeric_short_value_unchanged(self) -> None:
        e = _entity("1234", "CREDIT_CARD")
        assert MaskPlaceholderFactory().create([e])[e] == "1234"

    def test_numeric_custom_visible_chars(self) -> None:
        e = _entity("4111-1111-1111-1234", "CREDIT_CARD")
        result = MaskPlaceholderFactory(visible_chars=6).create([e])[e]
        assert result == "**********111234"

    # -- Default masking (names, locations, etc.) --

    def test_person_keeps_first_char(self) -> None:
        e = _entity("Patrick", "PERSON")
        assert MaskPlaceholderFactory().create([e])[e] == "P******"

    def test_location_keeps_first_char(self) -> None:
        e = _entity("Paris", "LOCATION")
        assert MaskPlaceholderFactory().create([e])[e] == "P****"

    def test_single_char_unchanged(self) -> None:
        e = _entity("X", "PERSON")
        assert MaskPlaceholderFactory().create([e])[e] == "X"

    # -- Custom mask char --

    def test_custom_mask_char(self) -> None:
        e = _entity("Patrick", "PERSON")
        assert MaskPlaceholderFactory(mask_char="#").create([e])[e] == "P######"

    # -- Custom strategies --

    def test_custom_strategies_replace_defaults(self) -> None:
        """User-provided strategies fully replace the built-in defaults."""

        def reverse_mask(text, _mc):
            return text[::-1]

        factory = MaskPlaceholderFactory(strategies={"PERSON": reverse_mask})
        e = _entity("Patrick", "PERSON")
        assert factory.create([e])[e] == "kcirtaP"

    def test_custom_strategy_label_case_insensitive(self) -> None:
        """Labels in strategies are normalized to lowercase."""

        def upper_mask(text, _mc):
            return text.upper()

        factory = MaskPlaceholderFactory(strategies={"CUSTOM_LABEL": upper_mask})
        e = _entity("secret", "CUSTOM_LABEL")
        assert factory.create([e])[e] == "SECRET"

    def test_custom_strategy_unknown_label_falls_back(self) -> None:
        """Labels not in custom strategies fall back to mask_default."""

        def noop(text, _mc):
            return "NOOP"

        factory = MaskPlaceholderFactory(strategies={"PERSON": noop})
        e = _entity("Paris", "LOCATION")
        assert factory.create([e])[e] == "P****"

    # -- Empty --

    def test_empty_list(self) -> None:
        assert MaskPlaceholderFactory().create([]) == {}


class TestGetPreservationTag:
    """Runtime tag recovery used by the pipeline's factory check."""

    def test_counter_is_labeled_identity_opaque(self) -> None:
        from piighost.placeholder import LabelCounterPlaceholderFactory
        from piighost.placeholder_tags import (
            PreservesIdentity,
            PreservesLabel,
            PreservesLabeledIdentityOpaque,
            get_preservation_tag,
        )

        tag = get_preservation_tag(LabelCounterPlaceholderFactory())
        assert tag is PreservesLabeledIdentityOpaque
        # multi-inheritance: opaque labeled-identity is both a label tag and an identity tag
        assert issubclass(tag, PreservesIdentity)
        assert issubclass(tag, PreservesLabel)

    def test_hash_is_labeled_identity_opaque(self) -> None:
        from piighost.placeholder import LabelHashPlaceholderFactory
        from piighost.placeholder_tags import (
            PreservesIdentity,
            PreservesLabel,
            PreservesLabeledIdentityOpaque,
            get_preservation_tag,
        )

        tag = get_preservation_tag(LabelHashPlaceholderFactory())
        assert tag is PreservesLabeledIdentityOpaque
        assert issubclass(tag, PreservesIdentity)
        assert issubclass(tag, PreservesLabel)

    def test_redact_is_preserves_label(self) -> None:
        from piighost.placeholder import LabelPlaceholderFactory
        from piighost.placeholder_tags import PreservesLabel, get_preservation_tag

        assert get_preservation_tag(LabelPlaceholderFactory()) is PreservesLabel

    def test_mask_is_preserves_shape(self) -> None:
        from piighost.placeholder import MaskPlaceholderFactory
        from piighost.placeholder_tags import PreservesShape, get_preservation_tag

        assert get_preservation_tag(MaskPlaceholderFactory()) is PreservesShape

    def test_untagged_factory_returns_none(self) -> None:
        """A duck-typed factory that doesn't subclass the generic protocol is untagged."""
        from piighost.placeholder_tags import get_preservation_tag

        class DuckFactory:
            def create(self, entities):  # noqa: ARG002
                return {}

        assert get_preservation_tag(DuckFactory()) is None


# ---------------------------------------------------------------------------
# RedactPlaceholderFactory
# ---------------------------------------------------------------------------


class TestRedactPlaceholderFactory:
    """Generates the same constant token for every entity."""

    def test_default_token(self) -> None:
        e1 = _entity("Patrick", "PERSON")
        e2 = _entity("Paris", "LOCATION", start=20)
        result = RedactPlaceholderFactory().create([e1, e2])
        assert result[e1] == "<<REDACT>>"
        assert result[e2] == "<<REDACT>>"

    def test_custom_value(self) -> None:
        e = _entity("Patrick", "PERSON")
        token = RedactPlaceholderFactory(value="HIDDEN").create([e])[e]
        assert token == "<<HIDDEN>>"

    def test_empty_list(self) -> None:
        assert RedactPlaceholderFactory().create([]) == {}

    def test_preservation_tag(self) -> None:
        from piighost.placeholder_tags import (
            PreservesNothing,
            get_preservation_tag,
        )

        assert get_preservation_tag(RedactPlaceholderFactory()) is PreservesNothing


# ---------------------------------------------------------------------------
# RedactHashPlaceholderFactory
# ---------------------------------------------------------------------------


class TestRedactHashPlaceholderFactory:
    """Generates <<REDACT:hash>> tokens with no label."""

    def test_token_format(self) -> None:
        e = _entity("Patrick", "PERSON")
        token = RedactHashPlaceholderFactory().create([e])[e]
        assert token.startswith("<<REDACT:")
        assert token.endswith(">>")
        assert "PERSON" not in token

    def test_deterministic(self) -> None:
        e = _entity("Patrick", "PERSON")
        t1 = RedactHashPlaceholderFactory().create([e])[e]
        t2 = RedactHashPlaceholderFactory().create([e])[e]
        assert t1 == t2

    def test_same_text_different_label_different_token(self) -> None:
        # Hash includes the label so PERSON("Paris") and LOCATION("Paris")
        # are distinguished even if the label is hidden in the output.
        e1 = _entity("Paris", "PERSON")
        e2 = _entity("Paris", "LOCATION")
        result = RedactHashPlaceholderFactory().create([e1, e2])
        assert result[e1] != result[e2]

    def test_custom_prefix(self) -> None:
        e = _entity("Patrick", "PERSON")
        token = RedactHashPlaceholderFactory(prefix="HIDDEN").create([e])[e]
        assert token.startswith("<<HIDDEN:")

    def test_custom_hash_length(self) -> None:
        e = _entity("Patrick", "PERSON")
        token = RedactHashPlaceholderFactory(hash_length=4).create([e])[e]
        hash_part = token.split(":")[1].rstrip(">")
        assert len(hash_part) == 4

    def test_empty_list(self) -> None:
        assert RedactHashPlaceholderFactory().create([]) == {}

    def test_preservation_tag(self) -> None:
        from piighost.placeholder_tags import (
            PreservesIdentity,
            PreservesIdentityOnly,
            get_preservation_tag,
        )

        tag = get_preservation_tag(RedactHashPlaceholderFactory())
        assert tag is PreservesIdentityOnly
        assert issubclass(tag, PreservesIdentity)


# ---------------------------------------------------------------------------
# RedactCounterPlaceholderFactory
# ---------------------------------------------------------------------------


class TestRedactCounterPlaceholderFactory:
    """Generates <<REDACT:N>> tokens with a global counter, no label."""

    def test_first_entity_gets_counter_one(self) -> None:
        e = _entity("Patrick", "PERSON")
        assert RedactCounterPlaceholderFactory().create([e])[e] == "<<REDACT:1>>"

    def test_global_counter_across_labels(self) -> None:
        e1 = _entity("Patrick", "PERSON")
        e2 = _entity("Paris", "LOCATION", start=20)
        e3 = _entity("Henri", "PERSON", start=30)
        result = RedactCounterPlaceholderFactory().create([e1, e2, e3])
        assert result[e1] == "<<REDACT:1>>"
        assert result[e2] == "<<REDACT:2>>"
        assert result[e3] == "<<REDACT:3>>"

    def test_custom_prefix(self) -> None:
        e = _entity("Patrick", "PERSON")
        token = RedactCounterPlaceholderFactory(prefix="HIDDEN").create([e])[e]
        assert token == "<<HIDDEN:1>>"

    def test_empty_list(self) -> None:
        assert RedactCounterPlaceholderFactory().create([]) == {}

    def test_preservation_tag(self) -> None:
        from piighost.placeholder_tags import (
            PreservesIdentity,
            PreservesIdentityOnly,
            get_preservation_tag,
        )

        tag = get_preservation_tag(RedactCounterPlaceholderFactory())
        assert tag is PreservesIdentityOnly
        assert issubclass(tag, PreservesIdentity)
