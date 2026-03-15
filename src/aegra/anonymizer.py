import re
from collections import defaultdict
from dataclasses import dataclass
from typing import (
    Optional,
    List,
    TypedDict,
    Required,
    NotRequired,
    Dict,
)
from uuid import uuid4

from gliner2 import GLiNER2


# extractor = GLiNER2.from_pretrained("fastino/gliner2-base-v1")


class GlinerEntity(TypedDict):
    """Raw entity dict as returned by the GLiNER library."""

    text: Required[str]
    confidence: NotRequired[float]
    start: NotRequired[int]
    end: NotRequired[int]


@dataclass
class NamedEntity:
    """Enriched named entity produced by the anonymizer pipeline.

    Attributes:
        text: The surface form of the entity as it appears in the text.
        entity_type: Category label (e.g. "person", "company").
        confidence: Detection confidence score in [0, 1].
        start: Character offset of the first character (inclusive).
        end: Character offset past the last character (exclusive).
    """

    text: str
    entity_type: str
    confidence: float
    start: Optional[int] = None
    end: Optional[int] = None


class ThreadID(str): ...


class Placeholder(str): ...


def build_placeholder(label: str, index: int) -> Placeholder:
    """Build a placeholder token for a given entity label and index.

    Args:
        label: Entity type label (e.g. "person").
        index: 1-based occurrence index within that label.

    Returns:
        A Placeholder string such as ``<PERSON_1>``.
    """
    return Placeholder(f"<{label}_{index}>".upper())


def resolve_thread_id(thread_id: Optional[str]) -> ThreadID:
    """Return a ThreadID, generating one from UUID if none is provided.

    Args:
        thread_id: An existing thread identifier, or None.

    Returns:
        A ThreadID guaranteed to be non-empty.
    """
    return ThreadID(thread_id or uuid4().hex)


