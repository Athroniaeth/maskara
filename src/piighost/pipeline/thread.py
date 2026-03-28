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
from piighost.models import Entity
from piighost.pipeline.base import AnonymizationPipeline
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

        Args:
            text_hash: SHA-256 hash of the original text.
            entities: Entities detected in that message.
        """
        new_entities = [e for e in entities if not self._is_known(e)]
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


class ThreadAnonymizationPipeline(AnonymizationPipeline):
    """Adds conversation memory on top of ``AnonymizationPipeline``.

    Delegates detection, resolution, and span-based anonymization to the
    base pipeline.  After each ``anonymize()`` call, entities are recorded
    in memory so that ``deanonymize_with_ent`` / ``anonymize_with_ent``
    can operate on *any* text via ``str.replace``.

    The placeholder factory is retrieved from ``pipeline.ph_factory``
    to guarantee that token generation is always consistent.

    Args:
        detector: The entity detector to use.
        span_resolver: The span conflict resolver to use.
        entity_linker: The entity linker to use.
        entity_resolver: The entity conflict resolver to use.
        anonymizer: The anonymizer to use for span-based replacement.
        memory: Optional conversation memory.  Defaults to a fresh
            ``ConversationMemory``.
    """

    def __init__(
        self,
        detector: AnyDetector,
        span_resolver: AnySpanConflictResolver,
        entity_linker: AnyEntityLinker,
        entity_resolver: AnyEntityConflictResolver,
        anonymizer: AnyAnonymizer,
        memory: AnyConversationMemory | None = None,
    ) -> None:
        super().__init__(
            detector,
            span_resolver,
            entity_linker,
            entity_resolver,
            anonymizer,
        )

        self.memory = memory or ConversationMemory()

    @property
    def resolved_entities(self) -> list[Entity]:
        """All entities from memory, merged by the pipeline's entity resolver."""
        return self._entity_resolver.resolve(self.memory.all_entities)

    async def anonymize(self, text: str) -> tuple[str, list[Entity]]:
        """Run detection, record entities in memory, then anonymize.

        Uses ``all_entities`` from memory for token creation so that
        counters stay consistent across messages.

        Args:
            text: The original text to anonymize.

        Returns:
            A tuple of (anonymized text, entities used for anonymization).
        """
        entities = await self.detect_entities(text)
        self.memory.record(hash_sha256(text), entities)
        result = self.anonymize_with_ent(text)

        # Required for deanonymize method which looks up mappings via cache.
        await self._store_mapping(text, result, entities)
        return result, entities

    async def deanonymize_with_ent(self, text: str) -> str:
        """Replace all known tokens with original values via ``str.replace``.

        Works on any text containing tokens, even text never anonymized
        by this pipeline (e.g. LLM-generated output, tool arguments).
        Tokens are replaced **longest-first** to avoid partial matches.

        The result is stored in the cache so that ``deanonymize()`` can
        look it up later.

        Args:
            text: Text potentially containing placeholder tokens.

        Returns:
            Text with tokens replaced by original values.
        """
        if not self.resolved_entities:
            return text

        tokens = self.ph_factory.create(self.resolved_entities)

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
        await self._store_mapping(text, anonymized, self.resolved_entities)
        return text

    def anonymize_with_ent(self, text: str) -> str:
        """Replace all known original values with tokens via ``str.replace``.

        Replaces **all** spelling variants of each entity (not just the
        canonical form).  Values are replaced **longest-first** to avoid
        partial matches.

        Args:
            text: Text potentially containing original PII values.

        Returns:
            Text with original values replaced by tokens.
        """
        if not self.resolved_entities:
            return text

        tokens = self.ph_factory.create(self.resolved_entities)

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
