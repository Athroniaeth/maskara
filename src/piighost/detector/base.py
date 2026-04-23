import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from piighost.models import Detection, Span


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


class BaseNERDetector(ABC):
    """Abstract base for detectors relying on a NER model.

    Normalizes the ``labels`` argument into an ``{external: internal}``
    mapping, builds the reverse lookup used during detection, and forces
    subclasses to implement :meth:`detect`.

    The distinction between *external* and *internal* labels lets callers
    decouple the label that appears in :class:`Detection.label` (and
    therefore in downstream placeholders, datasets, etc.) from the label
    a specific model prefers at query/output time. For instance, GLiNER2
    may find more entities when queried with ``"company"`` (lowercase) yet
    the caller wants a clean ``"COMPANY"`` label in the output.

    Args:
        labels: Either ``None`` / ``[]`` (no mapping, subclass decides
            identity behaviour), a list of labels (identity mapping
            ``{x: x}``), or a ``{external: internal}`` dict.

    Raises:
        ValueError: If two external labels map to the same internal label
            (the reverse lookup would be ambiguous).

    Example:
        >>> class MyDetector(BaseNERDetector):
        ...     async def detect(self, text: str) -> list[Detection]:
        ...         ...
        >>> detector = MyDetector(labels={"PERSON": "PER", "COMPANY": "ORG"})
        >>> detector.internal_labels
        ['PER', 'ORG']
        >>> detector._map_label("PER")
        'PERSON'
    """

    def __init__(self, labels: list[str] | dict[str, str] | None) -> None:
        self._label_map: dict[str, str] = self._normalize(labels)
        self._reverse_map: dict[str, str] = self._build_reverse(self._label_map)

    @abstractmethod
    async def detect(self, text: str) -> list[Detection]:
        """Detect entities in ``text``.

        Implementations must return :class:`Detection` objects whose
        ``label`` has already been remapped to the external label.
        """
        ...

    @staticmethod
    def _normalize(
        labels: list[str] | dict[str, str] | None,
    ) -> dict[str, str]:
        """Normalize the ``labels`` argument into an ``{external: internal}`` dict."""
        if labels is None:
            return {}
        if isinstance(labels, list):
            return {label: label for label in labels}
        return dict(labels)

    @staticmethod
    def _build_reverse(label_map: dict[str, str]) -> dict[str, str]:
        """Build the ``{internal: external}`` reverse lookup.

        Raises:
            ValueError: If an internal label is used by more than one
                external label.
        """
        reverse: dict[str, str] = {}
        for external, internal in label_map.items():
            if internal in reverse:
                raise ValueError(
                    f"Label mapping conflict: internal label '{internal}' is "
                    f"used by multiple external labels "
                    f"('{reverse[internal]}' and '{external}')."
                )
            reverse[internal] = external
        return reverse

    @property
    def internal_labels(self) -> list[str]:
        """Labels passed to the underlying model (mapping values)."""
        return list(self._label_map.values())

    @property
    def external_labels(self) -> list[str]:
        """Labels emitted in :class:`Detection.label` (mapping keys)."""
        return list(self._label_map.keys())

    def _map_label(self, internal: str) -> str | None:
        """Return the external label for an internal one, or ``None`` if unmapped."""
        return self._reverse_map.get(internal)


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

    bag_of_words: list[tuple[str, str]]
    _flags: re.RegexFlag
    _compiled: list[tuple[re.Pattern[str], str]]

    def __init__(
        self,
        bag_of_words: list[tuple[str, str]],
        flags: re.RegexFlag = re.IGNORECASE,
    ) -> None:
        self.bag_of_words = bag_of_words
        self._flags = flags
        self._compiled = [
            (self._build_pattern(word, flags), label) for word, label in bag_of_words
        ]

    @staticmethod
    def _build_pattern(word: str, flags: re.RegexFlag) -> re.Pattern[str]:
        escaped = re.escape(word)
        prefix = r"\b" if word[0:1].isalnum() or word[0:1] == "_" else r"(?<!\w)"
        suffix = r"\b" if word[-1:].isalnum() or word[-1:] == "_" else r"(?!\w)"
        return re.compile(f"{prefix}{escaped}{suffix}", flags)

    async def detect(self, text: str) -> list[Detection]:
        """Detect entities by matching words from the dictionary in the text.

        Iterates over each pre-compiled pattern and collects all
        non-overlapping matches.

        Args:
            text: The input text to search for entities.

        Returns:
            A list of ``Detection`` objects for each match found, with
            ``confidence`` set to ``1.0``.
        """
        detections: list[Detection] = []

        for pattern, label in self._compiled:
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
        validators: Optional mapping from label to a callable that returns
            ``True`` when the matched text is a genuine instance of the
            entity (e.g. Luhn checksum for credit cards, mod-97 for IBANs).
            A label without an entry in this mapping is accepted on the
            regex match alone. Matches rejected by a validator are
            silently dropped.

    Example:
        >>> from piighost.detector.patterns import FR_PATTERNS
        >>> from piighost.validators import validate_iban, validate_nir
        >>> detector = RegexDetector(
        ...     patterns=FR_PATTERNS,
        ...     validators={"FR_IBAN": validate_iban, "FR_NIR": validate_nir},
        ... )
    """

    patterns: dict[str, str] = field(default_factory=dict)
    validators: dict[str, Callable[[str], bool]] = field(default_factory=dict)
    _compiled: dict[str, re.Pattern[str]] = field(
        init=False, repr=False, compare=False, default_factory=dict
    )

    def __post_init__(self) -> None:
        self._compiled = {label: re.compile(p) for label, p in self.patterns.items()}

    async def detect(self, text: str) -> list[Detection]:
        """Find all regex matches for the configured patterns.

        For labels that have a registered validator, each regex match is
        passed to it and discarded if the validator returns ``False``.

        Args:
            text: The input text to search for entities.

        Returns:
            One ``Detection`` per accepted match, with ``confidence=1.0``.
        """
        detections: list[Detection] = []

        for label, compiled in self._compiled.items():
            validator = self.validators.get(label)

            for match in compiled.finditer(text):
                matched_text = match.group()
                if validator is not None and not validator(matched_text):
                    continue

                detections.append(
                    Detection(
                        text=matched_text,
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
