from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
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


@dataclass(frozen=True)
class Detection:
    """Represents a named entity recognition (NER) result from a text.

    Attributes:
        text: The surface form found in the source string (e.g. ``"Patrick"``).
            This field holds **raw PII**: it is rendered verbatim by the
            dataclass-generated ``__repr__``. If you forward Detection
            instances to logs or external sinks, scrub them yourself
            (e.g. via :meth:`to_dict` filtered, or a structured logger
            with field-level redaction).
        label: The entity type (e.g. ``"PERSON"``, ``"LOCATION"``).
        position: The span indicating where the entity was found.
        confidence: Confidence score of the detection (0.0 – 1.0).
    """

    text: str
    label: str
    position: Span
    confidence: float

    @property
    def hash(self) -> str:
        """Build a unique identifier for this detection.

        Combines text, label, position, and confidence so that two detections
        at different positions are always distinguishable.

        Returns:
            A colon-separated string uniquely identifying this detection.

        Notes:
            Used to check whether a detection appears multiple times
            during entity extraction.
        """
        return f"{self.text}:{self.label}:{self.position.start_pos}:{self.position.end_pos}:{self.confidence}"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly mapping of this detection."""
        return {
            "text": self.text,
            "label": self.label,
            "start_pos": self.position.start_pos,
            "end_pos": self.position.end_pos,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Detection":
        """Build a Detection from the mapping produced by :meth:`to_dict`."""
        return cls(
            text=data["text"],
            label=data["label"],
            position=Span(
                start_pos=data["start_pos"],
                end_pos=data["end_pos"],
            ),
            confidence=data["confidence"],
        )


@dataclass(frozen=True)
class Entity:
    """Group of detections that refer to the same PII.

    All detections in an entity share the same label. The label is
    derived from the first detection in the list.

    Attributes:
        detections: Tuple of detections referring to the same PII.

    Raises:
        ValueError: If ``detections`` is empty.
    """

    detections: tuple[Detection, ...]

    def __post_init__(self) -> None:
        if not self.detections:
            raise ValueError("At least one detection is required")

    @property
    def label(self) -> str:
        """The entity type, derived from the first detection.

        Returns:
            The label string (e.g. ``"PERSON"``).
        """
        return self.detections[0].label

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly mapping of this entity."""
        return {"detections": [d.to_dict() for d in self.detections]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Entity":
        """Build an Entity from the mapping produced by :meth:`to_dict`."""
        return cls(detections=tuple(Detection.from_dict(d) for d in data["detections"]))
