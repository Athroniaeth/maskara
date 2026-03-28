from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from piighost.models import Detection, Span

if TYPE_CHECKING:
    from gliner2 import GLiNER2


class AnyDetector(Protocol):
    """Protocol defining the interface for all entity detectors.

    Any class implementing this protocol must provide a ``detect`` method
    that performs Named Entity Recognition (NER) on a given text.
    """

    async def detect(self, text: str) -> list[Detection]:
        """Detect and extract entities from the given text.

        Args:
            text: The input text to analyze for entities.

        Returns:
            A list of ``Detection`` objects representing each entity found.
        """
        ...


class ExactMatchDetector:
    """Detector that finds entities by exact word matching against a dictionary.

    Uses word-boundary regex to match whole words only, preventing partial
    matches inside longer words (e.g., searching for ``"Patrick"`` will not
    match ``"Patric"``).

    All matches are returned with a confidence of ``1.0`` since they are
    exact matches.

    Attributes:
        bag_of_words: List of ``(text, label)`` tuples representing the
            words to search for and their entity labels
            (e.g., ``[("Patrick", "PERSON"), ("Paris", "LOCATION")]``).

    Args:
        bag_of_words: A list of ``(text, label)`` tuples.
        flags: Regex flags for matching. Defaults to ``re.IGNORECASE``
            for case-insensitive matching.

    Example:
        >>> detector = ExactMatchDetector([("Patrick", "PERSON"), ("Paris", "LOCATION")])
        >>> detections = detector.detect("Patrick habite à Paris")
        >>> [(d.label, d.position.start_pos, d.position.end_pos) for d in detections]
        [('PERSON', 0, 7), ('LOCATION', 17, 22)]
    """

    def __init__(
        self,
        bag_of_words: list[tuple[str, str]],
        flags: re.RegexFlag = re.IGNORECASE,
    ) -> None:
        self.bag_of_words = bag_of_words
        self._flags = flags

    async def detect(self, text: str) -> list[Detection]:
        """Detect entities by matching words from the dictionary in the text.

        Iterates over each word in ``bag_of_words``, builds a word-boundary
        regex pattern, and collects all non-overlapping matches.

        Args:
            text: The input text to search for entities.

        Returns:
            A list of ``Detection`` objects for each match found, with
            ``confidence`` set to ``1.0``.
        """
        detections: list[Detection] = []

        for word, label in self.bag_of_words:
            escaped = re.escape(word)

            prefix = r"\b" if word[0:1].isalnum() or word[0:1] == "_" else r"(?<!\w)"
            suffix = r"\b" if word[-1:].isalnum() or word[-1:] == "_" else r"(?!\w)"

            pattern = re.compile(f"{prefix}{escaped}{suffix}", self._flags)

            for match in pattern.finditer(text):
                detections.append(
                    Detection(
                        text=text[match.start() : match.end()],
                        label=label,
                        position=Span(
                            start_pos=match.start(),
                            end_pos=match.end(),
                        ),
                        confidence=1.0,
                    ),
                )

        return detections


@dataclass
class RegexDetector:
    """Detect entities using regular expressions, one pattern per label.

    Useful for structured PII with a known format (phone numbers, IBANs,
    API keys, etc.) that a model-based detector may miss.

    Args:
        patterns: Mapping from entity label to a regex pattern string.

    Example:
        >>> detector = RegexDetector(patterns={"FR_PHONE": r"\\b(?:\\+33|0)[1-9](?:[\\s.\\-]?\\d{2}){4}\\b"})
        >>> detections = await detector.detect("Appelez le 06 12 34 56 78")
    """

    patterns: dict[str, str] = field(default_factory=dict)

    async def detect(self, text: str) -> list[Detection]:
        """Find all regex matches for the configured patterns.

        Args:
            text: The input text to search for entities.

        Returns:
            One ``Detection`` per regex match, with ``confidence=1.0``.
        """
        detections: list[Detection] = []

        for label, pattern in self.patterns.items():
            compiled = re.compile(pattern)

            for match in compiled.finditer(text):
                detections.append(
                    Detection(
                        text=match.group(),
                        label=label,
                        position=Span(
                            start_pos=match.start(),
                            end_pos=match.end(),
                        ),
                        confidence=1.0,
                    ),
                )

        return detections


@dataclass
class CompositeDetector:
    """Run multiple detectors and merge their results.

    Lets you combine detectors (e.g. a model-based detector with a
    ``RegexDetector``) without changing the pipeline. Deduplication of
    overlapping spans is handled downstream by the span resolver.

    Args:
        detectors: Ordered list of detectors to run.

    Example:
        >>> detector = CompositeDetector(detectors=[
        ...     ExactMatchDetector([("Patrick", "PERSON")]),
        ...     RegexDetector(patterns={"FR_PHONE": r"\\b0[1-9](?:[\\s.\\-]?\\d{2}){4}\\b"}),
        ... ])
    """

    detectors: list[AnyDetector] = field(default_factory=list)

    async def detect(self, text: str) -> list[Detection]:
        """Collect detections from every child detector.

        Args:
            text: The input text to search for entities.

        Returns:
            Concatenated list of detections from all detectors.
        """
        detections: list[Detection] = []

        for detector in self.detectors:
            detections.extend(await detector.detect(text))

        return detections


class GlinerDetector:
    """Detect entities using a GLiNER2 model.

    Wraps a ``GLiNER2`` model instance so that callers can inject a
    pre-loaded model (useful for tests and shared workers).

    Args:
        model: A loaded ``GLiNER2`` model instance.
        labels: Entity types this detector is configured to find.
        threshold: Minimum confidence score to keep a prediction.
        flat_ner: Whether to use flat NER mode (no nested entities).

    Example:
        >>> from gliner2 import GLiNER2
        >>> model = GLiNER2.from_pretrained("urchade/gliner_multi_pii-v1")
        >>> detector = GlinerDetector(model=model, labels=["PERSON", "LOCATION"])
        >>> detections = await detector.detect("Je m'appelle Patrick")
    """

    def __init__(
        self,
        model: GLiNER2,
        labels: list[str],
        threshold: float = 0.5,
        flat_ner: bool = True,
    ) -> None:
        self.model = model
        self.labels = labels
        self.threshold = threshold
        self.flat_ner = flat_ner

    async def detect(self, text: str) -> list[Detection]:
        """Run GLiNER2 prediction and convert results to ``Detection`` objects.

        Args:
            text: The input text to search for entities.

        Returns:
            Detections whose score meets the configured threshold.
        """
        raw_entities = self.model.extract_entities(
            text,
            entity_types=self.labels,
            threshold=self.threshold,
            include_spans=True,
            include_confidence=True,
        )["entities"]

        return [
            Detection(
                text=entity["text"],
                label=entity_type,
                position=Span(
                    start_pos=entity["start"],
                    end_pos=entity["end"],
                ),
                confidence=entity["confidence"],
            )
            for entity_type, list_entity in raw_entities.items()
            for entity in list_entity
        ]

