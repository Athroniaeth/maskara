---
icon: lucide/code
---

# Basic usage

This page covers the fundamental usages of the library without any LangChain integration.

---

## Simple anonymization

```python
from gliner2 import GLiNER2
from piighost.anonymizer import Anonymizer, GlinerDetector

# Load the GLiNER2 model
model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")

# Create the detector with a confidence threshold
detector = GlinerDetector(model=model, threshold=0.5, flat_ner=True)

# Create the anonymizer
anonymizer = Anonymizer(detector=detector)

# Anonymize a text
result = anonymizer.anonymize(
    "Patrick lives in Paris. Patrick loves Paris.",
    labels=["PERSON", "LOCATION"],
)

print(result.anonymized_text)
# <<PERSON_1>> lives in <<LOCATION_1>>. <<PERSON_1>> loves <<LOCATION_1>>.

print(result.original_text)
# Patrick lives in Paris. Patrick loves Paris.

# Inspect the created placeholders
for placeholder in result.placeholders:
    print(f"{placeholder.original!r} → {placeholder.replacement!r} ({placeholder.label})")
# 'Patrick' → '<<PERSON_1>>' (PERSON)
# 'Paris' → '<<LOCATION_1>>' (LOCATION)
```

---

## Deanonymization

```python
# Restore the original text from an AnonymizationResult
original = anonymizer.deanonymize(result)
print(original)
# Patrick lives in Paris. Patrick loves Paris.
```

!!! note "Span-based"
    `Anonymizer.deanonymize()` uses **precomputed reverse spans** — it is character-precise but requires keeping the `AnonymizationResult` object.

---

## Multiple entity types

```python
result = anonymizer.anonymize(
    "Mary Smith works at Acme Corp in Lyon.",
    labels=["PERSON", "ORGANIZATION", "LOCATION"],
)

print(result.anonymized_text)
# <<PERSON_1>> works at <<ORGANIZATION_1>> in <<LOCATION_1>>.
```

---

## Session pipeline with caching

For multi-message scenarios (conversations), `AnonymizationPipeline` maintains a placeholder registry and avoids re-detecting the same entities.

```python
import asyncio
from piighost.pipeline import AnonymizationPipeline

pipeline = AnonymizationPipeline(
    anonymizer=anonymizer,
    labels=["PERSON", "LOCATION"],
)

async def conversation():
    # First message: NER detection + caching
    r1 = await pipeline.anonymize("Patrick is in Paris.")
    print(r1.anonymized_text)
    # <<PERSON_1>> is in <<LOCATION_1>>.

    # Same text again: result from cache (no second NER call)
    r2 = await pipeline.anonymize("Patrick is in Paris.")
    print(r2.anonymized_text)
    # <<PERSON_1>> is in <<LOCATION_1>>.

    # Synchronous deanonymization on any derived string
    print(pipeline.deanonymize_text("Hello, <<PERSON_1>>!"))
    # Hello, Patrick!

    # Reanonymize (original → placeholder)
    print(pipeline.reanonymize_text("Answer for Patrick in Paris"))
    # Answer for <<PERSON_1>> in <<LOCATION_1>>

asyncio.run(conversation())
```

---

## Custom store (Redis, PostgreSQL…)

By default, the pipeline uses an in-memory store. For cross-process persistence, implement `PlaceholderStore`:

```python
from piighost.pipeline import PlaceholderStore, AnonymizationPipeline
from piighost.anonymizer.models import AnonymizationResult
import pickle

class RedisPlaceholderStore:
    def __init__(self, client):
        self._client = client

    async def get(self, key: str) -> AnonymizationResult | None:
        data = await self._client.get(f"piighost:{key}")
        return pickle.loads(data) if data else None

    async def set(self, key: str, result: AnonymizationResult) -> None:
        await self._client.set(f"piighost:{key}", pickle.dumps(result))

# Inject the Redis store
pipeline = AnonymizationPipeline(
    anonymizer=anonymizer,
    labels=["PERSON", "LOCATION"],
    store=RedisPlaceholderStore(redis_client),
)
```

---

## Inspecting results

`AnonymizationResult` exposes all information from the anonymization pass:

```python
result = anonymizer.anonymize(
    "Contact John Martin at the Lyon office.",
    labels=["PERSON", "LOCATION"],
)

# Anonymized text
print(result.anonymized_text)

# Iterate over placeholders
for p in result.placeholders:
    print(f"'{p.original}' → '{p.replacement}' [{p.label}]")

# Count anonymized entities
print(f"{len(result.placeholders)} entity(ies) anonymized")
```

---

## Testing without loading GLiNER2

In tests, use a `FakeDetector` to avoid downloading the model:

```python
from typing import Sequence
from piighost.anonymizer.models import Entity
from piighost.anonymizer import Anonymizer

class FakeDetector:
    def __init__(self, entities: list[Entity]):
        self._entities = entities

    def detect(self, text: str, labels: Sequence[str]) -> list[Entity]:
        return self._entities

# Deterministic detection without an NER model
fake = FakeDetector([
    Entity(text="Patrick", label="PERSON", start=0, end=7, score=1.0),
    Entity(text="Paris", label="LOCATION", start=17, end=22, score=1.0),
])
anonymizer = Anonymizer(detector=fake)
```

See also [Extending PIIGhost](../extending.md) for creating other custom components.
