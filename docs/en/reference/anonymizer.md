---
icon: lucide/scan-text
---

# Reference — Anonymizer

Module: `piighost.anonymizer`

---

## `Anonymizer`

Orchestrator of the 4-stage anonymization pipeline. **Stateless** class — no internal state between calls.

### Constructor

```python
Anonymizer(
    detector: EntityDetector,
    occurrence_finder: OccurrenceFinder | None = None,
    placeholder_factory: PlaceholderFactory | None = None,
    replacer: SpanReplacer | None = None,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `detector` | `EntityDetector` | — | NER backend (required) |
| `occurrence_finder` | `OccurrenceFinder \| None` | `RegexOccurrenceFinder()` | Occurrence location strategy |
| `placeholder_factory` | `PlaceholderFactory \| None` | `CounterPlaceholderFactory()` | Tag generation strategy |
| `replacer` | `SpanReplacer \| None` | `SpanReplacer()` | Span replacement engine |

### Methods

#### `anonymize(text, labels) → AnonymizationResult`

Anonymizes `text` by detecting and replacing sensitive entities.

```python
result = anonymizer.anonymize(
    "Patrick lives in Paris. Patrick loves Paris.",
    labels=["PERSON", "LOCATION"],
)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `text` | `str` | Source text |
| `labels` | `Sequence[str]` | Entity types to detect (e.g. `["PERSON", "LOCATION"]`) |

**Returns**: `AnonymizationResult`

#### `deanonymize(result) → str`

Restores the original text from an `AnonymizationResult` (based on precomputed reverse spans).

```python
original = anonymizer.deanonymize(result)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `result` | `AnonymizationResult` | Result previously returned by `anonymize` |

**Returns**: `str` — the original text

---

## `GlinerDetector`

Implementation of `EntityDetector` using the **GLiNER2** model.

### Constructor

```python
@dataclass
GlinerDetector(
    model: GLiNER2,
    threshold: float = 0.5,
    flat_ner: bool = True,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | `GLiNER2` | — | GLiNER2 model instance (required) |
| `threshold` | `float` | `0.5` | Minimum confidence score (0.0–1.0) |
| `flat_ner` | `bool` | `True` | Flat NER mode (no nested entities) |

### Usage

```python
from gliner2 import GLiNER2
from piighost.anonymizer import GlinerDetector

model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")
detector = GlinerDetector(model=model, threshold=0.5, flat_ner=True)

entities = detector.detect("Patrick lives in Paris", ["PERSON", "LOCATION"])
# [Entity(text='Patrick', label='PERSON', start=0, end=7, score=0.97),
#  Entity(text='Paris', label='LOCATION', start=17, end=22, score=0.99)]
```

---

## `EntityDetector` (Protocol)

Interface to implement for a custom detector.

```python
class EntityDetector(Protocol):
    def detect(self, text: str, labels: Sequence[str]) -> list[Entity]:
        ...
```

See [Extending PIIGhost](../extending.md#custom-entitydetector) for examples.

---

## `OccurrenceFinder` (Protocol)

Interface for finding all positions of a fragment in a text.

```python
class OccurrenceFinder(Protocol):
    def find_all(self, text: str, fragment: str) -> list[tuple[int, int]]:
        ...
```

### `RegexOccurrenceFinder`

Default implementation: uses `\bFRAGMENT\b` with `re.IGNORECASE`.

```python
RegexOccurrenceFinder(flags: re.RegexFlag = re.IGNORECASE)
```

```python
finder = RegexOccurrenceFinder()
finder.find_all("Hello Patrick, APatrick", "Patrick")
# [(6, 13)]  — "APatrick" is NOT returned (no word-boundary)
```

---

## `PlaceholderFactory` (Protocol)

Interface for generating replacement tags.

```python
class PlaceholderFactory(Protocol):
    def get_or_create(self, original: str, label: str) -> Placeholder:
        ...

    def reset(self) -> None:
        ...
```

### `CounterPlaceholderFactory`

Default implementation: generates sequential `<<LABEL_N>>` tags.

```python
CounterPlaceholderFactory(template: str = "<<{label}_{index}>>")
```

```python
factory = CounterPlaceholderFactory()
factory.get_or_create("Patrick", "PERSON").replacement  # '<<PERSON_1>>'
factory.get_or_create("Marie", "PERSON").replacement    # '<<PERSON_2>>'
factory.get_or_create("Patrick", "PERSON").replacement  # '<<PERSON_1>>' (cached)
factory.reset()  # clears counters and cache
```

### `HashPlaceholderFactory`

Generates deterministic, opaque hash-based tags — the same strategy as LangChain's built-in PII redaction middleware.

```python
HashPlaceholderFactory(
    digest_length: int = 8,
    template: str = "<{label}:{digest}>",
)
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `digest_length` | `8` | Number of hex characters from the SHA-256 digest |
| `template` | `"<{label}:{digest}>"` | Format string with `{label}` and `{digest}` |

```python
from piighost.anonymizer import HashPlaceholderFactory

factory = HashPlaceholderFactory()
factory.get_or_create("Patrick", "PERSON").replacement  # '<PERSON:3b4c5d6e>'
factory.get_or_create("Patrick", "PERSON").replacement  # '<PERSON:3b4c5d6e>' (same hash)
factory.get_or_create("Marie", "PERSON").replacement    # '<PERSON:9f2a1c7b>' (different)
factory.reset()  # clears cache
```

The hash is computed from the original text only — the same entity always produces the same placeholder, regardless of encounter order.

**Usage with `Anonymizer`:**

```python
anonymizer = Anonymizer(
    detector=detector,
    placeholder_factory=HashPlaceholderFactory(digest_length=12),
)
```

---

## Data models

### `Entity`

Named entity detected by the NER model.

```python
@dataclass(frozen=True)
class Entity:
    text: str    # Surface form: "Patrick"
    label: str   # Type: "PERSON"
    start: int   # Inclusive start index
    end: int     # Exclusive end index
    score: float # Confidence score (0.0–1.0)
```

### `Placeholder`

Link between an original fragment and its replacement tag.

```python
@dataclass(frozen=True)
class Placeholder:
    original: str     # "Patrick"
    label: str        # "PERSON"
    replacement: str  # "<<PERSON_1>>"
```

### `AnonymizationResult`

Full output of an anonymization pass.

```python
@dataclass(frozen=True)
class AnonymizationResult:
    original_text: str              # Source text
    anonymized_text: str            # Text with placeholders
    placeholders: tuple[Placeholder, ...]  # All created placeholders
    reverse_spans: tuple            # Reverse spans for deanonymization
```

!!! note "Immutability"
    All models are **frozen dataclasses** (`frozen=True`) — they are thread-safe and hashable.
