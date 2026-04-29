import importlib.util
from typing import Any, Generic, Mapping, Tuple

from typing_extensions import TypeVar

if importlib.util.find_spec("aiocache") is None:
    raise ImportError(
        "AnonymizationPipeline requires aiocache for caching. Install with `uv add piighost[cache]`."
    )

from aiocache import BaseCache, SimpleMemoryCache

from piighost.anonymizer import AnyAnonymizer
from piighost.detector import AnyDetector
from piighost.exceptions import CacheMissError, PIIRemainingError
from piighost.guard import AnyGuardRail, DisabledGuardRail
from piighost.linker.entity import AnyEntityLinker, ExactEntityLinker
from piighost.models import Detection, Entity
from piighost.observation.base import AbstractObservationService, AbstractSpan, NoOpObservationService
from piighost.placeholder import AnyPlaceholderFactory
from piighost.placeholder_tags import PlaceholderPreservation
from piighost.resolver.entity import (
    AnyEntityConflictResolver,
    MergeEntityConflictResolver,
)
from piighost.resolver.span import (
    AnySpanConflictResolver,
    ConfidenceSpanConflictResolver,
)
from piighost.utils import hash_sha256

PreservationT = TypeVar(
    "PreservationT",
    bound=PlaceholderPreservation,
    default=PlaceholderPreservation,
)
"""Preservation tag carried by the pipeline's anonymiser factory."""

CACHE_KEY_DETECTION = "detect"
"""Prefix for detector-result cache entries."""

CACHE_KEY_ANONYMIZATION = "anon:anonymized"
"""Prefix for anonymized-text → (original, entities) cache entries."""


def _detection_to_dict(d: Detection) -> dict[str, Any]:
    """Serialize a Detection to a JSON-friendly dict for observation output."""
    return {
        "label": d.label,
        "position": [d.position.start_pos, d.position.end_pos],
        "confidence": d.confidence,
        "text": d.text,
    }


def _entity_to_dict(e: Entity) -> dict[str, Any]:
    """Serialize an Entity to a JSON-friendly dict for observation output."""
    return {
        "label": e.label,
        "detections": [_detection_to_dict(d) for d in e.detections],
    }


