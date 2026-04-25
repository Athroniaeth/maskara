"""Realistic-looking placeholder factories with a deterministic mechanism.

These factories sit between :class:`~piighost.placeholder.LabelHashPlaceholderFactory`
(opaque) and :class:`~piighost.ph_factory.faker.FakerPlaceholderFactory`
(random): the output looks like real data so downstream tools don't choke
on the format, but each entity carries a deterministic counter or hash
suffix so two distinct entities never collide.

Two factories are exposed:

* :class:`FakerCounterPlaceholderFactory` -- emits ``<base>:<counter>``
* :class:`FakerHashPlaceholderFactory`    -- emits ``<base>:<hash>``

Both follow the same configuration model: a strategies mapping where
each value is one of three forms (mode dispatch is done at runtime):

1. ``str`` without ``{hash}`` / ``{counter}`` placeholder
   -- treated as a base value; the factory appends ``:`` plus the
   counter or hash. Example: ``"John Doe"`` -> ``"John Doe:1"`` (Counter)
   or ``"John Doe:a1b2c3d4"`` (Hash).
2. ``str`` containing ``{hash}`` / ``{counter}``
   -- treated as a template; the placeholder is substituted with the
   counter or hash. Example: ``"{hash}@example.com"`` ->
   ``"a1b2c3d4@example.com"``.
3. ``Callable[[str], str]``
   -- arbitrary function receiving the counter (as ``str``) or the hash
   string and returning the formatted token. Use the ``fake_*`` helpers
   below to generate Faker-like values seeded by the hash for fields
   where neither base nor template can produce a valid value (IPs,
   phone numbers, IBANs, credit cards…).

Strategies are **mandatory** and have **no fallback**: an unknown label
raises :class:`ValueError` at ``create()`` time. This catches a
misconfigured pipeline immediately instead of silently producing
garbage tokens.
"""

import hashlib
import importlib.util
from collections.abc import Callable

from piighost.models import Entity
from piighost.placeholder import AnyPlaceholderFactory
from piighost.placeholder_tags import PreservesLabeledIdentityHashed

StrategyFn = Callable[[str], str]
"""Callable strategy: ``(counter_or_hash) -> token``."""

StrategyValue = str | StrategyFn
"""A strategy is either a base/template string or a callable."""


# ---------------------------------------------------------------------------
# Helpers: seed-Faker callable strategies
# ---------------------------------------------------------------------------


def _require_faker():
    if importlib.util.find_spec("faker") is None:
        raise ImportError(
            "The fake_* helpers require the optional Faker dependency. "
            "Install with: piighost[faker]"
        )


def fake_with_seed(method: str) -> StrategyFn:
    """Build a hash-seeded Faker strategy from a Faker method name.

    The returned callable takes a hex hash string, seeds a fresh
    ``Faker`` instance with the int value of that hash, and calls
    ``method`` on it. Output is deterministic per hash.

    Example:
        >>> ip_strategy = fake_with_seed("ipv4")
        >>> isinstance(ip_strategy("a1b2c3d4"), str)
        True
    """
    _require_faker()
    from faker import Faker

    def strategy(token: str) -> str:
        faker = Faker()
        # Seed deterministically from the token (hex hash or counter str).
        # int() handles both hex and decimal strings.
        try:
            seed = int(token, 16)
        except ValueError:
            seed = int(token)
        faker.seed_instance(seed)
        return getattr(faker, method)()

    return strategy


def fake_ip() -> StrategyFn:
    """Strategy that emits a deterministic Faker IPv4 from the hash."""
    return fake_with_seed("ipv4")


def fake_phone() -> StrategyFn:
    """Strategy that emits a deterministic Faker phone number from the hash."""
    return fake_with_seed("phone_number")


def fake_ssn() -> StrategyFn:
    """Strategy that emits a deterministic Faker SSN from the hash."""
    return fake_with_seed("ssn")


