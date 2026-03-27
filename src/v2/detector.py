import re
from typing import Protocol

from v2.models import Detection, Span


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