class AnonymizationPipeline(Generic[PreservationT]):
    """Orchestrates the full anonymization pipeline.

    Chains all components together: detect → resolve spans → link entities
    → resolve entities → anonymize. Uses aiocache for:
    - Detector results (avoid expensive NER re-computation)
    - Anonymization mappings (allow deanonymize without passing entities)

    Cache keys use prefixes to avoid collisions:
    - ``detect:<hash>`` detector results
    - ``anon:anonymized:<hash>`` anonymized text → (original, entities)

    Args:
        detector: The entity detector (async).
        span_resolver: Resolves overlapping detection spans.
        entity_linker: Expands and groups detections into entities.
        entity_resolver: Merges conflicting entities.
        anonymizer: Performs text replacement and deanonymization.
        guard_rail: Optional final stage that re-validates the
            anonymized text. Defaults to ``DisabledGuardRail`` (no-op).
            Pass a ``DetectorGuardRail`` (or any ``AnyGuardRail``) to
            raise ``PIIRemainingError`` whenever residual PII is found
            in the output.
        cache: Optional aiocache instance. If ``None``, no caching
            is performed and deanonymize will raise KeyError.
        cache_ttl: Time-to-live in seconds applied to every cache entry
            the pipeline writes.  ``None`` (default) keeps entries until
            the backend evicts them, which is fine for in-memory caches
            but can leak unbounded state when sharing a Redis backend
            across threads.
    """

    _detector: AnyDetector
    _span_resolver: AnySpanConflictResolver
    _entity_linker: AnyEntityLinker
    _entity_resolver: AnyEntityConflictResolver
    _anonymizer: AnyAnonymizer[PreservationT]
    _guard_rail: AnyGuardRail
    _cache: BaseCache
    _cache_ttl: int | None
    _observation: AbstractObservationService

    def __init__(
        self,
        detector: AnyDetector,
        anonymizer: AnyAnonymizer[PreservationT],
        span_resolver: AnySpanConflictResolver | None = None,
        entity_linker: AnyEntityLinker | None = None,
        entity_resolver: AnyEntityConflictResolver | None = None,
        guard_rail: AnyGuardRail | None = None,
        cache: BaseCache | None = None,
        cache_ttl: int | None = None,
        observation: AbstractObservationService | None = None,
    ) -> None:
        span_resolver = span_resolver or ConfidenceSpanConflictResolver()
        entity_linker = entity_linker or ExactEntityLinker()
        entity_resolver = entity_resolver or MergeEntityConflictResolver()
        guard_rail = guard_rail or DisabledGuardRail()

        self._detector = detector
        self._span_resolver = span_resolver
        self._entity_linker = entity_linker
        self._entity_resolver = entity_resolver
        self._anonymizer = anonymizer
        self._guard_rail = guard_rail
        self._cache = cache or SimpleMemoryCache()
        self._cache_ttl = cache_ttl
        self._observation = observation or NoOpObservationService()

    @property
    def ph_factory(self) -> AnyPlaceholderFactory[PreservationT]:
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

    async def anonymize(
        self,
        text: str,
        *,
        metadata: Mapping[str, Any] | None = None,
        root_span: AbstractSpan | None = None,
    ) -> Tuple[str, list[Entity]]:
        """Run the full pipeline: detect → resolve → link → resolve → anonymize.

        Args:
            text: The original text to anonymize.
            metadata: Optional metadata forwarded to the observation trace.
            root_span: Caller-supplied root span. When provided the pipeline
                nests its stage observations under it and does not create a
                new root span from the configured observation service.

        Returns:
            A tuple of (anonymized text, entities used for anonymization).

        Raises:
            PIIRemainingError: If a non-default guard rail detects
                residual PII in the anonymized output.
        """
        if root_span is not None:
            return await self._anonymize_with_span(text, root_span, metadata=metadata)

        with self._observation.start_as_current_span(
            name="piighost.anonymize_pipeline",
            input={"text": text},
            metadata=dict(metadata) if metadata else None,
        ) as auto_root:
            return await self._anonymize_with_span(text, auto_root, metadata=metadata)

    async def _anonymize_with_span(
        self,
        text: str,
        root_span: AbstractSpan,
        *,
        metadata: Mapping[str, Any] | None,
    ) -> Tuple[str, list[Entity]]:
        """Execute all pipeline stages, emitting child observations on *root_span*."""
        # Detect
        with root_span.start_as_current_observation(
            name="piighost.detect", as_type="tool",
        ) as span:
            detections = await self._cached_detect(text)
            span.update(
                input={"text": text},
                output={"detections": [_detection_to_dict(d) for d in detections]},
            )
            detections = self._span_resolver.resolve(detections)

        # Link
        with root_span.start_as_current_observation(
            name="piighost.link", as_type="span",
        ) as span:
            entities = self._entity_linker.link(text, detections)
            entities = self._entity_resolver.resolve(entities)
            span.update(
                input={"detections": [_detection_to_dict(d) for d in detections]},
                output={"entities": [_entity_to_dict(e) for e in entities]},
            )

        # Placeholder
        with root_span.start_as_current_observation(
            name="piighost.placeholder", as_type="tool",
        ) as span:
            anonymized = self._anonymizer.anonymize(text, entities)
            span.update(
                input={"text": text, "entity_count": len(entities)},
                output={"text": anonymized},
            )

        # Guard
        with root_span.start_as_current_observation(
            name="piighost.guard", as_type="guardrail",
        ) as span:
            span.update(input={"text": anonymized})
            try:
                await self._guard_rail.check(anonymized)
            except PIIRemainingError:
                span.update(output={"passed": False})
                raise
            span.update(output={"passed": True})

        root_span.update(
            output={"text": anonymized, "entity_count": len(entities)},
        )

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
        key = f"{CACHE_KEY_ANONYMIZATION}:{hash_sha256(anonymized_text)}"
        cached = await self._cache_get(key)

        if cached is None:
            raise CacheMissError(f"No anonymization mapping cached for hash {key!r}")

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
        key = f"{CACHE_KEY_ANONYMIZATION}:{hash_sha256(anonymized)}"

        await self._cache.set(
            key,
            {
                "original": original,
                "entities": serialized_entities,
            },
            ttl=self._cache_ttl,
        )

    async def _cached_detect(self, text: str) -> list[Detection]:
        """Detect entities, using cache if available."""
        if self._cache is None:
            return await self._detector.detect(text)

        cache_key = f"{CACHE_KEY_DETECTION}:{hash_sha256(text)}"
        cached = await self._cache.get(cache_key)

        if cached is not None:
            return self._deserialize_detections(cached)

        detections = await self._detector.detect(text)
        value = self._serialize_detections(detections)
        await self._cache.set(cache_key, value, ttl=self._cache_ttl)
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
        return [d.to_dict() for d in detections]

    @staticmethod
    def _deserialize_detections(data: list[dict]) -> list[Detection]:
        return [Detection.from_dict(d) for d in data]

    @staticmethod
    def _serialize_entities(entities: list[Entity]) -> list[list[dict]]:
        """Serialize entities as a list of detection lists."""
        return [[d.to_dict() for d in entity.detections] for entity in entities]

    @staticmethod
    def _deserialize_entities(data: list[list[dict]]) -> list[Entity]:
        """Deserialize entities from a list of detection lists."""
        return [
            Entity(detections=tuple(Detection.from_dict(d) for d in detections))
            for detections in data
        ]
