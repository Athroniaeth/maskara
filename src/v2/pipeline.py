from typing import Tuple

from aiocache import Cache

from v2.anonymizer import AnyAnonymizer
from v2.detector import AnyDetector
from v2.placeholder import AnyPlaceholderFactory
from v2.entity_linker import AnyEntityLinker
from v2.entity_resolver import AnyEntityConflictResolver
from v2.models import Detection, Entity, Span
from v2.span_resolver import AnySpanConflictResolver
from v2.utils import hash_sha256

try:
    from aiocache import BaseCache
except ImportError:
    raise ImportError(
        "AnonymizationPipeline requires aiocache for caching. Install with `uv add piighost[pipeline]`."
    )


class AnonymizationPipeline:
    """Orchestrates the full anonymization pipeline.

    Chains all components together: detect → resolve spans → link entities
    → resolve entities → anonymize. Uses aiocache for:
    - Detector results (avoid expensive NER re-computation)
    - Anonymization mappings (allow deanonymize without passing entities)

    Cache keys use prefixes to avoid collisions:
    - ``detect:<hash>`` detector results
    - ``anon:original:<hash>`` original text → (anonymized, entities)
    - ``anon:anonymized:<hash>`` anonymized text → (original, entities)

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
        anonymizer: AnyAnonymizer,
        cache: BaseCache | None = None,
    ) -> None:
        self._detector = detector
        self._span_resolver = span_resolver
        self._entity_linker = entity_linker
        self._entity_resolver = entity_resolver
        self._anonymizer = anonymizer
        self._cache = cache or Cache(Cache.MEMORY)

    @property
    def ph_factory(self) -> "AnyPlaceholderFactory":
        """The placeholder factory used by the anonymizer."""
        return self._anonymizer.ph_factory

    async def detect_entities(self, text: str) -> list[Entity]:
        """Run the detection pipeline: detect → resolve → link → resolve.

        Args:
            text: The text to analyze.

        Returns:
            Resolved and merged entities found in the text.
        """
        detections = await self._cached_detect(text)
        detections = self._span_resolver.resolve(detections)
        entities = self._entity_linker.link(text, detections)
        return self._entity_resolver.resolve(entities)

    async def anonymize(self, text: str) -> Tuple[str, list[Entity]]:
        """Run the full pipeline: detect → resolve → link → resolve → anonymize.

        Args:
            text: The original text to anonymize.

        Returns:
            A tuple of (anonymized text, entities used for anonymization).
        """
        entities = await self.detect_entities(text)

        # Replace detections with placeholder tokens.
        anonymized = self._anonymizer.anonymize(text, entities)

        # Store both directions for deanonymization lookup.
        await self._store_mapping(text, anonymized, entities)

        return anonymized, entities

    async def deanonymize(self, anonymized_text: str) -> Tuple[str, list[Entity]]:
        """Deanonymize using the anonymized text as lookup key.

        Args:
            anonymized_text: The anonymized text to restore.

        Returns:
            The restored original text.

        Raises:
            KeyError: If the anonymized text was never produced by this pipeline.
        """
        key = f"anon:anonymized:{hash_sha256(anonymized_text)}"
        cached = await self._cache_get(key)

        if cached is None:
            raise KeyError("No anonymization found for this text")

        entities = self._deserialize_entities(cached["entities"])
        result = self._anonymizer.deanonymize(anonymized_text, entities)
        return result, entities

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
        key = f"anon:anonymized:{hash_sha256(anonymized)}"

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

        cache_key = f"detect:{hash_sha256(text)}"
        cached = await self._cache.get(cache_key)

        if cached is not None:
            return self._deserialize_detections(cached)

        detections = await self._detector.detect(text)
        value = self._serialize_detections(detections)
        await self._cache.set(cache_key, value)
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
