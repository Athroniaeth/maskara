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

from dataclasses import dataclass, field
from typing import Protocol

from piighost.anonymizer import AnyAnonymizer
from piighost.detector import AnyDetector
from piighost.linker.entity import AnyEntityLinker
from piighost.models import Detection, Entity
from piighost.pipeline.base import AnonymizationPipeline
from piighost.placeholder import MaskPlaceholderFactory, RedactPlaceholderFactory
from piighost.resolver.entity import AnyEntityConflictResolver
from piighost.resolver.span import AnySpanConflictResolver
from piighost.utils import hash_sha256


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

    Example:
        >>> from piighost.models import Detection, Entity, Span
        >>> memory = ConversationMemory()
        >>> e = Entity(detections=(Detection("Patrick", "PERSON", Span(0, 7), 0.9),))
        >>> memory.record("abc123", [e])
        >>> memory.all_entities
        [Entity(detections=(Detection(text='Patrick', label='PERSON', position=Span(start_pos=0, end_pos=7), confidence=0.9),))]
    """

    entities_by_hash: dict[str, list[Entity]] = field(default_factory=dict)

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
        new_entities: list[Entity] = []
        for entity in entities:
            if self._is_known(entity):
                self._add_variant(entity)
            else:
                new_entities.append(entity)
        if text_hash in self.entities_by_hash:
            self.entities_by_hash[text_hash].extend(new_entities)
        else:
            self.entities_by_hash[text_hash] = new_entities

    @property
    def all_entities(self) -> list[Entity]:
        """Flat deduplicated list of all entities, in insertion order."""
        seen: set[tuple[str, str]] = set()
        result: list[Entity] = []
        for entities in self.entities_by_hash.values():
            for entity in entities:
                key = (entity.detections[0].text.lower(), entity.label)
                if key not in seen:
                    seen.add(key)
                    result.append(entity)
        return result

    def _is_known(self, entity: Entity) -> bool:
        """Check if a canonically identical entity already exists."""
        canonical = entity.detections[0].text.lower()
        label = entity.label
        return any(
            e.detections[0].text.lower() == canonical and e.label == label
            for entities in self.entities_by_hash.values()
            for e in entities
        )

    def _add_variant(self, entity: Entity) -> None:
        """Merge new text variants into the matching existing entity.

        When the same entity appears with a different surface form
        (e.g. ``"france"`` vs ``"France"``), the new text is appended
        to the existing ``Entity`` so that ``anonymize_with_ent`` can
        replace all forms via ``str.replace``.
        """
        canonical = entity.detections[0].text.lower()
        label = entity.label

        for entity_list in self.entities_by_hash.values():
            for i, existing in enumerate(entity_list):
                if (
                    existing.detections[0].text.lower() == canonical
                    and existing.label == label
                ):
                    existing_texts = {d.text for d in existing.detections}
                    new_dets = tuple(
                        d for d in entity.detections if d.text not in existing_texts
                    )
                    if new_dets:
                        entity_list[i] = Entity(
                            detections=existing.detections + new_dets
                        )
                    return


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
    """

    def __init__(
        self,
        detector: AnyDetector,
        anonymizer: AnyAnonymizer,
        entity_linker: AnyEntityLinker | None = None,
        entity_resolver: AnyEntityConflictResolver | None = None,
        span_resolver: AnySpanConflictResolver | None = None,
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
        )

        self._memories: dict[str, ConversationMemory] = {}
        self._thread_id: str = "default"

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

    def _thread_key(self, key: str) -> str:
        """Prefix a cache key with the active thread id."""
        return f"{self._thread_id}:{key}"

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

        self._thread_id = thread_id
        cache_key = self._thread_key(f"detect:{hash_sha256(text)}")
        value = self._serialize_detections(detections)
        await self._cache.set(cache_key, value)

    async def _cached_detect(self, text: str) -> list[Detection]:
        """Detect entities, using thread-scoped cache if available."""
        if self._cache is None:
            return await self._detector.detect(text)

        cache_key = self._thread_key(f"detect:{hash_sha256(text)}")
        cached = await self._cache.get(cache_key)

        if cached is not None:
            return self._deserialize_detections(cached)

        detections = await self._detector.detect(text)
        value = self._serialize_detections(detections)
        await self._cache.set(cache_key, value)
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

        serialized_entities = self._serialize_entities(entities)
        key = self._thread_key(f"anon:anonymized:{hash_sha256(anonymized)}")

        await self._cache.set(
            key,
            {
                "original": original,
                "entities": serialized_entities,
            },
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

        self._thread_id = thread_id
        key = self._thread_key(f"anon:anonymized:{hash_sha256(anonymized_text)}")
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
        self._thread_id = thread_id
        memory = self.get_memory(thread_id)

        entities = await self.detect_entities(text)
        entities = self._entity_linker.link_entities(
            entities,
            memory.all_entities,
        )
        memory.record(hash_sha256(text), entities)
        result = self.anonymize_with_ent(text, thread_id=thread_id)

        # Required for deanonymize method which looks up mappings via cache.
        await self._store_mapping(text, result, entities)
        return result, entities

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
        self._thread_id = thread_id
        resolved = self.get_resolved_entities(thread_id)

        if not resolved:
            return text

        tokens = self.ph_factory.create(resolved)

        anonymized = text
        # Sort by token length descending (longest-first).
        for entity, token in sorted(
            tokens.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        ):
            canonical = entity.detections[0].text
            text = text.replace(token, canonical)

        # Store mapping so deanonymize() cache lookup works for this text.
        await self._store_mapping(text, anonymized, resolved)
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
