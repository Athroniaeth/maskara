---
icon: lucide/database
---

# Pipeline Reference

Module: `piighost.pipeline`

`AnonymizationPipeline` chains the five stages detect, resolve spans, link entities, resolve entities, and anonymize, plus an optional final `guard` stage. `ThreadAnonymizationPipeline` adds memory and cache scoped by `thread_id` so the same entity keeps the same placeholder across every message of a conversation.

---

## `AnonymizationPipeline`

Stateless pipeline. Each `anonymize()` call is independent. Only the cache (SHA-256 keyed) carries continuity between calls.

### Constructor

!!! note "Every component is a protocol"
    `AnyDetector`, `AnySpanConflictResolver`, `AnyEntityLinker`, `AnyEntityConflictResolver`, `AnyAnonymizer`, `AnyGuardRail`, `AbstractObservationService`. Swap any one of them, see [Extending PIIGhost](../extending.md).

```python
AnonymizationPipeline(
    detector: AnyDetector,
    anonymizer: AnyAnonymizer,
    span_resolver: AnySpanConflictResolver | None = None,
    entity_linker: AnyEntityLinker | None = None,
    entity_resolver: AnyEntityConflictResolver | None = None,
    guard_rail: AnyGuardRail | None = None,
    cache: BaseCache | None = None,
    cache_ttl: int | None = None,
    observation: AbstractObservationService | None = None,
    observation_ph_factory: AnyPlaceholderFactory | None = None,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `detector` | `AnyDetector` | required | Async entity detector |
| `anonymizer` | `AnyAnonymizer` | required | Text-replacement engine and placeholder factory |
| `span_resolver` | `AnySpanConflictResolver` | `ConfidenceSpanConflictResolver()` | Resolves overlapping detections |
| `entity_linker` | `AnyEntityLinker` | `ExactEntityLinker()` | Groups detections into entities |
| `entity_resolver` | `AnyEntityConflictResolver` | `MergeEntityConflictResolver()` | Merges conflicting entities |
| `guard_rail` | `AnyGuardRail` | `DisabledGuardRail()` | Final stage that re-validates the output. Pass a `DetectorGuardRail` to raise `PIIRemainingError` when residual PII is detected |
| `cache` | `BaseCache` | `SimpleMemoryCache()` | aiocache backend for detections and anonymization mappings |
| `cache_ttl` | `int \| None` | `None` | Time-to-live in seconds applied to every cache entry the pipeline writes. `None` lets the backend decide eviction |
| `observation` | `AbstractObservationService` | `NoOpObservationService()` | Observation backend (Langfuse, etc.). The default logs nothing |
| `observation_ph_factory` | `AnyPlaceholderFactory` | `RedactPlaceholderFactory()` | Factory used to redact PII inside observation payloads. The default collapses every entity to `<<REDACT>>`. Pass another factory (for example `RedactCounterPlaceholderFactory`) to number the redactions |

### Methods

#### `anonymize(text, *, metadata=None, root_span=None) -> tuple[str, list[Entity]]` *(async)*

Runs the full pipeline and stores the mapping in cache for later deanonymization.

- `metadata` is forwarded to the observation trace (non-string values are coerced for Langfuse).
- `root_span` lets the caller supply an already-open root span. When provided, the pipeline nests its observations under it instead of opening a new one through the configured service.

```python
anonymized, entities = await pipeline.anonymize("Patrick lives in Paris.")
# <<PERSON:1>> lives in <<LOCATION:1>>.
```

#### `detect_entities(text) -> list[Entity]` *(async)*

Runs only detect → resolve spans → link → resolve entities, with no anonymization or cache write.

#### `deanonymize(anonymized_text) -> tuple[str, list[Entity]]` *(async)*

Looks the anonymized text up in the cache by SHA-256 hash and reconstructs the original via span replacement.

**Raises** `CacheMissError` if the text was never produced by this pipeline.

#### `ph_factory` (property)

The placeholder factory used by the anonymizer.

---

## `ThreadAnonymizationPipeline`

Conversation-aware pipeline. Memory and cache are isolated per `thread_id`, so the same entity keeps the same placeholder across every message of a thread, and there is no cross-thread bleed.

### Constructor

```python
ThreadAnonymizationPipeline(
    detector: AnyDetector,
    anonymizer: AnyAnonymizer,
    entity_linker: AnyEntityLinker | None = None,
    entity_resolver: AnyEntityConflictResolver | None = None,
    span_resolver: AnySpanConflictResolver | None = None,
    guard_rail: AnyGuardRail | None = None,
    cache: BaseCache | None = None,
    cache_ttl: int | None = None,
    max_threads: int | None = None,
    observation: AbstractObservationService | None = None,
    observation_ph_factory: AnyPlaceholderFactory | None = None,
)
```

In addition to every parameter of `AnonymizationPipeline`:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_threads` | `int \| None` | `None` | Maximum number of conversation memories kept in RAM. When the cap is reached, the least recently used memory is evicted. `None` disables the cap |

!!! warning "Reversible factory required"
    The constructor rejects placeholder factories that are not tagged `PreservesIdentity`. Use `LabelCounterPlaceholderFactory` or `LabelHashPlaceholderFactory`, the two reversible factories shipped.

!!! note "Multi-instance deployment"
    The default `SimpleMemoryCache` is process-local. In a multi-worker deployment, switch to a shared backend (Redis) so placeholders stay consistent across workers. The constructor warns once per process when this is the case. See [Multi-instance deployment](../multi-instance.md).

