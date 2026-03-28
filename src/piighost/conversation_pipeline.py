"""Conversation-aware anonymization pipeline.

Wraps :class:`AnonymizationPipeline` with a :class:`ConversationMemory`
to accumulate entities across messages.  Provides ``deanonymize_with_ent``
and ``anonymize_with_ent`` for simple ``str.replace``-based operations
on any text containing known tokens or original values.
"""

from piighost.anonymizer import AnyAnonymizer
from piighost.conversation_memory import ConversationMemory, AnyConversationMemory
from piighost.detector import AnyDetector
from piighost.entity_linker import AnyEntityLinker
from piighost.entity_resolver import AnyEntityConflictResolver
from piighost.models import Entity
from piighost.pipeline import AnonymizationPipeline
from piighost.span_resolver import AnySpanConflictResolver
from piighost.utils import hash_sha256


class ConversationAnonymizationPipeline(AnonymizationPipeline):
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
