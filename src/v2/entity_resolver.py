from typing import Protocol

from v2.models import Detection, Entity
from v2.similarity import AnySimilarityFn, jaro_winkler_similarity


class AnyEntityConflictResolver(Protocol):
    """Protocol defining the interface for entity conflict resolvers.

    When multiple entities share common detections (e.g. from different
    linker strategies), a resolver decides how to reconcile them.
    """

    def have_conflict(self, entity_a: Entity, entity_b: Entity) -> bool:
        """Check whether two entities are in conflict.

        Args:
            entity_a: The first entity.
            entity_b: The second entity.

        Returns:
            ``True`` if the two entities share at least one detection.
        """
        ...

    def resolve(self, entities: list[Entity]) -> list[Entity]:
        """Resolve conflicts across all entities.

        Args:
            entities: The full list of entities, potentially with
                shared detections.

        Returns:
            A list of entities with all conflicts resolved.
        """
        ...


class MergeEntityConflictResolver:
    """Resolver that merges entities sharing common detections.

    When two entities share at least one detection, they are merged
    into a single entity containing all their detections (deduplicated).
    This is transitive: if A shares a detection with B, and B shares
    one with C, all three are merged into one entity.

    Example:
        >>> from v2.models import Detection, Entity, Span
        >>> d_a = Detection(text="Patrick", label="PERSON", position=Span(0, 7), confidence=0.9)
        >>> d_b = Detection(text="Patrick", label="PERSON", position=Span(20, 27), confidence=0.9)
        >>> d_c = Detection(text="patric", label="PERSON", position=Span(30, 36), confidence=0.8)
        >>> entity_1 = Entity(detections=[d_a, d_b])
        >>> entity_2 = Entity(detections=[d_b, d_c])
        >>> resolver = MergeEntityConflictResolver()
        >>> result = resolver.resolve([entity_1, entity_2])
        >>> len(result)
        1
        >>> len(result[0].detections)
        3
    """

    def have_conflict(self, entity_a: Entity, entity_b: Entity) -> bool:
        """Check whether two entities share at least one common detection.

        Args:
            entity_a: The first entity.
            entity_b: The second entity.

        Returns:
            ``True`` if the entities have at least one detection in common.
        """
        detections_a = set(entity_a.detections)
        return any(d in detections_a for d in entity_b.detections)

    def resolve(self, entities: list[Entity]) -> list[Entity]:
        """Merge all entities that share common detections transitively.

        Uses a Union-Find algorithm to efficiently group entities that
        are connected through shared detections.

        Args:
            entities: The full list of entities.

        Returns:
            A merged list of entities with no shared detections,
            sorted by earliest ``start_pos``.
        """
        if not entities:
            return []

        # Start with a copy so we don't mutate the input.
        result: list[Entity] = list(entities)

        # Keep merging until no more conflicts are found.
        # On each pass, we look for two entities that share a detection
        # and merge them into one. We repeat until a full pass finds
        # no conflicts (meaning all remaining entities are independent).
        changed = True
        while changed:
            changed = False

            for i in range(len(result)):
                for j in range(i + 1, len(result)):
                    if self.have_conflict(result[i], result[j]):
                        # Merge entity j into entity i (deduplicate detections).
                        seen: set[Detection] = set(result[i].detections)
                        merged_detections = list(result[i].detections)
                        for d in result[j].detections:
                            if d not in seen:
                                seen.add(d)
                                merged_detections.append(d)

                        # Replace i with the merged entity, remove j.
                        result[i] = Entity(detections=tuple(merged_detections))
                        result.pop(j)

                        # Restart the scan indices have shifted after pop.
                        changed = True
                        break

                # Break the outer for-loop too so we restart the while.
                if changed:
                    break

        result.sort(key=lambda e: min(d.position.start_pos for d in e.detections))
        return result


class FuzzyEntityConflictResolver(MergeEntityConflictResolver):
    """Resolver that merges entities with similar canonical text.

    Subclasses ``MergeEntityConflictResolver`` and overrides
    ``have_conflict`` to use string similarity instead of shared
    detections.  The ``resolve`` loop is inherited as-is.

    Args:
        similarity_fn: A ``(str, str) -> float`` function returning
            a score in [0.0, 1.0].  Defaults to Jaro-Winkler.
        threshold: Minimum similarity score to consider two entities
            as the same.  Defaults to 0.85.

    Example:
        >>> from v2.models import Detection, Entity, Span
        >>> e1 = Entity(detections=(Detection("Patrick", "PERSON", Span(0, 7), 0.9),))
        >>> e2 = Entity(detections=(Detection("patric", "PERSON", Span(20, 26), 0.8),))
        >>> resolver = FuzzyEntityConflictResolver()
        >>> result = resolver.resolve([e1, e2])
        >>> len(result)
        1
    """

    def __init__(
        self,
        similarity_fn: AnySimilarityFn = jaro_winkler_similarity,
        threshold: float = 0.85,
    ) -> None:
        self._similarity_fn = similarity_fn
        self._threshold = threshold

    def have_conflict(self, entity_a: Entity, entity_b: Entity) -> bool:
        """Check whether two entities have similar canonical text.

        Args:
            entity_a: The first entity.
            entity_b: The second entity.

        Returns:
            ``True`` if the entities have the same label and their
            canonical texts are similar above the threshold.
        """
        if entity_a.label != entity_b.label:
            return False
        text_a = entity_a.detections[0].text.lower()
        text_b = entity_b.detections[0].text.lower()
        return self._similarity_fn(text_a, text_b) >= self._threshold
