from typing import Protocol

from piighost.models import Detection


class AnySpanConflictResolver(Protocol):
    """Protocol defining the interface for span conflict resolvers.

    When multiple detections overlap (i.e. their spans share character
    positions), a resolver decides which detections to keep and which
    to discard.
    """

    def resolve(self, detections: list[Detection]) -> list[Detection]:
        """Resolve overlapping detections and return only the winners.

        Args:
            detections: The full list of detections, potentially with
                overlapping spans.

        Returns:
            A filtered list of detections with no overlapping spans.
        """
        ...


class ConfidenceSpanConflictResolver:
    """Resolver that keeps the detection with the highest confidence on overlap.

    When two or more detections have overlapping spans, only the one with
    the highest ``confidence`` score is retained. Non-overlapping detections
    are always kept.

    The algorithm sorts detections by descending confidence, then greedily
    accepts each detection only if it does not overlap with any already
    accepted detection.

    Example:
        >>> from piighost.models import Detection, Span
        >>> detections = [
        ...     Detection(label="PERSON", position=Span(17, 24), confidence=0.91),
        ...     Detection(label="PERSON", position=Span(17, 22), confidence=0.51),
        ...     Detection(label="LOCATION", position=Span(45, 51), confidence=1.0),
        ... ]
        >>> resolver = ConfidenceSpanConflictResolver()
        >>> resolved = resolver.resolve(detections)
        >>> [(d.label, d.confidence) for d in resolved]
        [('PERSON', 0.91), ('LOCATION', 1.0)]
    """

    def resolve(self, detections: list[Detection]) -> list[Detection]:
        """Keep the highest-confidence detection when spans overlap.

        Args:
            detections: The full list of detections, potentially with overlapping spans.

        Returns:
            A filtered list of detections with no overlapping spans,
            sorted by position (ascending ``start_pos``).
        """
        accepted: list[Detection] = []
        ranked = sorted(detections, key=lambda d: d.confidence, reverse=True)

        for detection in ranked:
            gen = (detection.position.overlaps(a.position) for a in accepted)
            if not any(gen):
                accepted.append(detection)

        accepted.sort(key=lambda d: d.position.start_pos)
        return accepted