### Methods

#### `anonymize(text, thread_id="default", *, metadata=None, root_span=None) -> tuple[str, list[Entity]]` *(async)*

Detects entities, records them in `thread_id`'s memory, then anonymizes using every entity already known to that thread. Counters stay stable from one message to the next.

When the pipeline opens its own root span (no `root_span=` argument), the thread id is forwarded to the observation backend as `session_id` (skipped for the literal `"default"`).

```python
a1, _ = await pipeline.anonymize("Patrick lives in Paris.", thread_id="user-A")
a2, _ = await pipeline.anonymize("Patrick wrote to Marie.", thread_id="user-A")
# Patrick keeps <<PERSON:1>> across both turns.
```

#### `deanonymize(anonymized_text, thread_id="default") -> tuple[str, list[Entity]]` *(async)*

Returns the original text directly from the cache. Unlike the base implementation, this does not re-run span replacement, which would not work on positions coming from different messages.

**Raises** `CacheMissError` if the text was never produced in this thread.

#### `anonymize_with_ent(text, thread_id="default") -> str`

Synchronous, single-pass replacement of every known PII surface form (and its variants) by its placeholder. Works on text that did not flow through the pipeline (tool arguments, mid-stream LLM output).

#### `deanonymize_with_ent(text, thread_id="default") -> str` *(async)*

Inverse: replaces every known placeholder by its original surface form. The result is also cached so a later `deanonymize()` call can find it.

#### `override_detections(text, detections, thread_id="default") -> None` *(async)*

Overwrites the cached detections for *text*. Use it when the user corrects what the detector found. The next `anonymize()` call on this text will reuse the corrected detections instead of running the detector again.

#### `get_memory(thread_id="default") -> ConversationMemory`

Returns the thread's memory, created on first access. Refreshes its LRU position when `max_threads` is set.

#### `get_resolved_entities(thread_id="default") -> list[Entity]`

Every entity in the thread's memory, merged by the entity resolver.

#### `clear_memory(thread_id) -> None`

Drop the memory for *thread_id*. Call this when a conversation ends so entities don't pile up.

#### `clear_all_memories() -> None`

Drop every conversation memory tracked by the pipeline.

---

## `ConversationMemory`

Module: `piighost.pipeline`

Default in-memory implementation of `AnyConversationMemory`. Accumulates entities across a thread and deduplicates them by `(text.lower(), label)`. Surface-form variants of the same canonical entity (e.g. `"france"` after `"France"`) are merged into the existing entity so `anonymize_with_ent` can replace every observed spelling.

### Protocol

```python
class AnyConversationMemory(Protocol):
    entities_by_hash: dict[str, list[Entity]]

    @property
    def all_entities(self) -> list[Entity]: ...

    def record(self, text_hash: str, entities: list[Entity]) -> None: ...
```

### Members

- `record(text_hash, entities)` records entities for one message and merges variants.
- `all_entities` (property) returns the flat deduplicated list, in insertion order.

---

## Cache

The pipelines use **aiocache** with configurable backends. Keys carry stable prefixes:

- `detect:<sha256>` for the detector output of a given text.
- `anon:anonymized:<sha256>` for the `anonymized text → (original, entities)` mapping consumed by `deanonymize`.

`ThreadAnonymizationPipeline` additionally prefixes every key with `<thread_id>:` to isolate conversations.

```python
from aiocache import RedisCache

pipeline = ThreadAnonymizationPipeline(
    detector=detector,
    anonymizer=anonymizer,
    cache=RedisCache(endpoint="redis", port=6379),
    cache_ttl=86_400,  # one day
)
```

---

## Observation

Any `AbstractObservationService` produces a 4-stage child trace (`detect`, `link`, `placeholder`, `guard`) under a parent `piighost.anonymize_pipeline` span. The default `NoOpObservationService` logs nothing and has zero overhead. The shipped backend is `LangfuseObservationService(client)`.

By default the pipeline runs a dedicated placeholder factory on every PII span before the payload reaches the backend. The default factory, `RedactPlaceholderFactory()`, collapses every entity to `<<REDACT>>` and applies it to the root span's `input`, `detect.input/output`, `link.input/output`, and `placeholder.input`. Already-anonymized payloads (`placeholder.output`, `guard.input/output`, the root span's `output`) pass through unchanged. Pass a different `observation_ph_factory=` to use another factory. See [Security](../security.md) for the full threat-model rationale.

---

## Full example

```python
import asyncio

from gliner2 import GLiNER2

from piighost.anonymizer import Anonymizer
from piighost.detector.gliner2 import Gliner2Detector
from piighost.pipeline import ThreadAnonymizationPipeline
from piighost.placeholder import LabelCounterPlaceholderFactory

model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")
detector = Gliner2Detector(model=model, threshold=0.5, labels=["PERSON", "LOCATION"])
anonymizer = Anonymizer(ph_factory=LabelCounterPlaceholderFactory())

pipeline = ThreadAnonymizationPipeline(detector=detector, anonymizer=anonymizer)


async def main():
    a1, _ = await pipeline.anonymize("Patrick is in Lyon.", thread_id="user-A")
    print(a1)  # <<PERSON:1>> is in <<LOCATION:1>>.

    original, _ = await pipeline.deanonymize(a1, thread_id="user-A")
    print(original)  # Patrick is in Lyon.


asyncio.run(main())
```
