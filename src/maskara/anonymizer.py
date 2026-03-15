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
from langchain_core.messages import AnyMessage


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
        start: Character offset of the first character (inclusive) in the source text.
        end: Character offset past the last character (exclusive) in the source text.
        anon_start: Character offset of the placeholder (inclusive) in the anonymized text.
        anon_end: Character offset past the placeholder (exclusive) in the anonymized text.
    """

    text: str
    entity_type: str
    confidence: float
    start: Optional[int] = None
    end: Optional[int] = None
    anon_start: Optional[int] = None
    anon_end: Optional[int] = None


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
    _thread_store: Dict[ThreadID, Dict[str, "Placeholder"]]

    def __init__(
        self,
        extractor: GLiNER2,
        entity_types: Optional[List[str]] = None,
        min_confidence: float = 0.5,
    ):
        self.extractor = extractor
        self.entity_types = entity_types or ["company", "person", "product", "location"]
        self.min_confidence = min_confidence
        self._thread_store: Dict[ThreadID, Dict[str, Placeholder]] = {}

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

        detections = [d for d in detections if d.confidence >= self.min_confidence]
        return detections

    def assign_placeholders(
        self,
        detections: List[NamedEntity],
        existing_vocab: Optional[Dict[str, Placeholder]] = None,
    ) -> Dict[Placeholder, List[NamedEntity]]:
        """Assign a placeholder key to each unique entity text.

        Entities with the same surface form share the same placeholder.
        Different surface forms within the same label get distinct indices.
        If existing_vocab is provided, known texts reuse their existing
        placeholder and new indices start after the already-assigned ones.

        Args:
            detections: List of detected named entities.
            existing_vocab: Previously built vocabulary mapping entity text to placeholder.

        Returns:
            Mapping from Placeholder to all detections that share that placeholder.
        """
        occupied: Dict[Placeholder, str] = {}
        if existing_vocab:
            for text, ph in existing_vocab.items():
                occupied[ph] = text

        placeholders: Dict[Placeholder, List[NamedEntity]] = defaultdict(list)

        for detection in detections:
            label = detection.entity_type

            if existing_vocab and detection.text in existing_vocab:
                placeholders[existing_vocab[detection.text]].append(detection)
                continue

            for index in range(1, 1000):
                placeholder = build_placeholder(label, index)
                if placeholder not in occupied:
                    placeholders[placeholder].append(detection)
                    occupied[placeholder] = detection.text
                    break
                elif occupied[placeholder] == detection.text:
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
        candidates = []
        for placeholder, detections in placeholders.items():
            for detection in detections:
                if detection.start is None or detection.end is None:
                    continue
                candidates.append((detection.start, detection.end, placeholder, detection.confidence))

        # Greedy: prefer high confidence, then longer span
        candidates.sort(key=lambda x: (x[3], x[1] - x[0]), reverse=True)

        kept: List[tuple[int, int, str]] = []
        accepted_spans: List[tuple[int, int]] = []
        for start, end, placeholder, _ in candidates:
            if any(start < ae and end > as_ for as_, ae in accepted_spans):
                continue
            kept.append((start, end, placeholder))
            accepted_spans.append((start, end))

        # Apply in reverse start order to preserve indices
        kept.sort(key=lambda x: x[0], reverse=True)
        for start, end, placeholder in kept:
            text = text[:start] + placeholder + text[end:]

        return text

    def compute_anonymized_spans(
        self,
        anonymized_text: str,
        placeholders: Dict[Placeholder, List[NamedEntity]],
    ) -> Dict[Placeholder, List[NamedEntity]]:
        """Populate anon_start/anon_end on each entity by scanning the anonymized text.

        Args:
            anonymized_text: Text after all replacements have been applied.
            placeholders: Mapping from placeholder to detections.

        Returns:
            The same placeholders dict with anon_start/anon_end set on each entity.
        """
        for placeholder, entities in placeholders.items():
            occurrences = list(re.finditer(re.escape(placeholder), anonymized_text))
            for match, entity in zip(occurrences, entities):
                entity.anon_start = match.start()
                entity.anon_end = match.end()
        return placeholders

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
        tid = resolve_thread_id(thread_id)
        existing_vocab = self._thread_store.get(tid, {})
        detections = self.detect_entities(text)
        placeholders = self.assign_placeholders(detections, existing_vocab=existing_vocab)
        placeholders = self.expand_placeholders(text, placeholders)
        anonymized_text = self.replace_with_placeholders(text, placeholders)

        placeholders = self.compute_anonymized_spans(anonymized_text, placeholders)

        updated_vocab = dict(existing_vocab)
        for ph, entities in placeholders.items():
            if entities:
                updated_vocab[entities[0].text] = ph
        self._thread_store[tid] = updated_vocab

        return anonymized_text, placeholders

    def deanonymize(
        self,
        text: str,
        placeholders: Dict[Placeholder, List[NamedEntity]],
    ) -> str:
        """Restore original entity text by replacing placeholders.

        Each placeholder occurrence in the anonymized text is matched to its
        corresponding NamedEntity (sorted by original ``start`` offset), so that
        entities with different surface forms (e.g. after fuzzy matching) are each
        restored to their own original text rather than all defaulting to the first.

        Args:
            text: Anonymized text containing placeholder tokens.
            placeholders: Mapping returned by ``anonymize``.

        Returns:
            Text with each placeholder token replaced by the original entity text.
        """
        replacements: List[tuple[int, int, str]] = []

        for placeholder, entities in placeholders.items():
            if not entities:
                continue

            sorted_entities = sorted(
                (e for e in entities if e.start is not None),
                key=lambda e: e.start,  # type: ignore[arg-type]
            )
            occurrences = list(re.finditer(re.escape(placeholder), text))

            for match, entity in zip(occurrences, sorted_entities):
                replacements.append((match.start(), match.end(), entity.text))

        # Note: sort in reverse order to preserve character indices during replacement
        replacements.sort(key=lambda x: x[0], reverse=True)

        for start, end, original_text in replacements:
            text = text[:start] + original_text + text[end:]

        return text

    def anonymize_messages(
        self,
        messages: list[AnyMessage],
        thread_id: Optional[str] = None,
    ) -> tuple[list[AnyMessage], Dict[Placeholder, List[NamedEntity]]]:
        """Anonymize a list of messages, preserving thread context.

        Args:
            messages: List of LangChain messages to anonymize.
            thread_id: Thread identifier used to persist placeholder mappings.

        Returns:
            A tuple of (anonymized_messages, combined_placeholders).
        """
        new_messages = []
        combined_placeholders: Dict[Placeholder, List[NamedEntity]] = {}
        for message in messages:
            assert isinstance(message.content, str), (
                "This simple anonymizer only works for string content."
            )
            message.content, placeholders = self.anonymize(message.content, thread_id=thread_id)
            combined_placeholders.update(placeholders)
            new_messages.append(message)
        return new_messages, combined_placeholders

    def deanonymize_messages(
        self,
        messages: list[AnyMessage],
        thread_id: Optional[str] = None,
        placeholders: Optional[Dict[Placeholder, List[NamedEntity]]] = None,
    ) -> list[AnyMessage]:
        """Deanonymize a list of messages using thread store or explicit placeholders.

        Args:
            messages: List of LangChain messages to deanonymize.
            thread_id: Thread identifier to look up stored placeholder mappings.
            placeholders: Explicit placeholder mapping (overrides thread_id lookup).

        Returns:
            Messages with placeholders replaced by original entity text.
        """
        if placeholders is None and thread_id is not None:
            tid = resolve_thread_id(thread_id)
            vocab = self._thread_store.get(tid, {})
            reverse_vocab: Dict[str, str] = {ph: text for text, ph in vocab.items()}
        else:
            reverse_vocab = {
                ph: entities[0].text
                for ph, entities in (placeholders or {}).items()
                if entities
            }
        for message in messages:
            assert isinstance(message.content, str), (
                "This simple anonymizer only works for string content."
            )
            for ph, original_text in reverse_vocab.items():
                message.content = message.content.replace(ph, original_text)
        return messages


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
