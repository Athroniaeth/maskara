import re
from collections import defaultdict
from typing import Protocol

from piighost.models import Detection, Entity, Span


class AnyEntityLinker(Protocol):
    """Protocol defining the interface for entity linkers.

    An entity linker takes a text and a list of pre-existing detections,
    expands them by finding missed occurrences, and groups all detections
    that refer to the same PII into ``Entity`` objects.
    """

    def link(self, text: str, detections: list[Detection]) -> list[Entity]:
        """Link detections to entities.

        Args:
            text: The original source text.
            detections: Pre-existing detections from a detector.

        Returns:
            A list of ``Entity`` objects, each grouping detections
            that refer to the same PII.
        """
        ...


class ExactEntityLinker:
    """Entity linker that expands and groups detections by exact text match.

    For each detection, finds all exact occurrences of its surface text
    in the source text (word-boundary regex, case-insensitive). Creates
    new detections for missed occurrences, then groups all detections
    with the same normalized text and label into a single ``Entity``.

    Args:
        flags: Regex flags for occurrence matching. Defaults to
            ``re.IGNORECASE`` for case-insensitive matching.

    Example:
        >>> from piighost.models import Detection, Span
        >>> detections = [Detection(text="Patrick", label="PERSON", position=Span(0, 7), confidence=0.9)]
        >>> linker = ExactEntityLinker()
        >>> entities = linker.link("Patrick est gentil. Patrick habite ici.", detections)
        >>> len(entities)
        1
        >>> len(entities[0].detections)
        2
    """

    def __init__(self, flags: re.RegexFlag = re.IGNORECASE) -> None:
        self._flags = flags

    def link(self, text: str, detections: list[Detection]) -> list[Entity]:
        """Expand detections and group them into entities.

        Args:
            text: The original source text.
            detections: Pre-existing detections from a detector.

        Returns:
            A list of ``Entity`` objects sorted by the earliest
            ``start_pos`` of their detections.
        """
        if not detections:
            return []

        # Track positions already covered by existing detections
        # so we don't create duplicate detections at the same span.
        occupied: set[Span] = {d.position for d in detections}

        all_detections = list(detections)

        # Step 1: Expansion for each known detection, search the full text
        # for other occurrences the detector may have missed.
        # Example: NER found "Patrick" at pos 0 but missed "Patrick" at pos 30.
        for detection in detections:
            for start, end in self._find_all(text, detection.text):
                position = Span(start_pos=start, end_pos=end)

                if position not in occupied:
                    occupied.add(position)
                    all_detections.append(
                        Detection(
                            text=text[start:end],
                            label=detection.label,
                            position=position,
                            # 1.0 because this is an exact text match,
                            # not a probabilistic NER prediction.
                            confidence=1.0,
                        ),
                    )

        # Step 2: Grouping detections with the same normalized text
        # and label refer to the same PII, so they become one Entity.
        # We use .lower() so "Patrick" and "PATRICK" are grouped together.
        groups: dict[tuple[str, str], list[Detection]] = defaultdict(list)
        for d in all_detections:
            key = (d.text.lower(), d.label)
            groups[key].append(d)

        entities = [Entity(detections=tuple(dets)) for dets in groups.values()]
        entities.sort(key=lambda e: min(d.position.start_pos for d in e.detections))
        return entities

    def _find_all(self, text: str, fragment: str) -> list[tuple[int, int]]:
        """Find all word-boundary occurrences of a fragment in the text.

        Args:
            text: The source text to search.
            fragment: The substring to look for.

        Returns:
            A list of ``(start, end)`` tuples for every match.
        """
        # Escape special regex characters so "M. Dupont" doesn't treat "." as wildcard.
        escaped = re.escape(fragment)

        # Word boundaries (\b) prevent partial matches inside longer words:
        # searching "Patrick" won't match "APatrick".
        # But \b only works when the character at the boundary is alphanumeric
        # or underscore. For fragments starting/ending with special chars
        # (e.g. "+33..."), we use lookarounds instead: (?<!\w) and (?!\w).
        prefix = (
            r"\b" if fragment[0:1].isalnum() or fragment[0:1] == "_" else r"(?<!\w)"
        )
        suffix = r"\b" if fragment[-1:].isalnum() or fragment[-1:] == "_" else r"(?!\w)"

        pattern = re.compile(f"{prefix}{escaped}{suffix}", self._flags)
        return [(m.start(), m.end()) for m in pattern.finditer(text)]
