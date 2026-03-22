"""Entity detection abstraction and GLiNER2 implementation."""

import re
from dataclasses import dataclass, field
from typing import Protocol, Sequence

from gliner2 import GLiNER2

from maskara.anonymizer.models import Entity


class EntityDetector(Protocol):
    """Interface for named-entity detection (dependency-injection point).

    Implementations may wrap any NER backend: GLiNER, spaCy, a remote
    API, etc.  The anonymiser depends only on this protocol.
    """

    def detect(self, text: str, labels: Sequence[str]) -> list[Entity]:
        """Detect entities in *text* for the requested *labels*.

        Args:
            text: The source string to analyse.
            labels: Entity types to look for (e.g. ``["PERSON", "LOCATION"]``).

        Returns:
            A list of detected entities (may contain duplicates across
            positions but not at the exact same span).
        """
        ...  # pragma: no cover


@dataclass
class GlinerDetector:
    """Detect entities using a GLiNER2 model.

    The class lazily wraps a ``GLiNER`` model instance so that callers
    can inject a pre-loaded model (useful for tests and shared workers).

    Args:
        model: A loaded ``GLiNER`` model instance.
        threshold: Minimum confidence score to keep a prediction.
        flat_ner: Whether to use flat NER mode (no nested entities).

    Example:
        >>> from gliner import GLiNER
        >>> model = GLiNER.from_pretrained("urchade/gliner_multi_pii-v1")
        >>> detector = GlinerDetector(model=model, threshold=0.5)
        >>> entities = detector.detect("Je m'appelle Patrick", ["PERSON"])
    """

    model: GLiNER2
    threshold: float = 0.5
    flat_ner: bool = True

    def detect(self, text: str, labels: Sequence[str]) -> list[Entity]:
        """Run GLiNER prediction and convert results to ``Entity`` objects.

        Args:
            text: The source string.
            labels: Entity types to search for.

        Returns:
            Entities whose score meets the configured threshold.
        """
        raw_entities = self.model.extract_entities(
            text,
            entity_types=list(labels),
            threshold=self.threshold,
            include_spans=True,
            include_confidence=True,
        )["entities"]

        return [
            Entity(
                text=entity["text"],
                label=entity_type,
                start=entity["start"],
                end=entity["end"],
                score=entity["confidence"],
            )
            for entity_type, list_entity in raw_entities.items()
            for entity in list_entity
        ]


@dataclass
class RegexDetector:
    """Detect entities using regular expressions, one pattern per label.

    Useful for structured secrets with a known format (API keys, emails,
    credit-card numbers, etc.) that GLiNER2 may miss.

    Args:
        patterns: Mapping from entity label to a regex pattern (string or
            compiled).  Only labels present in this dict can be detected.

    Example:
        >>> detector = RegexDetector(patterns={
        ...     "OPENAI_API_KEY": r"sk-(?:proj-)?[A-Za-z0-9\\-_]{20,}",
        ... })
        >>> entities = detector.detect("my key is sk-proj-abc123xyz456789", ["OPENAI_API_KEY"])
    """

    patterns: dict[str, str | re.Pattern[str]] = field(default_factory=dict)

    def detect(self, text: str, labels: Sequence[str]) -> list[Entity]:
        """Find all regex matches for the requested *labels*.

        Args:
            text: The source string to analyse.
            labels: Only patterns whose label appears here are executed.

        Returns:
            One ``Entity`` per regex match, with ``score=1.0``.
        """
        entities: list[Entity] = []
        label_set = set(labels)
        for label, pattern in self.patterns.items():
            if label not in label_set:
                continue
            compiled = re.compile(pattern) if isinstance(pattern, str) else pattern
            for m in compiled.finditer(text):
                entities.append(
                    Entity(
                        text=m.group(),
                        label=label,
                        start=m.start(),
                        end=m.end(),
                        score=1.0,
                    )
                )
        return entities


@dataclass
class CompositeDetector:
    """Run multiple detectors and merge their results.

    Lets you combine a GLiNER-based detector (natural language) with a
    ``RegexDetector`` (structured patterns) without changing ``Anonymizer``.
    Deduplication of overlapping spans is handled downstream by ``Anonymizer``.

    Args:
        detectors: Ordered list of ``EntityDetector`` implementations to run.

    Example:
        >>> detector = CompositeDetector(detectors=[
        ...     GlinerDetector(model=gliner_model),
        ...     RegexDetector(patterns={"OPENAI_API_KEY": r"sk-[A-Za-z0-9\\-_]{20,}"}),
        ... ])
    """

    detectors: list[EntityDetector] = field(default_factory=list)

    def detect(self, text: str, labels: Sequence[str]) -> list[Entity]:
        """Collect entities from every child detector.

        Args:
            text: The source string.
            labels: Forwarded to each child detector unchanged.

        Returns:
            Concatenated list of entities from all detectors.
        """
        entities: list[Entity] = []
        for detector in self.detectors:
            entities.extend(detector.detect(text, labels))
        return entities
