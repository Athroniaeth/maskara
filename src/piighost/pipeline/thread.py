"""Conversation-aware anonymization pipeline.

Wraps :class:`AnonymizationPipeline` with a :class:`ConversationMemory`
to accumulate entities across messages.  Provides ``deanonymize_with_ent``
and ``anonymize_with_ent`` for simple ``str.replace``-based operations
on any text containing known tokens or original values.

Conversation-scoped memory for accumulating entities across messages.

Stores all :class:`Entity` objects seen during a conversation, indexed
by message hash and deduplicated by ``(text.lower(), label)``.  The
``all_entities`` property returns a flat, append-only list used by the
pipeline to recreate consistent placeholder tokens across messages.
"""

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Protocol

from aiocache import BaseCache

from piighost.anonymizer import AnyAnonymizer
from piighost.detector import AnyDetector
from piighost.linker.entity import AnyEntityLinker
from piighost.models import Detection, Entity
from piighost.pipeline.base import (
    CACHE_KEY_ANONYMIZATION,
    CACHE_KEY_DETECTION,
    AnonymizationPipeline,
)
from piighost.placeholder import MaskPlaceholderFactory, RedactPlaceholderFactory
from piighost.resolver.entity import AnyEntityConflictResolver
from piighost.resolver.span import AnySpanConflictResolver
from piighost.utils import hash_sha256

_current_thread_id: ContextVar[str] = ContextVar(
    "piighost_current_thread_id", default="default"
)
"""Active thread id for the running coroutine.

Used by :class:`ThreadAnonymizationPipeline` to propagate the ``thread_id``
argument down to the cache-key helpers without mutating instance state,
which would be unsafe when several coroutines share one pipeline.
"""


class AnyConversationMemory(Protocol):
    """Protocol for conversation memory implementations."""

    entities_by_hash: dict[str, list[Entity]]

    @property
    def all_entities(self) -> list[Entity]: ...

    def record(self, text_hash: str, entities: list[Entity]) -> None: ...


@dataclass
class ConversationMemory:
    """In-memory conversation memory that accumulates entities across messages.

    Entities are stored per message hash and deduplicated by canonical
    identity ``(text.lower(), label)``.  The ``all_entities`` property
    flattens all stored entities in insertion order, skipping duplicates.

    An internal canonical index makes ``record()`` lookups O(1) instead
    of scanning every previously-seen entity.  The index points at the
    current slot of each canonical entity inside ``entities_by_hash``
    so that merging a new surface-form variant stays O(1) too.

    Example:
        >>> from piighost.models import Detection, Entity, Span
        >>> memory = ConversationMemory()
        >>> e = Entity(detections=(Detection("Patrick", "PERSON", Span(0, 7), 0.9),))
        >>> memory.record("abc123", [e])
        >>> memory.all_entities
        [Entity(detections=(Detection(text='Patrick', label='PERSON', position=Span(start_pos=0, end_pos=7), confidence=0.9),))]
    """

    entities_by_hash: dict[str, list[Entity]] = field(default_factory=dict)
    _canonical_index: dict[tuple[str, str], tuple[str, int]] = field(
        default_factory=dict, repr=False, compare=False
    )

    def record(self, text_hash: str, entities: list[Entity]) -> None:
        """Record entities for a message, deduplicating against known ones.

        Known entities are not duplicated but their new text variants
        (e.g. ``"france"`` when ``"France"`` already exists) are merged
        into the existing entity so that ``anonymize_with_ent`` can
        replace all surface forms.

        Args:
            text_hash: SHA-256 hash of the original text.
            entities: Entities detected in that message.
        """
        bucket = self.entities_by_hash.setdefault(text_hash, [])

        for entity in entities:
            key = self._key(entity)
            slot = self._canonical_index.get(key)
            if slot is None:
                bucket.append(entity)
                self._canonical_index[key] = (text_hash, len(bucket) - 1)
            else:
                self._merge_variant(slot, entity)

    @property
    def all_entities(self) -> list[Entity]:
        """Flat deduplicated list of all entities, in insertion order."""
        return [
            self.entities_by_hash[text_hash][index]
            for text_hash, index in self._canonical_index.values()
        ]

    @staticmethod
    def _key(entity: Entity) -> tuple[str, str]:
        """Canonical identity used for deduplication."""
        return entity.detections[0].text.lower(), entity.label

    def _merge_variant(self, slot: tuple[str, int], entity: Entity) -> None:
        """Merge a new surface-form variant into the entity at *slot*.

        Detections whose exact ``text`` already belongs to the stored
        entity are skipped; anything new is appended so that
        ``anonymize_with_ent`` can replace every observed spelling.
        """
        text_hash, index = slot
        bucket = self.entities_by_hash[text_hash]
        existing = bucket[index]
        existing_texts = {d.text for d in existing.detections}
        new_dets = tuple(d for d in entity.detections if d.text not in existing_texts)
        if new_dets:
            bucket[index] = Entity(detections=existing.detections + new_dets)


