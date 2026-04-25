import hashlib
import re
from collections import defaultdict
from collections.abc import Callable
from typing import Protocol

from typing_extensions import TypeVar

from piighost.models import Entity
from piighost.placeholder_tags import (
    PlaceholderPreservation,
    PreservesIdentityOpaque,
    PreservesLabel,
    PreservesShape,
)

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


class CounterPlaceholderFactory(AnyPlaceholderFactory[PreservesIdentityOpaque]):
    """Factory that generates tokens like ``<<PERSON_1>>``, ``<<PERSON_2>>``.

    Each entity gets a unique counter per label. Two different PERSON
    entities get ``<<PERSON_1>>`` and ``<<PERSON_2>>``, while a LOCATION
    entity gets ``<<LOCATION_1>>``.

    Example:
        >>> from piighost.models import Detection, Entity, Span
        >>> factory = CounterPlaceholderFactory()
        >>> e = Entity(detections=(Detection(text="Patrick", label="PERSON", position=Span(0, 7), confidence=0.9),))
        >>> factory.create([e])[e]
        '<<PERSON_1>>'
    """

    def __init__(self): ...

    def create(self, entities: list[Entity]) -> dict[Entity, str]:
        """Create counter-based tokens for all entities.

        Args:
            entities: The entities to create tokens for.

        Returns:
            A dict mapping each entity to a token like ``"<<PERSON_1>>"``.
        """
        result: dict[Entity, str] = {}
        counters: dict[str, int] = defaultdict(int)

        for entity in entities:
            label = entity.label
            counters[label] += 1
            result[entity] = f"<<{label}_{counters[label]}>>"

        return result


class HashPlaceholderFactory(AnyPlaceholderFactory[PreservesIdentityOpaque]):
    """Factory that generates tokens like ``<PERSON:a1b2c3d4>``.

    Uses SHA-256 of the canonical text + label to produce a deterministic,
    opaque token. Same entity always produces the same hash.

    Args:
        hash_length: Number of hex characters to use from the hash.
            Defaults to 8.

    Example:
        >>> from piighost.models import Detection, Entity, Span
        >>> factory = HashPlaceholderFactory()
        >>> e = Entity(detections=(Detection(text="Patrick", label="PERSON", position=Span(0, 7), confidence=0.9),))
        >>> token = factory.create([e])[e]
        >>> token.startswith('<PERSON:') and token.endswith('>')
        True
    """

    _hash_length: int

    def __init__(self, hash_length: int = 8) -> None:
        self._hash_length = hash_length

    def create(self, entities: list[Entity]) -> dict[Entity, str]:
        """Create hash-based tokens for all entities.

        Args:
            entities: The entities to create tokens for.

        Returns:
            A dict mapping each entity to a token like ``"<PERSON:a1b2c3d4>"``.
        """
        result: dict[Entity, str] = {}

        for entity in entities:
            canonical_text = entity.detections[0].text.lower()
            label = entity.label
            raw = f"{canonical_text}:{label}"
            digest = hashlib.sha256(raw.encode()).hexdigest()[: self._hash_length]
            result[entity] = f"<{label}:{digest}>"

        return result


class RedactPlaceholderFactory(AnyPlaceholderFactory[PreservesLabel]):
    """Factory that generates tokens like ``<PERSON>``.

    All entities with the same label share the same token there is
    no discrimination between different PIIs of the same type.
    Reversible because ``deanonymize`` receives the entities with
    their original positions.

    Example:
        >>> from piighost.models import Detection, Entity, Span
        >>> factory = RedactPlaceholderFactory()
        >>> e = Entity(detections=(Detection(text="Patrick", label="PERSON", position=Span(0, 7), confidence=0.9),))
        >>> factory.create([e])[e]
        '<PERSON>'
    """

    def __init__(self): ...

    def create(self, entities: list[Entity]) -> dict[Entity, str]:
        """Create redact tokens for all entities.

        Args:
            entities: The entities to create tokens for.

        Returns:
            A dict mapping each entity to a token like ``"<PERSON>"``.
        """
        return {entity: f"<{entity.label}>" for entity in entities}


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