def fake_iban() -> StrategyFn:
    """Strategy that emits a deterministic Faker IBAN from the hash."""
    return fake_with_seed("iban")


def fake_credit_card() -> StrategyFn:
    """Strategy that emits a deterministic Faker credit-card number from the hash."""
    return fake_with_seed("credit_card_number")


def fake_url() -> StrategyFn:
    """Strategy that emits a deterministic Faker URL from the hash."""
    return fake_with_seed("url")


def fake_address() -> StrategyFn:
    """Strategy that emits a deterministic Faker address from the hash."""
    return fake_with_seed("address")


# ---------------------------------------------------------------------------
# Default strategies
# ---------------------------------------------------------------------------


def _default_strategies() -> dict[str, StrategyValue]:
    """Recommended defaults covering the most common labels.

    Helpers needing Faker are wrapped lazily so importing this module
    does not require Faker to be installed.
    """
    strategies: dict[str, StrategyValue] = {
        # Base mode: looks natural, suffix added by the factory.
        "person": "John Doe",
        "location": "Paris",
        "country": "France",
        "address": "12 rue de Paris",
        # Template mode: keeps a valid format.
        "email": "{hash}@example.com",
        "url": "https://example.com/{hash}",
    }
    # Callable mode: only registered if Faker is installed; users can
    # still register them manually after construction.
    if importlib.util.find_spec("faker") is not None:
        strategies.update(
            {
                "phone": fake_phone(),
                "phone_international": fake_phone(),
                "ip_address": fake_ip(),
                "ssn": fake_ssn(),
                "iban": fake_iban(),
                "credit_card": fake_credit_card(),
            }
        )
    return strategies


def _resolve_template_placeholder(strategies_kind: str) -> str:
    """Return the template placeholder name expected by each factory."""
    return "{counter}" if strategies_kind == "counter" else "{hash}"


def _apply_strategy(
    strategy: StrategyValue,
    token: str,
    placeholder: str,
) -> str:
    """Run the dispatch logic shared by Counter and Hash factories."""
    if callable(strategy):
        return strategy(token)
    if placeholder in strategy:
        return strategy.replace(placeholder, token)
    return f"{strategy}:{token}"


# ---------------------------------------------------------------------------
# FakerCounterPlaceholderFactory
# ---------------------------------------------------------------------------


class FakerCounterPlaceholderFactory(
    AnyPlaceholderFactory[PreservesLabeledIdentityHashed]
):
    """Realistic-looking placeholders with a sequential counter.

    Each entity gets ``base:counter`` (default mode), or a template
    expansion of ``{counter}``, or the result of a callable strategy.
    The counter is per-label (``person`` 1, 2, 3…; ``location`` 1, 2…).

    Args:
        strategies: Mapping from lower-cased label to a
            :data:`StrategyValue` (base str, template str with
            ``{counter}``, or callable). Must be non-empty.

    Raises:
        ValueError: If ``strategies`` is empty, or at ``create()`` time
            if an entity carries a label absent from ``strategies``.

    Example:
        >>> from piighost.models import Detection, Entity, Span
        >>> factory = FakerCounterPlaceholderFactory(
        ...     strategies={"person": "John Doe", "email": "{counter}@example.com"},
        ... )
        >>> e = Entity(detections=(Detection(text="Patrick", label="PERSON", position=Span(0, 7), confidence=0.9),))
        >>> factory.create([e])[e]
        'John Doe:1'
    """

    _strategies: dict[str, StrategyValue]

    def __init__(self, strategies: dict[str, StrategyValue] | None = None) -> None:
        if strategies is None:
            strategies = _default_strategies()
        if not strategies:
            raise ValueError(
                "FakerCounterPlaceholderFactory requires at least one "
                "strategy. Provide a (label -> base/template/callable) "
                "mapping covering every label your detector emits."
            )
        self._strategies = {k.lower(): v for k, v in strategies.items()}

    def create(self, entities: list[Entity]) -> dict[Entity, str]:
        """Apply per-label counter tokens to all entities.

        Raises:
            ValueError: If any entity carries a label that has no
                registered strategy.
        """
        result: dict[Entity, str] = {}
        counters: dict[str, int] = {}

        for entity in entities:
            label = entity.label.lower()
            if label not in self._strategies:
                _raise_unknown(entity.label, self._strategies)
            strategy = self._strategies[label]
            counters[label] = counters.get(label, 0) + 1
            counter_str = str(counters[label])
            result[entity] = _apply_strategy(strategy, counter_str, "{counter}")

        return result


