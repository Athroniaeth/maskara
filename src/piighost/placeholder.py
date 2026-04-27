import hashlib
import os
import re
from collections import defaultdict
from collections.abc import Callable
from typing import Protocol

from typing_extensions import TypeVar

from piighost.models import Entity
from piighost.placeholder_tags import (
    PlaceholderPreservation,
    PreservesIdentityOnly,
    PreservesLabel,
    PreservesLabeledIdentityOpaque,
    PreservesNothing,
    PreservesShape,
)

PEPPER_ENV_VAR = "PIIGHOST_HASH_PEPPER"
"""Environment variable read when a hash factory's ``pepper`` is left
to its default ``None``.  Lets operators inject a process-wide secret
without changing pipeline construction code."""


def _resolve_pepper(pepper: str | None) -> str:
    """Resolve the pepper value, falling back to the env var.

    ``None`` means "use the env var if set, otherwise none".  An empty
    string is treated as an explicit "no pepper" and skips the env-var
    lookup.
    """
    if pepper is not None:
        return pepper
    return os.environ.get(PEPPER_ENV_VAR, "")


def hash_canonical(
    canonical_text: str,
    label: str,
    salt: str,
    pepper: str,
    hash_length: int,
) -> str:
    """SHA-256 digest of a ``(text, label)`` pair, optionally salted/peppered.

    When both ``salt`` and ``pepper`` are empty, the digest input is the
    legacy ``"{canonical_text}:{label}"`` layout, so existing tokens
    stay stable.  As soon as either is non-empty, the layout switches
    to ``"{canonical_text}:{label}:{salt}:{pepper}"`` with both fields
    always present (even if empty) so a value cannot collide between
    the salt slot and the pepper slot.

    Args:
        canonical_text: Lower-cased entity text.
        label: Entity label.
        salt: Per-instance salt (empty string disables it).
        pepper: Process-wide secret (empty string disables it).
        hash_length: Number of hex characters to keep from the digest.

    Returns:
        The truncated hex digest.
    """
    raw = f"{canonical_text}:{label}"
    if salt or pepper:
        raw = f"{raw}:{salt}:{pepper}"
    return hashlib.sha256(raw.encode()).hexdigest()[:hash_length]


PreservationT_co = TypeVar(
    "PreservationT_co",
    bound=PlaceholderPreservation,
    default=PlaceholderPreservation,
    covariant=True,
)
"""Phantom tag describing how much information a factory preserves.

Defaults to :class:`PlaceholderPreservation` so that the legacy
unparameterised ``AnyPlaceholderFactory`` annotation stays usable.
Consumers that care about the level (anonymiser, pipeline,
middleware) specialise the parameter.
"""


class AnyPlaceholderFactory(Protocol[PreservationT_co]):
    """Protocol defining the interface for placeholder factories.

    A placeholder factory takes a list of entities and returns
    a mapping from each entity to its replacement token.

    The generic parameter ``PreservationT_co`` is a phantom tag
    declaring the information-preservation level of the tokens (see
    :mod:`piighost.placeholder_tags`).  It lets downstream components
    reject incompatible factories at type-check time.
    """

    def create(self, entities: list[Entity]) -> dict[Entity, str]:
        """Create replacement tokens for all entities at once.

        Args:
            entities: The entities to create tokens for.

        Returns:
            A dict mapping each entity to its replacement token.
        """
        ...


class RedactPlaceholderFactory(AnyPlaceholderFactory[PreservesNothing]):
    """Factory that emits the same constant token for every entity.

    The token is wrapped in ``<<...>>`` so it stays visually distinct
    from natural text. Every entity collapses to the same string, so
    the LLM learns *that* something was redacted but nothing about
    its type, count, or relations.

    Args:
        value: The bare token text (without delimiters). Defaults to
            ``"REDACT"``.

    Example:
        >>> from piighost.models import Detection, Entity, Span
        >>> factory = RedactPlaceholderFactory()
        >>> e = Entity(detections=(Detection(text="Patrick", label="PERSON", position=Span(0, 7), confidence=0.9),))
        >>> factory.create([e])[e]
        '<<REDACT>>'
    """

    _token: str

    def __init__(self, value: str = "REDACT") -> None:
        self._token = f"<<{value}>>"

    def create(self, entities: list[Entity]) -> dict[Entity, str]:
        """Create the same constant token for all entities.

        Args:
            entities: The entities to create tokens for.

        Returns:
            A dict mapping every entity to the same token.
        """
        return {entity: self._token for entity in entities}


