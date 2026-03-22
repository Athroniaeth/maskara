"""Session-aware anonymization pipeline with caching.

The ``AnonymizationPipeline`` sits between the stateless ``Anonymizer``
and any consumer (middleware, API handler, CLI).  It owns:

* A ``PlaceholderStore`` (async) for cross-session persistence.
* An in-memory ``_results`` registry for fast, synchronous
  deanonymization / reanonymization within the current session.

Public API:

* ``anonymize`` (async) – detect & replace PII, cache the result.
* ``deanonymize_text`` (sync) – replace placeholder tags with originals.
* ``reanonymize_text`` (sync) – replace originals back to tags.
"""

import hashlib
import logging
from typing import Protocol

from piighost.anonymizer.anonymizer import Anonymizer
from piighost.anonymizer.models import AnonymizationResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Store abstraction (DI point for Redis / in-memory / etc.)
# ---------------------------------------------------------------------------


class PlaceholderStore(Protocol):
    """Async key-value store for ``AnonymizationResult`` objects.

    Implementations may use Redis, an in-memory dict, or any other
    backend.  The pipeline depends only on this protocol.
    """

    async def get(self, key: str) -> AnonymizationResult | None:
        """Retrieve a stored result by key.

        Args:
            key: A deterministic hash of a text.

        Returns:
            The stored result, or *None* if the key is unknown.
        """
        ...  # pragma: no cover

    async def set(self, key: str, result: AnonymizationResult) -> None:
        """Persist an anonymization result.

        Args:
            key: A deterministic hash of a text.
            result: The result to store.
        """
        ...  # pragma: no cover


class InMemoryPlaceholderStore:
    """Simple in-memory store – suitable for tests and single-process use."""

    def __init__(self) -> None:
        self._data: dict[str, AnonymizationResult] = {}

    async def get(self, key: str) -> AnonymizationResult | None:
        """Return the stored result or *None*."""
        return self._data.get(key)

    async def set(self, key: str, result: AnonymizationResult) -> None:
        """Store an anonymization result."""
        self._data[key] = result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _text_hash(text: str) -> str:
    """Return a deterministic SHA-256 hex digest for *text*.

    Args:
        text: The source string.

    Returns:
        A hex digest string.
    """
    return hashlib.sha256(text.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class AnonymizationPipeline:
    """Session-aware anonymization with caching and bidirectional lookup.

    The pipeline wraps a stateless ``Anonymizer`` and adds:

    * **Caching** – each ``AnonymizationResult`` is stored in the
      ``PlaceholderStore`` under the hash of the original text, for
      cross-session persistence.
    * **In-memory registry** – results are also kept in ``_results``
      so that ``deanonymize_text`` and ``reanonymize_text`` can work
      synchronously without hitting the store.

    Args:
        anonymizer: The stateless anonymization engine.
        store: Async key-value backend.  Defaults to
            ``InMemoryPlaceholderStore``.

    Example:
        >>> pipeline = AnonymizationPipeline(anonymizer=my_anonymizer)
        >>> result = await pipeline.anonymize("Patrick habite a Paris.")
        >>> result.anonymized_text
        '<<PERSON_1>> habite a <<LOCATION_1>>.'
        >>> pipeline.deanonymize_text("Cherche <<PERSON_1>>")
        'Cherche Patrick'
        >>> pipeline.reanonymize_text("Resultat pour Patrick a Paris")
        'Resultat pour <<PERSON_1>> a <<LOCATION_1>>'
    """

    def __init__(
        self,
        anonymizer: Anonymizer,
        store: PlaceholderStore | None = None,
    ) -> None:
        self._anonymizer = anonymizer
        self._store = store or InMemoryPlaceholderStore()
        self._results: list[AnonymizationResult] = []

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    async def anonymize(self, text: str) -> AnonymizationResult:
        """Anonymise *text*, cache the result, and register it.

        If the exact text has already been processed (cache hit), the
        stored result is returned and re-registered in the in-memory
        registry if absent.

        Args:
            text: The source string.

        Returns:
            The ``AnonymizationResult`` (possibly cached).
        """
        key = _text_hash(text)
        cached = await self._store.get(key)

        if cached is not None:
            self._register(cached)
            return cached

        result = self._anonymizer.anonymize(text)

        if result.anonymized_text != text:
            await self._store.set(key, result)
            self._register(result)
            logger.debug(
                "Anonymised text (hash=%s): %d placeholder(s)",
                key[:12],
                len(result.placeholders),
            )

        return result

    def deanonymize_text(self, text: str) -> str:
        """Replace every known placeholder tag in *text* with its original.

        This performs simple string replacement (not span-based) so it
        works on *any* string derived from an anonymised text including
        LLM-generated tool-call arguments.

        Args:
            text: A string potentially containing placeholder tags.

        Returns:
            The string with placeholders restored to original values.
        """
        for result in self._results:
            for placeholder in result.placeholders:
                text = text.replace(placeholder.replacement, placeholder.original)
        return text

    def deanonymize_value(self, value: str) -> str:
        """Resolve a single value that may be a placeholder tag or contain one.

        Intended for individual tool-call argument values provided by the LLM,
        which sees only anonymized entities.  Works across all registered
        detectors and results accumulated in this session.

        Args:
            value: A string that may equal or contain a placeholder tag
                   (e.g. ``"<<PERSON_1>>"``).

        Returns:
            The original value if a matching placeholder is found, or *value*
            unchanged.
        """
        for result in self._results:
            for placeholder in result.placeholders:
                value = value.replace(placeholder.replacement, placeholder.original)
        return value

    def reanonymize_text(self, text: str) -> str:
        """Replace every known original value in *text* with its placeholder tag.

        This is the inverse of ``deanonymize_text``.
        """
        for result in self._results:
            for placeholder in result.placeholders:
                text = text.replace(placeholder.original, placeholder.replacement)
        return text

    @property
    def results(self) -> tuple[AnonymizationResult, ...]:
        """All results registered during this session (read-only)."""
        return tuple(self._results)

    # -----------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------

    def _register(self, result: AnonymizationResult) -> None:
        """Append *result* to the in-memory registry if not already present."""
        if result not in self._results:
            self._results.append(result)
