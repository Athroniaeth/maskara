---
icon: lucide/database
---

# Reference — Pipeline

Module: `piighost.pipeline`

---

## `AnonymizationPipeline`

Session-aware anonymization pipeline with **persistent caching**. Wraps a stateless `Anonymizer` with:

- A `PlaceholderStore` (async) for cross-session persistence
- An in-memory `_results` registry for fast synchronous operations

### Constructor

```python
AnonymizationPipeline(
    anonymizer: Anonymizer,
    labels: Sequence[str],
    store: PlaceholderStore | None = None,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `anonymizer` | `Anonymizer` | — | Stateless anonymization engine (required) |
| `labels` | `Sequence[str]` | — | Entity types to detect (required) |
| `store` | `PlaceholderStore \| None` | `InMemoryPlaceholderStore()` | Persistence backend |

### Methods

#### `anonymize(text) → AnonymizationResult` *(async)*

Anonymizes `text`, caches the result, and registers it in the session registry.

If the exact text has already been processed (cache hit), the stored result is returned without calling the NER model.

```python
result = await pipeline.anonymize("Patrick lives in Paris.")
print(result.anonymized_text)
# <<PERSON_1>> lives in <<LOCATION_1>>.
```

!!! note "SHA-256 cache"
    The cache key is the SHA-256 hash of the source text. Identical texts always return the same result.

#### `deanonymize_text(text) → str`

Replaces all known placeholder tags in `text` with their original values.

Works via **string replacement** (not span-based), so it can deanonymize any string derived from an anonymized text — including LLM-generated tool call arguments.

```python
pipeline.deanonymize_text("Hello, <<PERSON_1>> from <<LOCATION_1>>!")
# "Hello, Patrick from Paris!"
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `text` | `str` | String potentially containing placeholder tags |

**Returns**: `str`

#### `reanonymize_text(text) → str`

Inverse of `deanonymize_text`: replaces each known original value with its placeholder tag.

```python
pipeline.reanonymize_text("Result for Patrick in Paris")
# "Result for <<PERSON_1>> in <<LOCATION_1>>"
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `text` | `str` | String potentially containing original values |

**Returns**: `str`

#### `results` (property)

All results registered during the current session (read-only).

```python
pipeline.results  # tuple[AnonymizationResult, ...]
```

---

## `PlaceholderStore` (Protocol)

Interface for the `AnonymizationResult` persistence backend.

```python
class PlaceholderStore(Protocol):
    async def get(self, key: str) -> AnonymizationResult | None:
        ...

    async def set(self, key: str, result: AnonymizationResult) -> None:
        ...
```

| Method | Description |
|--------|-------------|
| `get(key)` | Retrieve a result by its SHA-256 key, or `None` if absent |
| `set(key, result)` | Persist a result |

The key is always the **SHA-256 hash** of the original source text.

---

## `InMemoryPlaceholderStore`

Default implementation: in-memory storage, suitable for tests and single-process deployments.

```python
InMemoryPlaceholderStore()
```

No configuration needed. Not persistent — data is lost when the process stops.

```python
from piighost.pipeline import InMemoryPlaceholderStore, AnonymizationPipeline

pipeline = AnonymizationPipeline(
    anonymizer=anonymizer,
    labels=["PERSON"],
    store=InMemoryPlaceholderStore(),  # equivalent to the default behavior
)
```

---

## Full example

```python
import asyncio
from piighost.anonymizer import Anonymizer, GlinerDetector
from piighost.pipeline import AnonymizationPipeline
from gliner2 import GLiNER2

model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")
detector = GlinerDetector(model=model)
anonymizer = Anonymizer(detector=detector)

pipeline = AnonymizationPipeline(
    anonymizer=anonymizer,
    labels=["PERSON", "LOCATION"],
)

async def main():
    # Async anonymization
    r1 = await pipeline.anonymize("Patrick is in Lyon.")
    print(r1.anonymized_text)  # <<PERSON_1>> is in <<LOCATION_1>>.

    # Same text → cache hit (no second NER call)
    r2 = await pipeline.anonymize("Patrick is in Lyon.")
    assert r1 is r2  # same object

    # Synchronous deanonymization
    text = pipeline.deanonymize_text("Hello <<PERSON_1>>, welcome to <<LOCATION_1>>.")
    print(text)  # Hello Patrick, welcome to Lyon.

    # Synchronous reanonymization
    text2 = pipeline.reanonymize_text("Patrick replied from Lyon.")
    print(text2)  # <<PERSON_1>> replied from <<LOCATION_1>>.

asyncio.run(main())
```

---

## Custom store

See [Extending PIIGhost — PlaceholderStore](../extending.md#custom-placeholderstore) for Redis and PostgreSQL examples.
