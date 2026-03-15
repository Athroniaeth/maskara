from __future__ import annotations

from typing import Optional
from uuid import uuid4

from gliner2 import GLiNER2
from langchain_core.messages import AnyMessage


class Anonymizer:
    """Anonymizes free-form text by replacing named entities with placeholders.

    Pipeline: detect (GLiNER2) → assign (<TYPE_N>) → replace (str.replace, longest-first).
    Per-thread memory ensures the same entity always maps to the same placeholder.
    """

    def __init__(
        self,
        extractor: GLiNER2,
        entity_types: Optional[list[str]] = None,
        min_confidence: float = 0.5,
    ):
        self.extractor = extractor
        self.entity_types = entity_types or ["company", "person", "product", "location"]
        self.min_confidence = min_confidence
        self._thread_store: dict[str, dict[str, str]] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _detect(self, text: str) -> list[tuple[str, str]]:
        """Extract entities via GLiNER2, returning (text, entity_type) pairs."""
        raw = self.extractor.extract_entities(
            text,
            self.entity_types,
            include_spans=True,
            include_confidence=True,
        )
        hits: list[tuple[str, str]] = []
        for entity_type, entities in raw["entities"].items():
            for entity in entities:
                if entity.get("confidence", 0) >= self.min_confidence:
                    stripped = entity["text"].strip()
                    if stripped:
                        hits.append((stripped, entity_type))
        return hits

    def _assign(
        self,
        detections: list[tuple[str, str]],
        vocab: dict[str, str],
    ) -> None:
        """Assign a placeholder to each new entity, mutating *vocab* in-place."""
        # Build a set of already-used indices per entity type.
        used: dict[str, set[int]] = {}
        for ph in vocab.values():
            inner = ph[1:-1]  # strip < >
            label, idx_str = inner.rsplit("_", 1)
            used.setdefault(label, set()).add(int(idx_str))

        for text, entity_type in detections:
            if text in vocab:
                continue
            label = entity_type.upper()
            indices = used.setdefault(label, set())
            idx = 1
            while idx in indices:
                idx += 1
            vocab[text] = f"<{label}_{idx}>"
            indices.add(idx)

    @staticmethod
    def _replace(text: str, mapping: dict[str, str]) -> str:
        """Replace all keys in *mapping* with their values, longest key first."""
        for key in sorted(mapping, key=len, reverse=True):
            text = text.replace(key, mapping[key])
        return text

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def anonymize(
        self,
        text: str,
        thread_id: Optional[str] = None,
    ) -> tuple[str, dict[str, str]]:
        """Anonymize *text*, returning ``(anonymized_text, vocab)``.

        *vocab* maps each original entity string to its placeholder token.
        """
        tid = thread_id or uuid4().hex
        vocab = dict(self._thread_store.get(tid, {}))
        detections = self._detect(text)
        self._assign(detections, vocab)
        self._thread_store[tid] = vocab
        return self._replace(text, vocab), vocab

    def deanonymize(self, text: str, vocab: dict[str, str]) -> str:
        """Restore original values in *text* using *vocab* (text→placeholder)."""
        reverse = {ph: original for original, ph in vocab.items()}
        return self._replace(text, reverse)

    def anonymize_messages(
        self,
        messages: list[AnyMessage],
        thread_id: Optional[str] = None,
    ) -> tuple[list[AnyMessage], dict[str, str]]:
        """Anonymize a list of LangChain messages, sharing thread context."""
        combined_vocab: dict[str, str] = {}
        for message in messages:
            assert isinstance(message.content, str), (
                "This simple anonymizer only works for string content."
            )
            message.content, vocab = self.anonymize(message.content, thread_id=thread_id)
            combined_vocab.update(vocab)
        return messages, combined_vocab

    def deanonymize_messages(
        self,
        messages: list[AnyMessage],
        thread_id: Optional[str] = None,
        placeholders: Optional[dict[str, str]] = None,
    ) -> list[AnyMessage]:
        """Deanonymize messages using explicit *placeholders* or the thread store."""
        if placeholders is not None:
            vocab = placeholders
        elif thread_id is not None:
            vocab = self._thread_store.get(thread_id, {})
        else:
            vocab = {}
        reverse = {ph: text for text, ph in vocab.items()}
        for message in messages:
            assert isinstance(message.content, str), (
                "This simple anonymizer only works for string content."
            )
            for ph, original in reverse.items():
                message.content = message.content.replace(ph, original)
        return messages


def main():
    extractor = GLiNER2.from_pretrained("fastino/gliner2-base-v1")
    anonymizer = Anonymizer(extractor)
    anonymized_text, vocab = anonymizer.anonymize(
        "Apple Inc. CEO Tim Cook announced iPhone "
        "15 in Cupertino. Cupertino is nice town. "
        "Paris is capital !"
    )
    for original, placeholder in vocab.items():
        print(f"  {original!r} → {placeholder}")

    print("---")
    print(anonymized_text)

    print("---")
    print(anonymizer.deanonymize(anonymized_text, vocab))


if __name__ == "__main__":
    main()