class LabelCounterPlaceholderFactory(
    AnyPlaceholderFactory[PreservesLabeledIdentityOpaque]
):
    """Factory that generates tokens like ``<<PERSON:1>>``, ``<<PERSON:2>>``.

    Each entity gets a unique counter per label. Two different PERSON
    entities get ``<<PERSON:1>>`` and ``<<PERSON:2>>``, while a LOCATION
    entity gets ``<<LOCATION:1>>``.

    Example:
        >>> from piighost.models import Detection, Entity, Span
        >>> factory = LabelCounterPlaceholderFactory()
        >>> e = Entity(detections=(Detection(text="Patrick", label="PERSON", position=Span(0, 7), confidence=0.9),))
        >>> factory.create([e])[e]
        '<<PERSON:1>>'
    """

    def __init__(self): ...

    def create(self, entities: list[Entity]) -> dict[Entity, str]:
        """Create counter-based tokens for all entities.

        Args:
            entities: The entities to create tokens for.

        Returns:
            A dict mapping each entity to a token like ``"<<PERSON:1>>"``.
        """
        result: dict[Entity, str] = {}
        counters: dict[str, int] = defaultdict(int)

        for entity in entities:
            label = entity.label
            counters[label] += 1
            result[entity] = f"<<{label}:{counters[label]}>>"

        return result


class LabelHashPlaceholderFactory(
    AnyPlaceholderFactory[PreservesLabeledIdentityOpaque]
):
    """Factory that generates tokens like ``<<PERSON:a1b2c3d4>>``.

    Uses SHA-256 of the canonical text + label to produce a deterministic,
    opaque token. Same entity always produces the same hash. The double
    angle brackets keep the token visually distinct from real text and
    from any HTML/XML the LLM might generate.

    Args:
        hash_length: Number of hex characters to use from the hash.
            Defaults to 8.
        salt: Per-instance string mixed into the hash.  Two instances
            with different salts produce different placeholders for the
            same input.  Defaults to ``""`` (no salt).
        pepper: Process-wide secret mixed into the hash on top of
            ``salt``.  Defaults to ``None``, which falls back to the
            ``PIIGHOST_HASH_PEPPER`` environment variable; pass an
            empty string to opt out explicitly.  Together with the
            salt, the pepper makes the derivation non-replayable
            outside the process and defeats rainbow-table attacks on
            small-cardinality inputs (first names, cities).

    Example:
        >>> from piighost.models import Detection, Entity, Span
        >>> factory = LabelHashPlaceholderFactory()
        >>> e = Entity(detections=(Detection(text="Patrick", label="PERSON", position=Span(0, 7), confidence=0.9),))
        >>> token = factory.create([e])[e]
        >>> token.startswith('<<PERSON:') and token.endswith('>>')
        True
    """

    _hash_length: int
    _salt: str
    _pepper: str

    def __init__(
        self,
        hash_length: int = 8,
        salt: str = "",
        pepper: str | None = None,
    ) -> None:
        self._hash_length = hash_length
        self._salt = salt
        self._pepper = _resolve_pepper(pepper)

    def create(self, entities: list[Entity]) -> dict[Entity, str]:
        """Create hash-based tokens for all entities.

        Args:
            entities: The entities to create tokens for.

        Returns:
            A dict mapping each entity to a token like ``"<<PERSON:a1b2c3d4>>"``.
        """
        result: dict[Entity, str] = {}

        for entity in entities:
            canonical_text = entity.detections[0].text.lower()
            label = entity.label
            digest = hash_canonical(
                canonical_text,
                label,
                self._salt,
                self._pepper,
                self._hash_length,
            )
            result[entity] = f"<<{label}:{digest}>>"

        return result


