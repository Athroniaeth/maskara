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

**Raises**: `IrreversibleAnonymizationError` if the placeholder factory is not reversible.

#### `reversible` (property)

Returns `True` if the placeholder factory supports deanonymization.

```python
anonymizer = Anonymizer(detector=detector)
anonymizer.reversible  # True (CounterPlaceholderFactory is the default)
anonymizer.check_reversible()  # no-op

anonymizer = Anonymizer(detector=detector, placeholder_factory=RedactPlaceholderFactory())
anonymizer.reversible  # False
anonymizer.check_reversible()  # raises IrreversibleAnonymizationError
```

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

## `PlaceholderFactory` (ABC)

Abstract base class for all placeholder factories. Provides two polymorphic methods for reversibility checks — no `isinstance` needed.

```python
class PlaceholderFactory(ABC):
    def get_or_create(self, original: str, label: str) -> Placeholder:
        ...

    def reset(self) -> None:
        ...

    @property
    def reversible(self) -> bool:
        """Returns False by default."""

    def check_reversible(self) -> None:
        """Raises IrreversibleAnonymizationError by default."""
```

Use `factory.reversible` to check at runtime, or `factory.check_reversible()` to raise if not supported.

### `ReversiblePlaceholderFactory` (ABC)

Base class for factories that produce **unique, distinguishable** replacement tags. Factories inheriting from this class guarantee that each `(original, label)` pair gets a distinct tag, making deanonymization possible.

`CounterPlaceholderFactory` and `HashPlaceholderFactory` both inherit from `ReversiblePlaceholderFactory`.

Overrides `reversible` to return `True` and `check_reversible()` to do nothing.

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

### `RedactPlaceholderFactory`

Replaces **all** entities with the same opaque tag (`[REDACTED]`). No index, no label, no distinction between entities — maximum privacy, zero information leakage.

```python
RedactPlaceholderFactory(tag: str = "[REDACTED]")
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `tag` | `"[REDACTED]"` | The replacement string for all entities |

```python
from piighost.anonymizer import RedactPlaceholderFactory

factory = RedactPlaceholderFactory()
factory.get_or_create("Patrick", "PERSON").replacement   # '[REDACTED]'
factory.get_or_create("Paris", "LOCATION").replacement    # '[REDACTED]'
factory.get_or_create("alice@example.com", "EMAIL").replacement  # '[REDACTED]'
```

**Usage with `Anonymizer`:**

```python
anonymizer = Anonymizer(
    detector=detector,
    placeholder_factory=RedactPlaceholderFactory(),
)
result = anonymizer.anonymize("Patrick lives in Paris.")
print(result.anonymized_text)
# [REDACTED] lives in [REDACTED].
```

!!! warning "Not reversible"
    `RedactPlaceholderFactory` does **not** inherit from `ReversiblePlaceholderFactory`. Calling `anonymizer.deanonymize(result)` will raise `IrreversibleAnonymizationError`. It cannot be used with `AnonymizationPipeline` (which requires deanonymization for tool calls).

---

### Reversible vs irreversible

PIIGhost distinguishes two categories of placeholder factories:

| | Reversible | Irreversible |
|---|---|---|
| **Base class** | `ReversiblePlaceholderFactory` | `PlaceholderFactory` directly |
| **`reversible`** | `True` | `False` |
| **`check_reversible()`** | No-op | Raises `IrreversibleAnonymizationError` |
| **Unique tags** | Each entity gets a distinct tag | All entities share the same tag |
| **Deanonymization** | Supported | Raises `IrreversibleAnonymizationError` |
| **Information leakage** | Reveals entity count and co-references | Zero leakage |
| **Use with Pipeline** | Yes | No |
| **Use with Middleware** | Yes | No |
| **Implementations** | `CounterPlaceholderFactory`, `HashPlaceholderFactory` | `RedactPlaceholderFactory` |

**When to use each:**

- **Reversible** (default) — when you need bidirectional anonymization, e.g. in LLM agent conversations where tool calls must be deanonymized before execution.
- **Irreversible** — when you only need to strip PII from text and never recover it, e.g. logging, analytics, data export, compliance redaction.

---

## Exceptions

### `IrreversibleAnonymizationError`

Raised when attempting to deanonymize a result produced by a non-reversible factory.

```python
from piighost.anonymizer import IrreversibleAnonymizationError

anonymizer = Anonymizer(
    detector=detector,
    placeholder_factory=RedactPlaceholderFactory(),
)
result = anonymizer.anonymize("Patrick lives in Paris.")

try:
    anonymizer.deanonymize(result)
except IrreversibleAnonymizationError as e:
    print(e)
    # RedactPlaceholderFactory is not reversible. Deanonymization requires
    # a ReversiblePlaceholderFactory (e.g. CounterPlaceholderFactory or HashPlaceholderFactory).
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
