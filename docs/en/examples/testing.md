---
icon: lucide/test-tube
tags:
  - Testing
---

# Testing

How to unit-test PIIGhost pipelines and custom components. The recommended approach uses `ExactMatchDetector` to avoid downloading an NER model in CI, but the patterns here apply to any detector.

---

## Deterministic detection with `ExactMatchDetector`

`ExactMatchDetector` takes a list of `(text, label)` pairs and finds their word-boundary occurrences. No model, no network, fully predictable output.

```python
from piighost.anonymizer import Anonymizer
from piighost.detector import ExactMatchDetector
from piighost.linker.entity import ExactEntityLinker
from piighost.resolver import MergeEntityConflictResolver, ConfidenceSpanConflictResolver
from piighost.pipeline import AnonymizationPipeline
from piighost.placeholder import LabelCounterPlaceholderFactory

detector = ExactMatchDetector([("Patrick", "PERSON"), ("Paris", "LOCATION")])
span_resolver = ConfidenceSpanConflictResolver()
entity_linker = ExactEntityLinker()
entity_resolver = MergeEntityConflictResolver()
anonymizer = Anonymizer(LabelCounterPlaceholderFactory())

pipeline = AnonymizationPipeline(
    detector=detector,
    span_resolver=span_resolver,
    entity_linker=entity_linker,
    entity_resolver=entity_resolver,
    anonymizer=anonymizer,
)

anonymized, entities = await pipeline.anonymize("Patrick lives in Paris.")
assert anonymized == "<<PERSON:1>> lives in <<LOCATION:1>>."
```

---

## Pytest pattern

```python
import pytest
from piighost.anonymizer import Anonymizer
from piighost.detector import ExactMatchDetector
from piighost.linker.entity import ExactEntityLinker
from piighost.resolver import MergeEntityConflictResolver, ConfidenceSpanConflictResolver
from piighost.pipeline import AnonymizationPipeline
from piighost.placeholder import LabelCounterPlaceholderFactory


@pytest.mark.asyncio
async def test_my_pipeline():
    detector = ExactMatchDetector([("Alice", "PERSON")])
    span_resolver = ConfidenceSpanConflictResolver()
    entity_linker = ExactEntityLinker()
    entity_resolver = MergeEntityConflictResolver()
    anonymizer = Anonymizer(LabelCounterPlaceholderFactory())

    pipeline = AnonymizationPipeline(
        detector=detector,
        span_resolver=span_resolver,
        entity_linker=entity_linker,
        entity_resolver=entity_resolver,
        anonymizer=anonymizer,
    )

    anonymized, entities = await pipeline.anonymize("Alice lives in Lyon.")
    assert "<<PERSON:1>>" in anonymized
    assert "Alice" not in anonymized
```

!!! tip "ExactMatchDetector in CI"
    Always use `ExactMatchDetector` (or equivalent) in CI to avoid loading an NER model during automated tests.

---

## Testing custom components

Every pipeline stage is a protocol, which makes each component swappable in isolation for tests. See [Extending PIIGhost](../extending.md) for protocol definitions, then inject your custom component alongside `ExactMatchDetector` above.
