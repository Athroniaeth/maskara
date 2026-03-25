from dataclasses import dataclass

@dataclass
class Span:
    """Represents the position of a substring within a text.

    Attributes:
        start_pos: Inclusive start index in the source text.
        end_pos: Exclusive end index in the source text.
    """

    start_pos: int
    end_pos: int

    def overlaps(self, other: "Span") -> bool:
        """Check whether this span overlaps with another.

        Args:
            other: The span to test against.

        Returns:
            ``True`` if the two spans share at least one character position.
        """
        return self.start_pos < other.end_pos and other.start_pos < self.end_pos


@dataclass
class Detection:
    """Represents a named entity recognition (NER) result from a text.

    Attributes:
        label: The entity type (e.g. ``"PERSON"``, ``"LOCATION"``).
        position: The span indicating where the entity was found.
        confidence: Confidence score of the detection (0.0 – 1.0).
    """

    label: str
    position: Span
    confidence: float

    @property
    def hash(self) -> str:
        """Build a unique identifier for this detection.

        Combines label, position, and confidence so that two detections
        at different positions are always distinguishable.

        Returns:
            A colon-separated string uniquely identifying this detection.

        Notes:
            Used to check whether a detection appears multiple times
            during entity extraction.
        """
        return f"{self.label}:{self.position.start_pos}:{self.position.end_pos}:{self.confidence}"