class ThreadAnonymizationPipeline(AnonymizationPipeline):
    """Adds conversation memory on top of ``AnonymizationPipeline``.

    Delegates detection, resolution, and span-based anonymization to the
    base pipeline.  After each ``anonymize()`` call, entities are recorded
    in memory so that ``deanonymize_with_ent`` / ``anonymize_with_ent``
    can operate on *any* text via ``str.replace``.

    Memory and cache are isolated per ``thread_id`` passed to each
    method.  Cache keys are prefixed with the thread id so that a
    shared Redis backend keeps conversations separate.  The default
    thread id is ``"default"``.

    Args:
        detector: The entity detector to use.
        span_resolver: The span conflict resolver to use.
        entity_linker: The entity linker to use.
        entity_resolver: The entity conflict resolver to use.
        anonymizer: The anonymizer to use for span-based replacement.
        cache: Optional aiocache backend.  Defaults to a fresh
            ``SimpleMemoryCache``.
        cache_ttl: Time-to-live in seconds for every cache entry the
            pipeline writes.  ``None`` keeps entries forever.
    """

    def __init__(
        self,
        detector: AnyDetector,
        anonymizer: AnyAnonymizer,
        entity_linker: AnyEntityLinker | None = None,
        entity_resolver: AnyEntityConflictResolver | None = None,
        span_resolver: AnySpanConflictResolver | None = None,
        cache: BaseCache | None = None,
        cache_ttl: int | None = None,
    ) -> None:
        factory = anonymizer.ph_factory
        if isinstance(factory, (RedactPlaceholderFactory, MaskPlaceholderFactory)):
            raise ValueError(
                f"{type(factory).__name__} cannot be used with "
                f"ThreadAnonymizationPipeline because it produces "
                f"non-unique tokens that cannot be deanonymized. "
                f"Use CounterPlaceholderFactory or HashPlaceholderFactory instead."
            )

        super().__init__(
            detector,
            span_resolver=span_resolver,
            entity_linker=entity_linker,
            entity_resolver=entity_resolver,
            anonymizer=anonymizer,
            cache=cache,
            cache_ttl=cache_ttl,
        )

        self._memories: dict[str, ConversationMemory] = {}

    def get_memory(self, thread_id: str = "default") -> ConversationMemory:
        """Return the memory for *thread_id* (created on first access)."""
        if thread_id not in self._memories:
            self._memories[thread_id] = ConversationMemory()
        return self._memories[thread_id]

    def get_resolved_entities(self, thread_id: str = "default") -> list[Entity]:
        """All entities from the thread's memory, merged by the entity resolver."""
        return self._entity_resolver.resolve(self.get_memory(thread_id).all_entities)

    # ------------------------------------------------------------------
    # Cache key helpers — prefix with thread_id for isolation
    # ------------------------------------------------------------------

    @staticmethod
    def _thread_key(thread_id: str, key: str) -> str:
        """Prefix a cache key with the given thread id."""
        return f"{thread_id}:{key}"

    async def override_detections(
        self,
        text: str,
        detections: list[Detection],
        thread_id: str = "default",
    ) -> None:
        """Override cached detection results for user corrections.

        Overwrites the detection cache entry for the given text so that
        subsequent calls to ``anonymize()`` use the corrected detections
        instead of re-running the detector.

        Args:
            text: The original text whose detections should be overridden.
            detections: The corrected list of detections.
            thread_id: Thread identifier for cache isolation.

        Raises:
            RuntimeError: If no cache backend is configured.
        """
        if self._cache is None:
            raise RuntimeError("Cannot override detections without a cache backend")

        cache_key = self._thread_key(
            thread_id, f"{CACHE_KEY_DETECTION}:{hash_sha256(text)}"
        )
        value = self._serialize_detections(detections)
        await self._cache.set(cache_key, value, ttl=self._cache_ttl)

    async def _cached_detect(self, text: str) -> list[Detection]:
        """Detect entities, using thread-scoped cache if available."""
        if self._cache is None:
            return await self._detector.detect(text)

        thread_id = _current_thread_id.get()
        cache_key = self._thread_key(
            thread_id, f"{CACHE_KEY_DETECTION}:{hash_sha256(text)}"
        )
        cached = await self._cache.get(cache_key)

        if cached is not None:
            return self._deserialize_detections(cached)

        detections = await self._detector.detect(text)
        value = self._serialize_detections(detections)
        await self._cache.set(cache_key, value, ttl=self._cache_ttl)
        return detections

    async def _store_mapping(
        self,
        original: str,
        anonymized: str,
        entities: list[Entity],
    ) -> None:
        """Store anonymization mapping under a thread-scoped key."""
        if self._cache is None:
            return

        thread_id = _current_thread_id.get()
        serialized_entities = self._serialize_entities(entities)
        key = self._thread_key(
            thread_id, f"{CACHE_KEY_ANONYMIZATION}:{hash_sha256(anonymized)}"
        )

        await self._cache.set(
            key,
            {
                "original": original,
                "entities": serialized_entities,
            },
            ttl=self._cache_ttl,
        )

    # ------------------------------------------------------------------
    # Anonymize / deanonymize
    # ------------------------------------------------------------------

    async def deanonymize(
        self,
        anonymized_text: str,
        thread_id: str = "default",
    ) -> tuple[str, list[Entity]]:
        """Return the cached original text directly.

        The base pipeline reconstructs the original via span-based
        replacement, but in a conversation context entity detections
        carry positions from *different* messages.  Using the cached
        original avoids mismatches.

        Args:
            anonymized_text: The anonymized text to restore.
            thread_id: Thread identifier for cache isolation.

        Returns:
            The original text and the entities used for anonymization.

        Raises:
            CacheMissError: If *anonymized_text* was never produced
                by this pipeline.
        """
        from piighost.exceptions import CacheMissError

        key = self._thread_key(
            thread_id, f"{CACHE_KEY_ANONYMIZATION}:{hash_sha256(anonymized_text)}"
        )
        cached = await self._cache_get(key)

        if cached is None:
            raise CacheMissError(f"No anonymization mapping cached for hash {key!r}")

        entities = self._deserialize_entities(cached["entities"])
        return cached["original"], entities

    async def anonymize(
        self,
        text: str,
        thread_id: str = "default",
    ) -> tuple[str, list[Entity]]:
        """Run detection, record entities in memory, then anonymize.

        Uses ``all_entities`` from memory for token creation so that
        counters stay consistent across messages.

        Args:
            text: The original text to anonymize.
            thread_id: Thread identifier for memory and cache isolation.

        Returns:
            A tuple of (anonymized text, entities used for anonymization).
        """
        token = _current_thread_id.set(thread_id)
        try:
            memory = self.get_memory(thread_id)

            entities = await self.detect_entities(text)
            entities = self._entity_linker.link_entities(
                entities,
                memory.all_entities,
            )
            memory.record(hash_sha256(text), entities)
            result = self.anonymize_with_ent(text, thread_id=thread_id)

            await self._store_mapping(text, result, entities)
            return result, entities
        finally:
            _current_thread_id.reset(token)

    async def deanonymize_with_ent(
        self,
        text: str,
        thread_id: str = "default",
    ) -> str:
        """Replace all known tokens with original values via ``str.replace``.

        Works on any text containing tokens, even text never anonymized
        by this pipeline (e.g. LLM-generated output, tool arguments).
        Tokens are replaced **longest-first** to avoid partial matches.

        The result is stored in the cache so that ``deanonymize()`` can
        look it up later.

        Args:
            text: Text potentially containing placeholder tokens.
            thread_id: Thread identifier for memory and cache isolation.

        Returns:
            Text with tokens replaced by original values.
        """
        resolved = self.get_resolved_entities(thread_id)

        if not resolved:
            return text

        tokens = self.ph_factory.create(resolved)

        anonymized = text
        for entity, token in sorted(
            tokens.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        ):
            canonical = entity.detections[0].text
            text = text.replace(token, canonical)

        cv_token = _current_thread_id.set(thread_id)
        try:
            await self._store_mapping(text, anonymized, resolved)
        finally:
            _current_thread_id.reset(cv_token)
        return text

    def anonymize_with_ent(
        self,
        text: str,
        thread_id: str = "default",
    ) -> str:
        """Replace all known original values with tokens via ``str.replace``.

        Replaces **all** spelling variants of each entity (not just the
        canonical form).  Values are replaced **longest-first** to avoid
        partial matches.

        Args:
            text: Text potentially containing original PII values.
            thread_id: Thread identifier for memory isolation.

        Returns:
            Text with original values replaced by tokens.
        """
        resolved = self.get_resolved_entities(thread_id)

        if not resolved:
            return text

        tokens = self.ph_factory.create(resolved)

        # Collect all (detection_text, token) pairs for all variants.
        replacements: list[tuple[str, str]] = []
        for entity, token in tokens.items():
            for detection in entity.detections:
                replacements.append((detection.text, token))

        # Sort by original text length descending (longest-first).
        replacements.sort(key=lambda x: len(x[0]), reverse=True)

        for original, token in replacements:
            text = text.replace(original, token)
        return text
