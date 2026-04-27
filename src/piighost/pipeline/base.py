import importlib.util
from typing import Generic, Tuple

from typing_extensions import TypeVar

if importlib.util.find_spec("aiocache") is None:
    raise ImportError(
        "AnonymizationPipeline requires aiocache for caching. Install with `uv add piighost[cache]`."
    )

from aiocache import BaseCache, SimpleMemoryCache

from piighost.anonymizer import AnyAnonymizer
from piighost.detector import AnyDetector
from piighost.exceptions import CacheMissError
from piighost.guard import AnyGuardRail, DisabledGuardRail
from piighost.linker.entity import AnyEntityLinker, ExactEntityLinker
from piighost.models import Detection, Entity
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

    async def anonymize(self, text: str) -> Tuple[str, list[Entity]]:
        """Run the full pipeline: detect → resolve → link → resolve → anonymize.

        Args:
            text: The original text to anonymize.

        Returns:
            A tuple of (anonymized text, entities used for anonymization).

        Raises:
            PIIRemainingError: If a non-default guard rail detects
                residual PII in the anonymized output.
        """
        entities = await self.detect_entities(text)

        # Replace detections with placeholder tokens.
        anonymized = self._anonymizer.anonymize(text, entities)

        # Final binary check on the anonymized output. The default
        # DisabledGuardRail is a no-op, so existing pipelines keep
        # their behaviour untouched.
        await self._guard_rail.check(anonymized)

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
