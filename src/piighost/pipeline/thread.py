"""Conversation-aware anonymization pipeline.

Wraps :class:`AnonymizationPipeline` with a :class:`ConversationMemory`
to accumulate entities across messages.  Provides ``deanonymize_with_ent``
and ``anonymize_with_ent`` for single-pass regex replacement on any text
containing known tokens or original values.

Conversation-scoped memory for accumulating entities across messages.

Stores all :class:`Entity` objects seen during a conversation, indexed
by message hash and deduplicated by ``(text.lower(), label)``.  The
``all_entities`` property returns a flat, append-only list used by the
pipeline to recreate consistent placeholder tokens across messages.
"""

import re
import time
import warnings
from collections import OrderedDict
from contextvars import ContextVar
from typing import Any, Mapping, Protocol

from typing_extensions import TypeVar

from aiocache import BaseCache, SimpleMemoryCache

from piighost.anonymizer import AnyAnonymizer
from piighost.detector import AnyDetector
from piighost.exceptions import PIIGhostConfigWarning, PIIRemainingError
from piighost.guard import AnyGuardRail
from piighost.linker.entity import AnyEntityLinker
from piighost.models import Detection, Entity
from piighost.observation.base import AbstractObservationService, AbstractSpan
from piighost.pipeline.base import (
    CACHE_KEY_ANONYMIZATION,
    CACHE_KEY_DETECTION,
    AnonymizationPipeline,
    _detection_to_dict,
    _entity_to_dict,
)
from piighost.placeholder import AnyPlaceholderFactory
from piighost.placeholder_tags import (
    PlaceholderPreservation,
    PreservesIdentity,
    get_preservation_tag,
)
from piighost.resolver.entity import AnyEntityConflictResolver
from piighost.resolver.span import AnySpanConflictResolver
from piighost.utils import hash_sha256

PreservationT = TypeVar(
    "PreservationT",
    bound=PlaceholderPreservation,
    default=PlaceholderPreservation,
)

_current_thread_id: ContextVar[str] = ContextVar(
    "piighost_current_thread_id", default="default"
)
"""Active thread id for the running coroutine.

Used by :class:`ThreadAnonymizationPipeline` to propagate the ``thread_id``
argument down to the cache-key helpers without mutating instance state,
which would be unsafe when several coroutines share one pipeline.
"""

_multi_instance_warning_emitted: bool = False
"""Process-wide flag so the unshared-cache warning fires at most once.

Module-level rather than class-level: the semantics are "has any pipeline
in this process already warned?", which is module state, not class state.
"""


def _replace_longest_first(text: str, pairs: list[tuple[str, str]]) -> str:
    """Replace every *source* with its *target* in one regex pass.

    Sources are emitted longest-first in the alternation so that a match
    on a longer source wins over any shorter prefix.  Duplicate sources
    are collapsed: the first mapping wins.  Returns *text* unchanged
    when ``pairs`` is empty.
    """
    mapping: dict[str, str] = {}
    for source, target in pairs:
        if source and source not in mapping:
            mapping[source] = target

    if not mapping:
        return text

    sources = sorted(mapping, key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(s) for s in sources))
    return pattern.sub(lambda m: mapping[m.group(0)], text)


class AnyConversationMemory(Protocol):
    """Protocol for conversation memory implementations."""

    entities_by_hash: dict[str, list[Entity]]

    @property
    def all_entities(self) -> list[Entity]: ...

    def record(self, text_hash: str, entities: list[Entity]) -> None: ...


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

    def __init__(
        self,
        entities_by_hash: dict[str, list[Entity]] | None = None,
    ) -> None:
        self.entities_by_hash: dict[str, list[Entity]] = (
            entities_by_hash if entities_by_hash is not None else {}
        )
        self._canonical_index: dict[tuple[str, str], tuple[str, int]] = {}

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