class Anonymizer:
    """Anonymizes free-form text by replacing named entities with placeholders.

    Attributes:
        extractor: GLiNER2 model used for entity detection.
        entity_types: Entity categories to detect.
    """

    extractor: GLiNER2
    entity_types: List[str]

    def __init__(self, extractor: GLiNER2, entity_types: Optional[List[str]] = None):
        self.extractor = extractor
        self.entity_types = entity_types or ["company", "person", "product", "location"]

    def detect_entities(self, text: str) -> List[NamedEntity]:
        """Detect and return named entities found in the text.

        Args:
            text: Input text to analyse.

        Returns:
            List of NamedEntity objects with type, confidence, and span info.
        """
        detections: List[NamedEntity] = []
        result = self.extractor.extract_entities(
            text,
            self.entity_types,
            include_spans=True,
            include_confidence=True,
        )

        list_entity: List[GlinerEntity]
        for entity_type, list_entity in result["entities"].items():
            for entity in list_entity:
                detections.append(
                    NamedEntity(
                        text=entity["text"],
                        entity_type=entity_type,
                        confidence=entity["confidence"],
                        start=entity["start"],
                        end=entity["end"],
                    )
                )

        return detections

    def assign_placeholders(
        self,
        detections: List[NamedEntity],
    ) -> Dict[Placeholder, List[NamedEntity]]:
        """Assign a placeholder key to each unique entity text.

        Entities with the same surface form share the same placeholder.
        Different surface forms within the same label get distinct indices.

        Args:
            detections: List of detected named entities.

        Returns:
            Mapping from Placeholder to all detections that share that placeholder.
        """
        placeholders: Dict[Placeholder, List[NamedEntity]] = defaultdict(list)

        for detection in detections:
            label = detection.entity_type

            for index in range(1, 1000):
                placeholder = build_placeholder(label, index)
                if placeholder not in placeholders:
                    placeholders[placeholder].append(detection)
                    break
                else:
                    first_detection = placeholders[placeholder][0]
                    # Todo : use fuzzy matching ?
                    if first_detection.text == detection.text:
                        placeholders[placeholder].append(detection)
                        break

        return placeholders

    def expand_placeholders(
        self,
        text: str,
        placeholders: Dict[Placeholder, List[NamedEntity]],
    ) -> Dict[Placeholder, List[NamedEntity]]:
        """Expand placeholder coverage by scanning for additional occurrences.

        GLiNER often detects only the first occurrence of an entity.
        This method scans the full text to find additional matches
        of the detected entity strings.

        Args:
            text: Original input text.
            placeholders: Existing placeholders mapped to detections.

        Returns:
            Updated placeholders with additional detections.
        """
        new_placeholders: Dict[Placeholder, List[NamedEntity]] = placeholders.copy()

        for placeholder, detections in placeholders.items():
            if not detections:
                continue

            reference = detections[0]
            entity_text = reference.text
            entity_type = reference.entity_type

            pattern = re.escape(entity_text)

            # Existing spans to avoid duplicates
            existing_spans = {
                (d.start, d.end)
                for d in detections
                if d.start is not None and d.end is not None
            }

            for match in re.finditer(pattern, text):
                start, end = match.span()

                if (start, end) in existing_spans:
                    continue

                new_placeholders[placeholder].append(
                    NamedEntity(
                        text=entity_text,
                        entity_type=entity_type,
                        confidence=1.0,
                        start=start,
                        end=end,
                    )
                )

        return new_placeholders

    def replace_with_placeholders(
        self,
        text: str,
        placeholders: Dict[Placeholder, List[NamedEntity]],
    ) -> str:
        """Replace detected entity spans in text with their placeholder tokens.

        Args:
            text: Original input text.
            placeholders: Mapping from placeholder to detections with span info.

        Returns:
            Text with all entity spans substituted by placeholder tokens.
        """
        replacements = []

        for placeholder, detections in placeholders.items():
            for detection in detections:
                if detection.start is None or detection.end is None:
                    continue
                replacements.append((detection.start, detection.end, placeholder))

        # Note: sort in reverse order to preserve character indices during replacement
        replacements.sort(key=lambda x: x[0], reverse=True)

        for start, end, placeholder in replacements:
            text = text[:start] + placeholder + text[end:]

        return text

    def anonymize(
        self,
        text: str,
        thread_id: Optional[str] = None,
    ) -> tuple[str, Dict[Placeholder, List[NamedEntity]]]:
        """Anonymize the given text by replacing named entities with placeholders.

        Args:
            text: Input text to anonymize.
            thread_id: Optional identifier for tracking conversation threads.

        Returns:
            A tuple of (anonymized_text, placeholders) where placeholders maps
            each Placeholder token to the list of NamedEntity objects it replaced.
        """
        thread_id = resolve_thread_id(thread_id)
        detections = self.detect_entities(text)
        placeholders = self.assign_placeholders(detections)
        placeholders = self.expand_placeholders(text, placeholders)
        text = self.replace_with_placeholders(text, placeholders)
        return text, placeholders

    def deanonymize(
        self,
        text: str,
        placeholders: Dict[Placeholder, List[NamedEntity]],
    ) -> str:
        """Restore original entity text by replacing placeholders.

        Args:
            text: Anonymized text containing placeholder tokens.
            placeholders: Mapping returned by ``anonymize``.

        Returns:
            Text with each placeholder token replaced by the original entity text.
        """
        for placeholder, entities in placeholders.items():
            if not entities:
                continue
            text = text.replace(placeholder, entities[0].text)
        return text


def main():
    extractor = GLiNER2.from_pretrained("fastino/gliner2-base-v1")
    anonymizer = Anonymizer(extractor)
    anonymized_text, placeholders = anonymizer.anonymize(
        "Apple Inc. CEO Tim Cook announced iPhone "
        "15 in Cupertino. Cupertino is nice town. "
        "Paris is capital !"
    )
    for entity_type, entities in placeholders.items():
        print(entity_type)
        for entity in entities:
            print(f"\t{entity}")

    print("---")
    print(anonymized_text)

    print("---")
    desanonymized_text = anonymizer.deanonymize(anonymized_text, placeholders)
    print(desanonymized_text)


if __name__ == "__main__":
    main()