class RedactCounterPlaceholderFactory(AnyPlaceholderFactory[PreservesIdentityOnly]):
    """Factory that generates tokens like ``<<REDACT:1>>``, ``<<REDACT:2>>``.

    Each entity gets a globally unique counter, regardless of label.
    Two distinct PERSON entities get ``<<REDACT:1>>`` and ``<<REDACT:2>>``;
    a LOCATION entity inserted between them gets ``<<REDACT:3>>``. The
    label is not revealed; only the counter distinguishes entities.

    Useful for archival redaction with traceable ids, or when you want
    a label-less identity that is easier to read in logs than a hash.

    Args:
        prefix: Bare prefix before the counter. Defaults to ``"REDACT"``.

    Example:
        >>> from piighost.models import Detection, Entity, Span
        >>> factory = RedactCounterPlaceholderFactory()
        >>> e = Entity(detections=(Detection(text="Patrick", label="PERSON", position=Span(0, 7), confidence=0.9),))
        >>> factory.create([e])[e]
        '<<REDACT:1>>'
    """

    _prefix: str

    def __init__(self, prefix: str = "REDACT") -> None:
        self._prefix = prefix

    def create(self, entities: list[Entity]) -> dict[Entity, str]:
        """Create label-less counter tokens for all entities.

        Args:
            entities: The entities to create tokens for.

        Returns:
            A dict mapping each entity to a token like
            ``"<<REDACT:1>>"``, ``"<<REDACT:2>>"``…
        """
        return {
            entity: f"<<{self._prefix}:{counter}>>"
            for counter, entity in enumerate(entities, start=1)
        }


class RedactHashPlaceholderFactory(AnyPlaceholderFactory[PreservesIdentityOnly]):
    """Factory that generates tokens like ``<<REDACT:a1b2c3d4>>``.

    Like :class:`LabelHashPlaceholderFactory` but **without** the
    entity label in the token. Two distinct PERSON entities and two
    distinct LOCATION entities all carry the ``REDACT:`` prefix; only
    the hash distinguishes them. The LLM learns the entities are
    different but cannot tell whether they are persons, emails, or
    credit cards.

    Useful for bias reduction (CV screening: same prefix erases the
    gender / origin signal a name carries) and for sensitive types
    where the type itself is a PII (medical category, clearance level).

    Args:
        prefix: Bare prefix before the hash. Defaults to ``"REDACT"``.
        hash_length: Number of hex characters from the SHA-256 digest.
            Defaults to ``8``.
        salt: Per-instance string mixed into the hash.  See
            :class:`LabelHashPlaceholderFactory` for details.
        pepper: Process-wide secret mixed into the hash, sourced from
            the ``PIIGHOST_HASH_PEPPER`` environment variable when left
            to ``None``.  See :class:`LabelHashPlaceholderFactory`.

    Example:
        >>> from piighost.models import Detection, Entity, Span
        >>> factory = RedactHashPlaceholderFactory()
        >>> e = Entity(detections=(Detection(text="Patrick", label="PERSON", position=Span(0, 7), confidence=0.9),))
        >>> token = factory.create([e])[e]
        >>> token.startswith('<<REDACT:') and token.endswith('>>')
        True
    """

    _prefix: str
    _hash_length: int
    _salt: str
    _pepper: str

    def __init__(
        self,
        prefix: str = "REDACT",
        hash_length: int = 8,
        salt: str = "",
        pepper: str | None = None,
    ) -> None:
        self._prefix = prefix
        self._hash_length = hash_length
        self._salt = salt
        self._pepper = _resolve_pepper(pepper)

    def create(self, entities: list[Entity]) -> dict[Entity, str]:
        """Create label-less hash tokens for all entities.

        Args:
            entities: The entities to create tokens for.

        Returns:
            A dict mapping each entity to a token like
            ``"<<REDACT:a1b2c3d4>>"``.
        """
        result: dict[Entity, str] = {}

        for entity in entities:
            # Hash on (text + label) so two entities with the same
            # surface text but different labels still get distinct ids.
            canonical_text = entity.detections[0].text.lower()
            digest = hash_canonical(
                canonical_text,
                entity.label,
                self._salt,
                self._pepper,
                self._hash_length,
            )
            result[entity] = f"<<{self._prefix}:{digest}>>"

        return result


class LabelPlaceholderFactory(AnyPlaceholderFactory[PreservesLabel]):
    """Factory that generates tokens like ``<<PERSON>>``.

    All entities with the same label share the same token there is
    no discrimination between different PIIs of the same type.
    Reversible because ``deanonymize`` receives the entities with
    their original positions.

    Example:
        >>> from piighost.models import Detection, Entity, Span
        >>> factory = LabelPlaceholderFactory()
        >>> e = Entity(detections=(Detection(text="Patrick", label="PERSON", position=Span(0, 7), confidence=0.9),))
        >>> factory.create([e])[e]
        '<<PERSON>>'
    """

    def __init__(self): ...

    def create(self, entities: list[Entity]) -> dict[Entity, str]:
        """Create redact tokens for all entities.

        Args:
            entities: The entities to create tokens for.

        Returns:
            A dict mapping each entity to a token like ``"<<PERSON>>"``.
        """
        return {entity: f"<<{entity.label}>>" for entity in entities}