class ThreadAnonymizationPipeline(AnonymizationPipeline[PreservationT]):
    """Adds conversation memory on top of ``AnonymizationPipeline``.

    Delegates detection, resolution, and span-based anonymization to the
    base pipeline.  After each ``anonymize()`` call, entities are recorded
    in memory so that ``deanonymize_with_ent`` / ``anonymize_with_ent``
    can operate on *any* text via a single regex-alternation pass.

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
        max_threads: Maximum number of conversation memories kept in
            RAM.  When a new thread is created past the cap, the least
            recently used memory is evicted.  ``None`` (default)
            disables the cap; use it with caution on long-running
            servers that juggle many conversations.
    """

    def __init__(
        self,
        detector: AnyDetector,
        anonymizer: AnyAnonymizer[PreservationT],
        entity_linker: AnyEntityLinker | None = None,
        entity_resolver: AnyEntityConflictResolver | None = None,
        span_resolver: AnySpanConflictResolver | None = None,
        guard_rail: AnyGuardRail | None = None,
        cache: BaseCache | None = None,
        cache_ttl: int | None = None,
        max_threads: int | None = None,
        observation: AbstractObservationService | None = None,
        observation_ph_factory: AnyPlaceholderFactory | None = None,
    ) -> None:
        if max_threads is not None and max_threads <= 0:
            raise ValueError(f"max_threads must be positive or None, got {max_threads}")
        self._reject_non_identity_factory(anonymizer.ph_factory)

        super().__init__(
            detector,
            span_resolver=span_resolver,
            entity_linker=entity_linker,
            entity_resolver=entity_resolver,
            anonymizer=anonymizer,
            guard_rail=guard_rail,
            cache=cache,
            cache_ttl=cache_ttl,
            observation=observation,
            observation_ph_factory=observation_ph_factory,
        )

        self._memories: OrderedDict[str, ConversationMemory] = OrderedDict()
        self._max_threads = max_threads
        self._maybe_warn_unshared_cache()

    def _maybe_warn_unshared_cache(self) -> None:
        """Warn once per process when the active cache is process-local.

        Multi-instance deployments behind a load balancer need a shared
        backend, otherwise the same ``thread_id`` routed to two workers
        sees inconsistent placeholders mid-conversation.  The warning
        focuses on correctness (cross-worker placeholder consistency),
        not performance.
        """
        global _multi_instance_warning_emitted
        if _multi_instance_warning_emitted:
            return
        if not isinstance(self._cache, SimpleMemoryCache):
            return
        _multi_instance_warning_emitted = True
        warnings.warn(
            "ThreadAnonymizationPipeline is using a process-local cache "
            "(SimpleMemoryCache). In a multi-instance deployment behind a "
            "load balancer, the placeholder mapping is not shared across "
            "workers: the same thread_id routed to two workers will see "
            "Patrick assigned to <<PERSON:1>> on one worker and "
            "<<PERSON:2>> on the next, breaking placeholder consistency "
            "mid-conversation. For multi-worker deployments, configure a "
            "shared cache backend (e.g. RedisCache). See the "
            "'Multi-instance deployment' page in the documentation. "
            "Silence this warning with "
            "warnings.filterwarnings('ignore', category=PIIGhostConfigWarning).",
            PIIGhostConfigWarning,
            stacklevel=3,
        )

    @staticmethod
    def _reject_non_identity_factory(factory: object) -> None:
        """Raise if the factory does not advertise ``PreservesIdentity``.

        Mirrors the static-typing constraint: the middleware and
        conversation-memory logic both assume each entity maps to a
        unique, reversible token, so factories tagged with a weaker
        preservation level are rejected upfront.
        """
        tag = get_preservation_tag(factory)
        if tag is None:
            # Untyped factory: accept but trust the caller. Preserves
            # backwards-compat with user-defined factories that haven't
            # adopted the phantom-tag system yet.
            return
        if not issubclass(tag, PreservesIdentity):
            raise ValueError(
                f"{type(factory).__name__} is tagged "
                f"'{tag.__name__}' and cannot be used with "
                f"ThreadAnonymizationPipeline, which requires a factory "
                f"tagged 'PreservesIdentity' so tokens can be "
                f"deanonymised per-entity. "
                f"Use LabelCounterPlaceholderFactory or LabelHashPlaceholderFactory instead."
            )

    def get_memory(self, thread_id: str = "default") -> ConversationMemory:
        """Return the memory for *thread_id* (created on first access).

        If ``max_threads`` is set, accessing a thread refreshes its LRU
        position and creating a new one evicts the least recently used
        memory.
        """
        memory = self._memories.get(thread_id)
        if memory is not None:
            self._memories.move_to_end(thread_id)
            return memory

        memory = ConversationMemory()
        self._memories[thread_id] = memory
        if self._max_threads is not None and len(self._memories) > self._max_threads:
            self._memories.popitem(last=False)
        return memory

    def clear_memory(self, thread_id: str) -> None:
        """Drop the memory for *thread_id* (no-op if unknown).

        Callers should invoke this when a conversation ends so the
        pipeline does not retain its entities indefinitely.
        """
        self._memories.pop(thread_id, None)

    def clear_all_memories(self) -> None:
        """Drop every conversation memory tracked by the pipeline."""
        self._memories.clear()

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
        *,
        metadata: Mapping[str, Any] | None = None,
        root_span: AbstractSpan | None = None,
    ) -> tuple[str, list[Entity]]:
        """Run detection, record entities in memory, then anonymize.

        Uses ``all_entities`` from memory for token creation so that
        counters stay consistent across messages.

        Args:
            text: The original text to anonymize.
            thread_id: Thread identifier for memory and cache isolation.
            metadata: Optional metadata forwarded to the observation trace.
            root_span: Caller-supplied root span. When provided the pipeline
                nests its stage observations under it and does not create a
                new root span from the configured observation service.

        Returns:
            A tuple of (anonymized text, entities used for anonymization).
        """
        if root_span is not None:
            return await self._anonymize_with_span(
                text,
                root_span,
                thread_id=thread_id,
                metadata=metadata,
            )

        # Root span input is filled in retroactively from
        # ``_anonymize_with_span`` once detections are available, so the
        # observation factory can render the obs-redacted form rather
        # than swallowing the whole text under one sentinel.
        with self._observation.start_as_current_span(
            name="piighost.anonymize_pipeline",
            session_id=thread_id if thread_id != "default" else None,
            metadata=dict(metadata) if metadata else None,
        ) as auto_root:
            return await self._anonymize_with_span(
                text,
                auto_root,
                thread_id=thread_id,
                metadata=metadata,
            )

    async def _anonymize_with_span(
        self,
        text: str,
        root_span: AbstractSpan,
        *,
        metadata: Mapping[str, Any] | None,
        thread_id: str = "default",
    ) -> tuple[str, list[Entity]]:
        """Execute all conversation-aware pipeline stages, emitting child observations.

        ``thread_id`` is keyword-only and defaults to ``"default"`` so
        the override stays compatible with the base
        ``_anonymize_with_span`` signature.  In practice, the override
        is always reached through this class' own ``anonymize`` which
        forwards the explicit thread id, so the default only matters
        for callers that bypass that path.
        """
        token = _current_thread_id.set(thread_id)
        try:
            memory = self.get_memory(thread_id)

            # Detect
            with root_span.start_as_current_observation(
                name="piighost.detect",
                as_type="tool",
            ) as span:
                detections = await self._cached_detect(text)
                det_token_map = self._obs_tokens_for_detections(detections)
                obs_text_pre_link = self._obs_anonymizer.anonymize(
                    text, [Entity(detections=(d,)) for d in detections]
                )
                root_span.update(input={"text": obs_text_pre_link})
                span.update(
                    input={"text": obs_text_pre_link},
                    output={
                        "detections": [
                            _detection_to_dict(d, token=det_token_map[d])
                            for d in detections
                        ]
                    },
                )
                detections = self._span_resolver.resolve(detections)
                time.sleep(0.001)

            # Link
            with root_span.start_as_current_observation(
                name="piighost.link",
                as_type="span",
            ) as span:
                entities = self._entity_linker.link(text, detections)
                entities = self._entity_resolver.resolve(entities)
                entities = self._entity_linker.link_entities(
                    entities,
                    memory.all_entities,
                )
                ent_tokens = self._obs_ph_factory.create(entities)
                span.update(
                    input={
                        "detections": [
                            _detection_to_dict(d, token=det_token_map[d])
                            for d in detections
                        ]
                    },
                    output={
                        "entities": [
                            _entity_to_dict(e, token=ent_tokens[e]) for e in entities
                        ]
                    },
                )
                time.sleep(0.001)

            memory.record(hash_sha256(text), entities)

            # Placeholder
            with root_span.start_as_current_observation(
                name="piighost.placeholder",
                as_type="tool",
            ) as span:
                result = self.anonymize_with_ent(text, thread_id=thread_id)
                obs_text = self._obs_anonymizer.anonymize(text, entities)
                span.update(
                    input={"text": obs_text, "entity_count": len(entities)},
                    output={"text": result},
                )
                time.sleep(0.001)

            # Guard
            with root_span.start_as_current_observation(
                name="piighost.guard",
                as_type="guardrail",
            ) as span:
                span.update(input={"text": result})
                try:
                    await self._guard_rail.check(result)
                except PIIRemainingError:
                    span.update(output={"passed": False})
                    raise
                span.update(output={"passed": True})
                time.sleep(0.001)

            root_span.update(
                output={"text": result, "entity_count": len(entities)},
            )

            await self._store_mapping(text, result, entities)
            return result, entities
        finally:
            _current_thread_id.reset(token)

    async def deanonymize_with_ent(
        self,
        text: str,
        thread_id: str = "default",
    ) -> str:
        """Replace all known tokens with original values in a single pass.

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
        pairs = [(token, entity.detections[0].text) for entity, token in tokens.items()]

        anonymized = text
        restored = _replace_longest_first(text, pairs)

        cv_token = _current_thread_id.set(thread_id)
        try:
            await self._store_mapping(restored, anonymized, resolved)
        finally:
            _current_thread_id.reset(cv_token)
        return restored

    def anonymize_with_ent(
        self,
        text: str,
        thread_id: str = "default",
    ) -> str:
        """Replace all known original values with tokens in a single pass.

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

        pairs: list[tuple[str, str]] = []
        for entity, token in tokens.items():
            for detection in entity.detections:
                pairs.append((detection.text, token))

        return _replace_longest_first(text, pairs)
