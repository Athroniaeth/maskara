from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from v2.anonymizer import Anonymizer
from v2.detector import AnyDetector
from v2.entity_linker import AnyEntityLinker
from v2.entity_resolver import AnyEntityConflictResolver
from v2.models import Detection, Entity, Span
from v2.span_resolver import AnySpanConflictResolver

if TYPE_CHECKING:
    from aiocache import BaseCache


class AnonymizationPipeline:
    """Orchestrates the full anonymization pipeline.

    Chains all components together: detect → resolve spans → link entities
    → resolve entities → anonymize. Uses aiocache for:
    - Detector results (avoid expensive NER re-computation)
    - Anonymization mappings (allow deanonymize without passing entities)

    Cache keys use prefixes to avoid collisions:
    - ``detect:<hash>`` — detector results
    - ``anon:original:<hash>`` — original text → (anonymized, entities)
    - ``anon:anonymized:<hash>`` — anonymized text → (original, entities)

    Args:
        detector: The entity detector (async).
        span_resolver: Resolves overlapping detection spans.
        entity_linker: Expands and groups detections into entities.
        entity_resolver: Merges conflicting entities.
        anonymizer: Performs text replacement and deanonymization.
        cache: Optional aiocache instance. If ``None``, no caching
            is performed and deanonymize will raise KeyError.
    """

    def __init__(
        self,
        detector: AnyDetector,
        span_resolver: AnySpanConflictResolver,
        entity_linker: AnyEntityLinker,
        entity_resolver: AnyEntityConflictResolver,
        anonymizer: Anonymizer,
        cache: BaseCache | None = None,
    ) -> None:
        self._detector = detector
        self._span_resolver = span_resolver
        self._entity_linker = entity_linker
        self._entity_resolver = entity_resolver
        self._anonymizer = anonymizer
        self._cache = cache

    async def anonymize(self, text: str) -> str:
        """Run the full pipeline: detect → resolve → link → resolve → anonymize.

        Args:
            text: The original text to anonymize.

        Returns:
            The anonymized text.
        """
        # Detect entities (cached if a cache is configured).
        detections = await self._cached_detect(text)

        # Resolve overlapping spans (keep highest confidence).
        detections = self._span_resolver.resolve(detections)

        # Expand detections and group into entities.
        entities = self._entity_linker.link(text, detections)

        # Merge entities that share detections.
        entities = self._entity_resolver.resolve(entities)

        # Replace detections with placeholder tokens.
        anonymized = self._anonymizer.anonymize(text, entities)

        # Store both directions for deanonymization lookup.
        await self._store_mapping(text, anonymized, entities)

        return anonymized

    async def deanonymize(self, anonymized_text: str) -> str:
        """Deanonymize using the anonymized text as lookup key.

        Args:
            anonymized_text: The anonymized text to restore.

        Returns:
            The restored original text.

        Raises:
            KeyError: If the anonymized text was never produced by this pipeline.
        """
        key = f"anon:anonymized:{self._hash(anonymized_text)}"
        cached = await self._cache_get(key)

        if cached is None:
            raise KeyError("No anonymization found for this text")

        entities = self._deserialize_entities(cached["entities"])
        return self._anonymizer.deanonymize(anonymized_text, entities)

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    async def _store_mapping(
        self,
        original: str,
        anonymized: str,
        entities: list[Entity],
    ) -> None:
        """Store the anonymization mapping in cache (both directions)."""
        if self._cache is None:
            return

        serialized_entities = self._serialize_entities(entities)
        key = f"anon:anonymized:{self._hash(anonymized)}"

        await self._cache.set(
            key,
            {
                "original": original,
                "entities": serialized_entities,
            },
        )

    async def _cached_detect(self, text: str) -> list[Detection]:
        """Detect entities, using cache if available."""
        if self._cache is None:
            return await self._detector.detect(text)

        cache_key = f"detect:{self._hash(text)}"
        cached = await self._cache.get(cache_key)

        if cached is not None:
            return self._deserialize_detections(cached)

        detections = await self._detector.detect(text)
        await self._cache.set(cache_key, self._serialize_detections(detections))
        return detections

    async def _cache_get(self, key: str) -> dict | None:
        """Get a value from cache, or None if no cache or key missing."""
        if self._cache is None:
            return None
        result = await self._cache.get(key)
        return result

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    @staticmethod
    def _serialize_detections(detections: list[Detection]) -> list[dict]:
        return [
            {
                "text": d.text,
                "label": d.label,
                "start": d.position.start_pos,
                "end": d.position.end_pos,
                "confidence": d.confidence,
            }
            for d in detections
        ]

    @staticmethod
    def _deserialize_detections(data: list[dict]) -> list[Detection]:
        return [
            Detection(
                text=d["text"],
                label=d["label"],
                position=Span(start_pos=d["start"], end_pos=d["end"]),
                confidence=d["confidence"],
            )
            for d in data
        ]

    @staticmethod
    def _serialize_entities(entities: list[Entity]) -> list[list[dict]]:
        """Serialize entities as a list of detection lists."""
        return [
            [
                {
                    "text": d.text,
                    "label": d.label,
                    "start": d.position.start_pos,
                    "end": d.position.end_pos,
                    "confidence": d.confidence,
                }
                for d in entity.detections
            ]
            for entity in entities
        ]

    @staticmethod
    def _deserialize_entities(data: list[list[dict]]) -> list[Entity]:
        """Deserialize entities from a list of detection lists."""
        return [
            Entity(
                detections=tuple(
                    Detection(
                        text=d["text"],
                        label=d["label"],
                        position=Span(start_pos=d["start"], end_pos=d["end"]),
                        confidence=d["confidence"],
                    )
                    for d in detections
                )
            )
            for detections in data
        ]

    @staticmethod
    def _hash(text: str) -> str:
        """SHA-256 hash of a text string."""
        return hashlib.sha256(text.encode()).hexdigest()