MaskFn = Callable[[str, str], str]
"""Signature for masking functions: ``(text, mask_char) -> masked_text``."""

NUMERIC_LABELS: frozenset[str] = frozenset(
    {
        "credit_card",
        "phone",
        "phone_international",
        "us_phone",
        "fr_phone",
        "de_phone",
        "ssn",
        "us_ssn",
        "fr_ssn",
        "iban",
        "eu_iban",
        "uk_nhs",
        "us_ein",
        "us_bank_routing",
        "ip_address",
    }
)


def mask_email(text: str, mask_char: str = "*") -> str:
    """``j***@email.com`` — keep first char of local part + domain."""
    match = re.match(r"^(.)(.*?)(@.+)$", text)
    if not match:
        return mask_default(text, mask_char)
    first, middle, domain = match.groups()
    return first + mask_char * len(middle) + domain


def mask_numeric(text: str, mask_char: str = "*", visible_chars: int = 4) -> str:
    """``****4567`` — keep last ``visible_chars`` digits."""
    digits = re.sub(r"\D", "", text)
    if len(digits) <= visible_chars:
        return text
    visible = digits[-visible_chars:]
    masked_count = len(digits) - visible_chars
    return mask_char * masked_count + visible


def mask_default(text: str, mask_char: str = "*") -> str:
    """``P******`` — keep first character, mask the rest."""
    if len(text) <= 1:
        return text
    return text[0] + mask_char * (len(text) - 1)


def _build_default_strategies(mask_char: str, visible_chars: int) -> dict[str, MaskFn]:
    """Build the default label → mask function mapping.

    * Labels containing ``"email"`` → :func:`mask_email`
    * Labels in :data:`NUMERIC_LABELS` → :func:`mask_numeric`
    """
    strategies: dict[str, MaskFn] = {"email": mask_email}

    for label in NUMERIC_LABELS:
        strategies[label] = lambda t, mc=mask_char, vc=visible_chars: mask_numeric(
            t, mc, vc
        )

    return strategies


class MaskPlaceholderFactory(AnyPlaceholderFactory[PreservesShape]):
    """Factory that generates partially masked tokens preserving some original characters.

    Uses a configurable ``strategies`` mapping from label (lowercase) to
    a masking function ``(text, mask_char) -> str``.  Labels not present
    in the mapping fall back to :func:`mask_default`.  Labels containing
    ``"email"`` are automatically routed to :func:`mask_email` unless
    overridden.

    Built-in defaults:

    * **Email** labels: :func:`mask_email` → ``j***@email.com``
    * **Numeric** labels: :func:`mask_numeric` → ``****4567``
    * **Everything else**: :func:`mask_default` → ``P******``

    Args:
        mask_char: Character used for masking.  Defaults to ``"*"``.
        visible_chars: Number of characters to keep visible for the
            default numeric strategy.  Defaults to 4.
        strategies: Optional dict mapping lowercase labels to masking
            functions.  Merged on top of the built-in defaults.

    Example:
        >>> from piighost.models import Detection, Entity, Span
        >>> factory = MaskPlaceholderFactory()
        >>> e = Entity(detections=(Detection(text="patrick@email.com", label="EMAIL", position=Span(0, 17), confidence=0.9),))
        >>> factory.create([e])[e]
        'p***@email.com'
    """

    _mask_char: str
    _strategies: dict[str, MaskFn]

    def __init__(
        self,
        mask_char: str = "*",
        visible_chars: int = 4,
        strategies: dict[str, MaskFn] | None = None,
    ) -> None:
        if strategies is None:
            strategies = _build_default_strategies(mask_char, visible_chars)
        else:
            strategies = {k.lower(): v for k, v in strategies.items()}

        self._mask_char = mask_char
        self._strategies = strategies

    def create(self, entities: list[Entity]) -> dict[Entity, str]:
        """Create partially masked tokens for all entities.

        Args:
            entities: The entities to create tokens for.

        Returns:
            A dict mapping each entity to a masked token.
        """
        return {entity: self._mask(entity) for entity in entities}

    def _mask(self, entity: Entity) -> str:
        text = entity.detections[0].text
        label_lower = entity.label.lower()

        # Explicit strategy match takes priority.
        if label_lower in self._strategies:
            return self._strategies[label_lower](text, self._mask_char)

        return mask_default(text, self._mask_char)
