from dataclasses import dataclass


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


@dataclass(frozen=True, repr=False)
class Detection:
    """Represents a named entity recognition (NER) result from a text.

    Attributes:
        text: The surface form found in the source string (e.g. ``"Patrick"``).
            This field holds **raw PII**; it is masked in :meth:`__repr__`
            to prevent accidental leaks through ``print``, ``logger``,
            or uncaught tracebacks. Access the raw value via
            ``detection.text`` when needed.
        label: The entity type (e.g. ``"PERSON"``, ``"LOCATION"``).
        position: The span indicating where the entity was found.
        confidence: Confidence score of the detection (0.0 – 1.0).
    """

    text: str
    label: str
    position: Span
    confidence: float

    def __repr__(self) -> str:
        """Return a repr that masks the raw PII surface form.

        The ``text`` field is redacted to ``<redacted:N>`` (N = length
        in characters) so accidental ``print(detection)`` or a logger
        call does not surface the unanonymised value. The other fields
        are rendered verbatim.
        """
        return (
            f"Detection(text=<redacted:{len(self.text)}>, "
            f"label={self.label!r}, position={self.position!r}, "
            f"confidence={self.confidence})"
        )

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
