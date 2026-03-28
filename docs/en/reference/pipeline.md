---
icon: lucide/database
---

# Reference Pipeline

Module: `piighost.pipeline`

---

## `AnonymizationPipeline`

Orchestrates the full anonymization pipeline: detect → resolve spans → link entities → resolve entities → anonymize. Uses aiocache for caching detector results and anonymization mappings.

### Constructor

```python
AnonymizationPipeline(
    detector: AnyDetector,
    span_resolver: AnySpanConflictResolver,
    entity_linker: AnyEntityLinker,
    entity_resolver: AnyEntityConflictResolver,
    anonymizer: AnyAnonymizer,
    cache: BaseCache | None = None,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `detector` | `AnyDetector` | | Async entity detector (required) |
| `span_resolver` | `AnySpanConflictResolver` | | Handles overlapping detections (required) |
| `entity_linker` | `AnyEntityLinker` | | Groups detections into entities (required) |
| `entity_resolver` | `AnyEntityConflictResolver` | | Merges conflicting entities (required) |
| `anonymizer` | `AnyAnonymizer` | | Text replacement engine (required) |
| `cache` | `BaseCache \| None` | `Cache(Cache.MEMORY)` | aiocache instance for caching |

### Methods

#### `detect_entities(text) -> list[Entity]` *(async)*

Runs the detection pipeline: detect → resolve spans → link → resolve entities.

```python
entities = await pipeline.detect_entities("Patrick lives in Paris.")
```

#### `anonymize(text) -> tuple[str, list[Entity]]` *(async)*

Runs the full pipeline and stores the mapping in cache for later deanonymization.

```python
anonymized, entities = await pipeline.anonymize("Patrick lives in Paris.")
print(anonymized)
# <<PERSON_1>> lives in <<LOCATION_1>>.
```

!!! note "SHA-256 cache"
    Detector results are cached by `detect:<hash>` and anonymization mappings by `anon:anonymized:<hash>`.

#### `deanonymize(anonymized_text) -> tuple[str, list[Entity]]` *(async)*

Deanonymizes using the anonymized text as cache lookup key.

```python
original, entities = await pipeline.deanonymize(anonymized)
print(original)
# Patrick lives in Paris.
```

**Raises**: `CacheMissError` if the anonymized text was never produced by this pipeline.

#### `ph_factory` (property)

Returns the placeholder factory used by the anonymizer.

```python
pipeline.ph_factory  # AnyPlaceholderFactory
```

---

## `ConversationAnonymizationPipeline`

Module: `piighost.conversation_pipeline`

Extends `AnonymizationPipeline` with conversation memory for consistent entity tracking across messages.

### Constructor

```python
ConversationAnonymizationPipeline(
    detector: AnyDetector,
    span_resolver: AnySpanConflictResolver,
    entity_linker: AnyEntityLinker,
    entity_resolver: AnyEntityConflictResolver,
    anonymizer: AnyAnonymizer,
    memory: AnyConversationMemory | None = None,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `memory` | `AnyConversationMemory \| None` | `ConversationMemory()` | Conversation memory instance |
| *(others)* | | | Same as `AnonymizationPipeline` |

### Methods

#### `anonymize(text) -> tuple[str, list[Entity]]` *(async)*

Detects entities, records them in memory, then anonymizes using all known entities for consistent token assignment.

```python
anonymized, entities = await conv_pipeline.anonymize("Patrick lives in Paris.")
# <<PERSON_1>> lives in <<LOCATION_1>>.
```

#### `deanonymize_with_ent(text) -> str` *(async)*

Replaces all known tokens with original values via `str.replace`. Works on any text containing tokens, even text never anonymized by this pipeline (e.g., LLM-generated output, tool arguments). Tokens are replaced **longest-first** to avoid partial matches.

```python
result = await conv_pipeline.deanonymize_with_ent("Hello <<PERSON_1>>!")
# "Hello Patrick!"
```

#### `anonymize_with_ent(text) -> str`

Replaces all known original values with tokens via `str.replace`. Replaces all spelling variants of each entity. Values are replaced **longest-first**.

```python
result = conv_pipeline.anonymize_with_ent("Result for Patrick in Paris")
# "Result for <<PERSON_1>> in <<LOCATION_1>>"
```

#### `resolved_entities` (property)

All entities from memory, merged by the entity resolver.

```python
conv_pipeline.resolved_entities  # list[Entity]
```

---

## `ConversationMemory`

Module: `piighost.conversation_memory`

In-memory conversation memory that accumulates entities across messages, deduplicating by `(text.lower(), label)`.

### Protocol

```python
class AnyConversationMemory(Protocol):
    entities_by_hash: dict[str, list[Entity]]

    @property
    def all_entities(self) -> list[Entity]: ...

    def record(self, text_hash: str, entities: list[Entity]) -> None: ...
```

### Methods

#### `record(text_hash, entities) -> None`

Records entities for a message. Deduplicates against already known entities.

#### `all_entities` (property)

Flat deduplicated list of all entities, in insertion order.

---

## Caching

The pipeline uses **aiocache** with configurable backends. By default, `Cache(Cache.MEMORY)` is used (in-memory, not persistent).

Cache keys use prefixes to avoid collisions:

- `detect:<hash>` detector results
- `anon:anonymized:<hash>` anonymization mappings (anonymized text → original + entities)

To use a different cache backend (Redis, Memcached), pass an aiocache `BaseCache` instance:

```python
from aiocache import Cache

pipeline = AnonymizationPipeline(
    ...,
    cache=Cache(Cache.REDIS, endpoint="localhost", port=6379),
)
```

---

## Full example

```python
import asyncio
from piighost.anonymizer import Anonymizer
from piighost.detector import Gliner2Detector
from piighost.linker.entity import ExactEntityLinker
from piighost.entity_resolver import MergeEntityConflictResolver
from piighost.pipeline import AnonymizationPipeline
from piighost.placeholder import CounterPlaceholderFactory
from piighost.span_resolver import ConfidenceSpanConflictResolver
from gliner2 import GLiNER2

model = GLiNER2.from_pretrained("urchade/gliner_multi_pii-v1")

pipeline = AnonymizationPipeline(
    detector=Gliner2Detector(model=model, labels=["PERSON", "LOCATION"], threshold=0.5),
    span_resolver=ConfidenceSpanConflictResolver(),
    entity_linker=ExactEntityLinker(),
    entity_resolver=MergeEntityConflictResolver(),
    anonymizer=Anonymizer(CounterPlaceholderFactory()),
)


async def main():
    # Async anonymization
    anonymized, entities = await pipeline.anonymize("Patrick is in Lyon.")
    print(anonymized)  # <<PERSON_1>> is in <<LOCATION_1>>.

    # Deanonymize via cache lookup
    original, _ = await pipeline.deanonymize(anonymized)
    print(original)  # Patrick is in Lyon.


asyncio.run(main())
```
