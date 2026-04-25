"""Realistic-format placeholder factory backed by a hash.

Produces values that look like genuine data (e.g. ``a1b2c3d4@anonymized.local``
for an email, ``Patient_a1b2c3d4`` for a name) so downstream tools that
validate the format keep working, while the content itself is a hash so
collisions with real-world values are impossible.

Unlike :class:`~piighost.ph_factory.faker.FakerPlaceholderFactory`, the
caller MUST register a strategy for every label the detector emits.
There is no implicit fallback: an unknown label raises
:class:`ValueError` at ``create()`` time, so configuration drift is
caught immediately rather than silently producing garbage tokens.
"""

import hashlib
from collections.abc import Callable

from piighost.models import Entity
from piighost.placeholder import AnyPlaceholderFactory
from piighost.placeholder_tags import PreservesLabeledIdentityHashed

HashedFn = Callable[[str], str]
"""Signature for a realistic-format strategy: ``(hash_value) -> token``.

The hash value is already truncated to the configured length. The
strategy embeds it in a label-appropriate envelope.
"""


def hashed_email(domain: str = "anonymized.local") -> HashedFn:
    """Strategy producing ``<hash>@<domain>`` tokens.

    Example:
        >>> hashed_email()("a1b2c3d4")
        'a1b2c3d4@anonymized.local'
    """
    return lambda h: f"{h}@{domain}"


def hashed_with_prefix(prefix: str) -> HashedFn:
    """Strategy producing ``<prefix>_<hash>`` tokens.

    Useful for names, identifiers, anything that is read as a single
    word with a recognisable prefix.

    Example:
        >>> hashed_with_prefix("Patient")("a1b2c3d4")
        'Patient_a1b2c3d4'
    """
    return lambda h: f"{prefix}_{h}"


def hashed_template(template: str) -> HashedFn:
    """Strategy producing tokens by substituting ``{hash}`` in a template.

    Example:
        >>> hashed_template("user-{hash}@example.com")("a1b2c3d4")
        'user-a1b2c3d4@example.com'
    """
    return lambda h: template.format(hash=h)


class RealisticHashPlaceholderFactory(
    AnyPlaceholderFactory[PreservesLabeledIdentityHashed]
):
    """Factory that emits realistic-looking tokens with hashed content.

    The output mimics the natural format of each PII type (email, name,
    identifier, …) so downstream tools that validate the format still
    accept the placeholder. The token's content is driven by a SHA-256
    hash of the canonical text, so it is unique per entity and cannot
    coincidentally match a real-world value (unlike
    :class:`~piighost.ph_factory.faker.FakerPlaceholderFactory`).

    Strategies are **mandatory** and have **no fallback**: every label
    your detector emits must have an entry in ``strategies`` (matched
    case-insensitively). An unknown label raises ``ValueError`` so a
    misconfigured pipeline is caught immediately.

    Args:
        strategies: Mapping from lower-cased label to a strategy
            ``(hash_value) -> token``. Must be non-empty.
        hash_length: Number of hex characters from the SHA-256 digest.
            Defaults to ``8``.

    Raises:
        ValueError: If ``strategies`` is empty, or at ``create()`` time
            if an entity carries a label absent from ``strategies``.

    Example:
        >>> from piighost.models import Detection, Entity, Span
        >>> from piighost.ph_factory.realistic import (
        ...     RealisticHashPlaceholderFactory,
        ...     hashed_email,
        ...     hashed_with_prefix,
        ... )
        >>> factory = RealisticHashPlaceholderFactory(
        ...     strategies={
        ...         "email": hashed_email("anonymized.local"),
        ...         "person": hashed_with_prefix("Patient"),
        ...     },
        ... )
        >>> e = Entity(detections=(Detection(text="patrick@mail.com", label="EMAIL", position=Span(0, 16), confidence=0.9),))
        >>> token = factory.create([e])[e]
        >>> token.endswith('@anonymized.local')
        True
    """

    _strategies: dict[str, HashedFn]
    _hash_length: int

    def __init__(
        self,
        strategies: dict[str, HashedFn],
        hash_length: int = 8,
    ) -> None:
        if not strategies:
            raise ValueError(
                "RealisticHashPlaceholderFactory requires at least one "
                "strategy. Provide a (label -> hashed_fn) mapping covering "
                "every label your detector emits."
            )
        # Normalise keys to lower-case once at construction time.
        self._strategies = {k.lower(): v for k, v in strategies.items()}
        self._hash_length = hash_length

    def create(self, entities: list[Entity]) -> dict[Entity, str]:
        """Create realistic-format hashed tokens for all entities.

        Args:
            entities: The entities to create tokens for.

        Returns:
            A dict mapping each entity to its formatted token.

        Raises:
            ValueError: If any entity carries a label that has no
                registered strategy.
        """
        result: dict[Entity, str] = {}

        for entity in entities:
            label = entity.label.lower()
            strategy = self._strategies.get(label)
            if strategy is None:
                known = ", ".join(sorted(self._strategies)) or "<none>"
                raise ValueError(
                    f"No strategy registered for label {entity.label!r}. "
                    f"Add it to the strategies mapping. "
                    f"Known labels: {known}."
                )
            canonical_text = entity.detections[0].text.lower()
            raw = f"{canonical_text}:{entity.label}"
            digest = hashlib.sha256(raw.encode()).hexdigest()[: self._hash_length]
            result[entity] = strategy(digest)

        return result


__all__ = [
    "HashedFn",
    "RealisticHashPlaceholderFactory",
    "hashed_email",
    "hashed_template",
    "hashed_with_prefix",
]
