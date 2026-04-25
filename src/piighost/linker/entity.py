import re
from collections import defaultdict
from typing import Protocol

from piighost.models import Detection, Entity, Span
from piighost.utils import find_all_word_boundary


class AnyEntityLinker(Protocol):
    """Protocol defining the interface for entity linkers.

    An entity linker takes a text and a list of pre-existing detections,
    expands them by finding missed occurrences, and groups all detections
    that refer to the same PII into ``Entity`` objects.

    It can also link entities across different texts via
    ``link_entities``, so that the same PII detected in separate
    messages shares a single placeholder.
    """

    def link(self, text: str, detections: list[Detection]) -> list[Entity]:
        """Link detections to entities within a single text.

        Args:
            text: The original source text.
            detections: Pre-existing detections from a detector.

        Returns:
            A list of ``Entity`` objects, each grouping detections
            that refer to the same PII.
        """
        ...

    def link_entities(
        self,
        entities: list[Entity],
        known_entities: list[Entity],
    ) -> list[Entity]:
        """Link entities from the current text with known entities.

        For each current entity whose canonical text and label match
        a known entity, merge them so they share the same placeholder.

        Args:
            entities: Entities detected in the current text.
            known_entities: Entities accumulated from previous texts.

        Returns:
            A list of entities where matched ones are merged with
            their known counterpart (known detections first).
        """
        ...


class BaseEntityLinker:
    """Base class providing common filtering for entity linkers.

    Subclasses inherit ``min_text_length`` filtering, which controls
    which detections are eligible for expansion (finding additional
    occurrences in the text).  Detections shorter than the threshold
    are kept as-is but not expanded.

    Args:
        min_text_length: Minimum character length for a detection to
            be expanded.  Detections shorter than this are preserved
            but the linker will not search for additional occurrences.
            Defaults to ``1`` (expand everything, backward-compatible).
    """

    _min_text_length: int

    def __init__(self, min_text_length: int = 1) -> None:
        self._min_text_length = min_text_length

    def _is_expandable(self, detection: Detection) -> bool:
        """Whether this detection should be expanded to other occurrences."""
        return len(detection.text) >= self._min_text_length


class DisabledEntityLinker:
    """Passthrough linker that disables entity expansion and grouping.

    Each detection becomes its own ``Entity`` (one detection per entity,
    no expansion, no cross-message linking). Useful when the detector
    already produces clean, deduplicated detections, or when the user
    explicitly wants every detection to remain a separate placeholder
    even if surface texts collide.

    Example:
        >>> from piighost.models import Detection, Span
        >>> detections = [
        ...     Detection(text="Patrick", label="PERSON", position=Span(0, 7), confidence=0.9),
        ...     Detection(text="Patrick", label="PERSON", position=Span(20, 27), confidence=0.9),
        ... ]
        >>> linker = DisabledEntityLinker()
        >>> entities = linker.link("Patrick et Patrick", detections)
        >>> len(entities)
        2
    """

    def link(self, text: str, detections: list[Detection]) -> list[Entity]:
        return [Entity(detections=(d,)) for d in detections]

    def link_entities(
        self,
        entities: list[Entity],
        known_entities: list[Entity],
    ) -> list[Entity]:
        return list(entities)


class ExactEntityLinker(BaseEntityLinker):
    """Entity linker that expands and groups detections by exact text match.

    For each detection, finds all exact occurrences of its surface text
    in the source text (word-boundary regex, case-insensitive). Creates
    new detections for missed occurrences, then groups all detections
    with the same normalized text and label into a single ``Entity``.

    Args:
        flags: Regex flags for occurrence matching. Defaults to
            ``re.IGNORECASE`` for case-insensitive matching.
        min_text_length: Minimum character length for a detection to
            be expanded.  Inherited from ``BaseEntityLinker``.

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

    _flags: re.RegexFlag

    def __init__(
        self,
        flags: re.RegexFlag = re.IGNORECASE,
        min_text_length: int = 1,
    ) -> None:
        super().__init__(min_text_length=min_text_length)
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
        return self._group(self._expand(text, detections))

    def link_entities(
        self,
        entities: list[Entity],
        known_entities: list[Entity],
    ) -> list[Entity]:
        """Link current entities with known entities from previous messages.

        For each current entity, if a known entity shares the same
        canonical text (case-insensitive) and label, merge them into
        a single entity with known detections first.  This ensures
        that ``LabelCounterPlaceholderFactory`` assigns the same token.

        Args:
            entities: Entities detected in the current text.
            known_entities: Entities accumulated from previous texts.

        Returns:
            Entities where matched ones are merged with their known
            counterpart.  Unmatched entities are returned as-is.
        """
        if not entities or not known_entities:
            return entities
        current_detections = [d for e in entities for d in e.detections]
        return self._group(current_detections, seed_entities=known_entities)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _expand(self, text: str, detections: list[Detection]) -> list[Detection]:
        """Find missed occurrences of each detection in the full text.

        For each detection, searches the text for all word-boundary
        matches and creates new detections for positions not already
        covered.

        Args:
            text: The source text to search.
            detections: Detections to expand.

        Returns:
            The original detections plus any newly discovered ones
            (with ``confidence=1.0``).
        """
        occupied: set[Span] = {d.position for d in detections}
        expanded = list(detections)

        for detection in detections:
            if not self._is_expandable(detection):
                continue

            for start, end in self._find_all(text, detection.text):
                position = Span(start_pos=start, end_pos=end)
                if position not in occupied:
                    occupied.add(position)
                    expanded.append(
                        Detection(
                            text=text[start:end],
                            label=detection.label,
                            position=position,
                            confidence=1.0,
                        ),
                    )

        return expanded

    def _group(
        self,
        detections: list[Detection],
        seed_entities: list[Entity] | None = None,
    ) -> list[Entity]:
        """Group detections by canonical key ``(text.lower(), label)``.

        When *seed_entities* is provided, their detections are placed
        first in each matching group so the canonical identity (first
        detection) is preserved.  Only groups that received at least
        one detection from *detections* are included in the result.

        Args:
            detections: Detections to group.
            seed_entities: Optional known entities whose detections
                seed the groups before current detections are added.

        Returns:
            A list of ``Entity`` objects sorted by earliest position.
        """
        groups: dict[tuple[str, str], list[Detection]] = defaultdict(list)

        if seed_entities:
            for entity in seed_entities:
                key = (entity.detections[0].text.lower(), entity.label)
                if key not in groups:
                    groups[key] = list(entity.detections)

        active_keys: set[tuple[str, str]] = set()
        for d in detections:
            key = (d.text.lower(), d.label)
            active_keys.add(key)
            groups[key].append(d)

        entities = [
            Entity(detections=tuple(dets))
            for key, dets in groups.items()
            if key in active_keys
        ]
        entities.sort(
            key=lambda e: min(d.position.start_pos for d in e.detections),
        )
        return entities

    def _find_all(self, text: str, fragment: str) -> list[tuple[int, int]]:
        """Find all word-boundary occurrences of a fragment in the text.

        Args:
            text: The source text to search.
            fragment: The substring to look for.

        Returns:
            A list of ``(start, end)`` tuples for every match.
        """
        return find_all_word_boundary(text, fragment, self._flags)
