---
icon: lucide/puzzle
---

# Extending PIIGhost

PIIGhost is built around **protocols** (Python structural subtyping). Every pipeline stage is an injection point where you can plug in your own implementation without touching the rest of the code.

```mermaid
flowchart LR
    A[AnonymizationPipeline] -->|inject| B[AnyDetector]
    A -->|inject| C[AnySpanConflictResolver]
    A -->|inject| D[AnyEntityLinker]
    A -->|inject| E[AnyEntityConflictResolver]
    A -->|inject| F[AnyAnonymizer]
    F -->|inject| G[AnyPlaceholderFactory]
```

No base class to inherit from. Simply implement the required method Python checks compatibility at call time.

---

## Custom `AnyDetector`

**When to use**: replace GLiNER2 with spaCy, a remote API call, an allowlist, etc.

### Protocol

```python
class AnyDetector(Protocol):
    async def detect(self, text: str) -> list[Detection]: ...
```

### Example spaCy detector

```python
import spacy
from piighost.models import Detection, Span

class SpacyDetector:
    """NER detector backed by spaCy."""

    def __init__(self, model_name: str = "en_core_web_sm"):
        self._nlp = spacy.load(model_name)

    async def detect(self, text: str) -> list[Detection]:
        doc = self._nlp(text)
        return [
            Detection(
                text=ent.text,
                label=ent.label_,
                position=Span(start_pos=ent.start_char, end_pos=ent.end_char),
                confidence=1.0,
            )
            for ent in doc.ents
        ]
```

### Example allowlist detector

```python
import re
from piighost.models import Detection, Span

class AllowlistDetector:
    """Detects entities from a fixed list (useful for tests or structured data)."""

    def __init__(self, allowlist: dict[str, str]):
        # {"Patrick Dupont": "PERSON", "Paris": "LOCATION"}
        self._allowlist = allowlist

    async def detect(self, text: str) -> list[Detection]:
        detections = []
        for fragment, label in self._allowlist.items():
            for match in re.finditer(re.escape(fragment), text):
                detections.append(Detection(
                    text=match.group(),
                    label=label,
                    position=Span(start_pos=match.start(), end_pos=match.end()),
                    confidence=1.0,
                ))
        return detections
```

### Usage

```python
from piighost.pipeline import AnonymizationPipeline

pipeline = AnonymizationPipeline(
    detector=SpacyDetector("en_core_web_sm"),
    ...,
)
```

---

## Custom `AnySpanConflictResolver`

**When to use**: different strategy for handling overlapping detections (e.g., prefer longer spans).

### Protocol

```python
class AnySpanConflictResolver(Protocol):
    def resolve(self, detections: list[Detection]) -> list[Detection]: ...
```

### Example longest span wins

```python
from piighost.models import Detection

class LongestSpanResolver:
    """Keeps the longest detection when spans overlap."""

    def resolve(self, detections: list[Detection]) -> list[Detection]:
        # Sort by span length descending
        sorted_dets = sorted(
            detections,
            key=lambda d: d.position.end_pos - d.position.start_pos,
            reverse=True,
        )
        kept: list[Detection] = []
        for det in sorted_dets:
            if not any(det.position.overlaps(k.position) for k in kept):
                kept.append(det)
        return kept
```

---

## Custom `AnyEntityLinker`

**When to use**: different logic for grouping detections into entities (e.g., fuzzy matching, phonetic variants).

### Protocol

```python
class AnyEntityLinker(Protocol):
    def link(self, text: str, detections: list[Detection]) -> list[Entity]: ...
```

---

## Custom `AnyEntityConflictResolver`

**When to use**: different strategy for merging entities that refer to the same PII.

### Protocol

```python
class AnyEntityConflictResolver(Protocol):
    def resolve(self, entities: list[Entity]) -> list[Entity]: ...
```

The built-in implementations:

- `MergeEntityConflictResolver` union-find algorithm merging entities with shared detections
- `FuzzyEntityConflictResolver` merges entities with similar canonical text using Jaro-Winkler similarity