# ---------------------------------------------------------------------------
# FakerHashPlaceholderFactory
# ---------------------------------------------------------------------------


class FakerHashPlaceholderFactory(
    AnyPlaceholderFactory[PreservesLabeledIdentityHashed]
):
    """Realistic-looking placeholders with a SHA-256 hash suffix.

    Each entity gets ``base:hash`` (default mode), or a template
    expansion of ``{hash}``, or the result of a callable strategy
    receiving the truncated hash. The hash is deterministic per
    ``(text, label)`` pair so the same entity always maps to the
    same placeholder.

    Args:
        strategies: Mapping from lower-cased label to a
            :data:`StrategyValue` (base str, template str with
            ``{hash}``, or callable). Must be non-empty.
        hash_length: Number of hex characters from the SHA-256 digest.
            Defaults to ``8``.

    Raises:
        ValueError: If ``strategies`` is empty, or at ``create()`` time
            if an entity carries a label absent from ``strategies``.

    Example:
        >>> from piighost.models import Detection, Entity, Span
        >>> factory = FakerHashPlaceholderFactory(
        ...     strategies={
        ...         "person": "John Doe",
        ...         "email":  "{hash}@example.com",
        ...     },
        ... )
        >>> e = Entity(detections=(Detection(text="Patrick", label="PERSON", position=Span(0, 7), confidence=0.9),))
        >>> token = factory.create([e])[e]
        >>> token.startswith('John Doe:')
        True
    """

    _strategies: dict[str, StrategyValue]
    _hash_length: int

    def __init__(
        self,
        strategies: dict[str, StrategyValue] | None = None,
        hash_length: int = 8,
    ) -> None:
        if strategies is None:
            strategies = _default_strategies()
        if not strategies:
            raise ValueError(
                "FakerHashPlaceholderFactory requires at least one "
                "strategy. Provide a (label -> base/template/callable) "
                "mapping covering every label your detector emits."
            )
        self._strategies = {k.lower(): v for k, v in strategies.items()}
        self._hash_length = hash_length

    def create(self, entities: list[Entity]) -> dict[Entity, str]:
        """Apply per-entity hashed tokens to all entities.

        Raises:
            ValueError: If any entity carries a label that has no
                registered strategy.
        """
        result: dict[Entity, str] = {}

        for entity in entities:
            label = entity.label.lower()
            if label not in self._strategies:
                _raise_unknown(entity.label, self._strategies)
            strategy = self._strategies[label]
            canonical_text = entity.detections[0].text.lower()
            raw = f"{canonical_text}:{entity.label}"
            digest = hashlib.sha256(raw.encode()).hexdigest()[: self._hash_length]
            result[entity] = _apply_strategy(strategy, digest, "{hash}")

        return result


def _raise_unknown(label: str, strategies: dict[str, StrategyValue]) -> None:
    known = ", ".join(sorted(strategies)) or "<none>"
    raise ValueError(
        f"No strategy registered for label {label!r}. "
        f"Add it to the strategies mapping. "
        f"Known labels: {known}."
    )


__all__ = [
    "FakerCounterPlaceholderFactory",
    "FakerHashPlaceholderFactory",
    "StrategyFn",
    "StrategyValue",
    "fake_address",
    "fake_credit_card",
    "fake_iban",
    "fake_ip",
    "fake_phone",
    "fake_ssn",
    "fake_url",
    "fake_with_seed",
]