---

## Custom `AnyPlaceholderFactory`

**When to use**: UUID tags for full anonymity, custom format, integration with an external token system.

### Protocol

```python
class AnyPlaceholderFactory(Protocol):
    def create(self, entities: list[Entity]) -> dict[Entity, str]: ...
```

### Example UUID tags

```python
import uuid
from piighost.models import Entity

class UUIDPlaceholderFactory:
    """Generates opaque UUID tags, e.g. <<a3f2-1b4c>>."""

    def create(self, entities: list[Entity]) -> dict[Entity, str]:
        result: dict[Entity, str] = {}
        seen: dict[str, str] = {}  # canonical → token

        for entity in entities:
            canonical = entity.detections[0].text.lower()
            if canonical not in seen:
                seen[canonical] = f"<<{uuid.uuid4().hex[:8]}>>"
            result[entity] = seen[canonical]

        return result
```

### Example custom format

```python
from collections import defaultdict
from piighost.models import Entity

class BracketPlaceholderFactory:
    """Generates tags in the format [PERSON:1], [LOCATION:2], etc."""

    def create(self, entities: list[Entity]) -> dict[Entity, str]:
        result: dict[Entity, str] = {}
        counters: dict[str, int] = defaultdict(int)

        for entity in entities:
            label = entity.label
            counters[label] += 1
            result[entity] = f"[{label}:{counters[label]}]"

        return result
```

### Usage

```python
from piighost.anonymizer import Anonymizer

anonymizer = Anonymizer(ph_factory=UUIDPlaceholderFactory())
```

---

## Full composition

All components are independent and can be freely combined:

```python
from piighost.anonymizer import Anonymizer
from piighost.conversation_memory import ConversationMemory
from piighost.conversation_pipeline import ConversationAnonymizationPipeline
from piighost.linker.entity import ExactEntityLinker
from piighost.entity_resolver import FuzzyEntityConflictResolver
from piighost.middleware import PIIAnonymizationMiddleware
from piighost.span_resolver import ConfidenceSpanConflictResolver

pipeline = ConversationAnonymizationPipeline(
    detector=SpacyDetector("en_core_web_sm"),  # Your detector
    span_resolver=ConfidenceSpanConflictResolver(),  # Or your resolver
    entity_linker=ExactEntityLinker(),  # Or your linker
    entity_resolver=FuzzyEntityConflictResolver(),  # Fuzzy merging
    anonymizer=Anonymizer(UUIDPlaceholderFactory()),  # Opaque UUID tags
    memory=ConversationMemory(),
)

middleware = PIIAnonymizationMiddleware(pipeline=pipeline)
```

---

## Testing your components

Protocols make unit testing straightforward. Use `ExactMatchDetector` for deterministic tests:

```python
import pytest
from piighost.anonymizer import Anonymizer
from piighost.detector import ExactMatchDetector
from piighost.linker.entity import ExactEntityLinker
from piighost.entity_resolver import MergeEntityConflictResolver
from piighost.pipeline import AnonymizationPipeline
from piighost.placeholder import CounterPlaceholderFactory
from piighost.span_resolver import ConfidenceSpanConflictResolver


@pytest.mark.asyncio
async def test_my_pipeline():
    pipeline = AnonymizationPipeline(
        detector=ExactMatchDetector([("Alice", "PERSON")]),
        span_resolver=ConfidenceSpanConflictResolver(),
        entity_linker=ExactEntityLinker(),
        entity_resolver=MergeEntityConflictResolver(),
        anonymizer=Anonymizer(CounterPlaceholderFactory()),
    )

    anonymized, entities = await pipeline.anonymize("Alice lives in Lyon.")
    assert "<<PERSON_1>>" in anonymized
    assert "Alice" not in anonymized
```

!!! tip "ExactMatchDetector in CI"
    Always use `ExactMatchDetector` (or equivalent) in CI to avoid loading the GLiNER2 model (~500 MB) during automated tests.
