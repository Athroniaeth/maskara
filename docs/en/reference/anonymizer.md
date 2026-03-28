---
icon: lucide/scan-text
---

# Reference Anonymizer

Module: `piighost.anonymizer`

---

## `Anonymizer`

Performs span-based text replacement using a placeholder factory. **Stateless** class no internal state between calls.

### Constructor

```python
Anonymizer(ph_factory: AnyPlaceholderFactory)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `ph_factory` | `AnyPlaceholderFactory` | Placeholder factory for token generation (required) |

### Methods

#### `anonymize(text, entities) -> str`

Replaces each detection in `text` with its entity's token. Replacements are applied right to left so that earlier span positions remain valid.

```python
from piighost.anonymizer import Anonymizer
from piighost.placeholder import CounterPlaceholderFactory
from piighost.models import Detection, Entity, Span

anonymizer = Anonymizer(CounterPlaceholderFactory())

entity = Entity(detections=(
    Detection(text="Patrick", label="PERSON", position=Span(0, 7), confidence=0.9),
))

result = anonymizer.anonymize("Patrick est gentil", [entity])
# '<<PERSON_1>> est gentil'
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `text` | `str` | Source text |
| `entities` | `list[Entity]` | Entities whose detections should be replaced |

**Returns**: `str` the anonymized text

#### `deanonymize(anonymized_text, entities) -> str`

Restores the original text by replacing tokens with original detection texts, using the original positions to handle entities with multiple spelling variants.

```python
original = anonymizer.deanonymize("<<PERSON_1>> est gentil", [entity])
# 'Patrick est gentil'
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `anonymized_text` | `str` | Text containing placeholder tokens |
| `entities` | `list[Entity]` | Same entities used during anonymization |

**Returns**: `str` the restored original text

---

## `AnyAnonymizer` (Protocol)

Interface for all anonymizer implementations.

```python
class AnyAnonymizer(Protocol):
    ph_factory: AnyPlaceholderFactory

    def anonymize(self, text: str, entities: list[Entity]) -> str: ...
    def deanonymize(self, anonymized_text: str, entities: list[Entity]) -> str: ...
```

---

## Detectors

Module: `piighost.detector`

### `AnyDetector` (Protocol)

Interface for all entity detectors. All detectors are **async**.

```python
class AnyDetector(Protocol):
    async def detect(self, text: str) -> list[Detection]: ...
```

### `GlinerDetector`

Implementation using the **GLiNER2** model.

```python
GlinerDetector(
    model: GLiNER2,
    labels: list[str],
    threshold: float = 0.5,
    flat_ner: bool = True,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | `GLiNER2` | | GLiNER2 model instance (required) |
| `labels` | `list[str]` | | Entity types to detect (required) |
| `threshold` | `float` | `0.5` | Minimum confidence score (0.0–1.0) |
| `flat_ner` | `bool` | `True` | Flat NER mode (no nested entities) |

```python
from gliner2 import GLiNER2
from piighost.detector import Gliner2Detector

model = GLiNER2.from_pretrained("urchade/gliner_multi_pii-v1")
detector = Gliner2Detector(model=model, labels=["PERSON", "LOCATION"], threshold=0.5)

detections = await detector.detect("Patrick lives in Paris")
# [Detection(text='Patrick', label='PERSON', position=Span(0, 7), confidence=0.97),
#  Detection(text='Paris', label='LOCATION', position=Span(17, 22), confidence=0.99)]
```

### `ExactMatchDetector`

Detects entities by exact word matching using word-boundary regex. Useful for tests.

```python
ExactMatchDetector(
    bag_of_words: list[tuple[str, str]],
    flags: re.RegexFlag = re.IGNORECASE,
)
```

```python
from piighost.detector import ExactMatchDetector

detector = ExactMatchDetector([("Patrick", "PERSON"), ("Paris", "LOCATION")])
detections = await detector.detect("Patrick habite a Paris")
```

### `RegexDetector`

Pattern-based detection with one regex per label.

```python
RegexDetector(patterns: dict[str, str])
```

```python
from piighost.detector import RegexDetector

detector = RegexDetector(patterns={"FR_PHONE": r"\b(?:\+33|0)[1-9](?:[\s.\-]?\d{2}){4}\b"})
detections = await detector.detect("Appelez le 06 12 34 56 78")
```

### `CompositeDetector`

Chains multiple detectors and merges their results.

```python
from piighost.detector import CompositeDetector

detector = CompositeDetector(detectors=[gliner_detector, regex_detector])
```

---

## Placeholder Factories

Module: `piighost.placeholder`

### `AnyPlaceholderFactory` (Protocol)

Interface for all placeholder factories.

```python
class AnyPlaceholderFactory(Protocol):
    def create(self, entities: list[Entity]) -> dict[Entity, str]: ...
```

### `CounterPlaceholderFactory`

Default implementation: generates sequential `<<LABEL_N>>` tags.

```python
from piighost.placeholder import CounterPlaceholderFactory
from piighost.models import Detection, Entity, Span

factory = CounterPlaceholderFactory()
person = Entity(detections=(Detection("Patrick", "PERSON", Span(0, 7), 0.9),))
location = Entity(detections=(Detection("Paris", "LOCATION", Span(17, 22), 0.9),))

tokens = factory.create([person, location])
# {person: '<<PERSON_1>>', location: '<<LOCATION_1>>'}
```

### `HashPlaceholderFactory`

Generates deterministic, opaque hash-based tags.

```python
from piighost.placeholder import HashPlaceholderFactory

factory = HashPlaceholderFactory(hash_length=8)
tokens = factory.create([person])
# {person: '<PERSON:a1b2c3d4>'}
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `hash_length` | `8` | Number of hex characters from the SHA-256 digest |

### `RedactPlaceholderFactory`

All entities with the same label share the same `<LABEL>` token. No counter, no distinction between entities.

```python
from piighost.placeholder import RedactPlaceholderFactory

factory = RedactPlaceholderFactory()
tokens = factory.create([person, location])
# {person: '<PERSON>', location: '<LOCATION>'}
```

!!! warning "Deanonymization with RedactPlaceholderFactory"
    Since multiple entities share the same token, deanonymization relies on original position order. This works correctly with the `Anonymizer.deanonymize()` method.

---

## Data models

Module: `piighost.models`

### `Detection`

A single NER result from the text.

```python
@dataclass(frozen=True)
class Detection:
    text: str           # Surface form: "Patrick"
    label: str          # Entity type: "PERSON"
    position: Span      # Where it was found
    confidence: float   # Score (0.0–1.0)
```

### `Entity`

Group of detections referring to the same PII.

```python
@dataclass(frozen=True)
class Entity:
    detections: tuple[Detection, ...]  # All detections for this entity
    # label: str (property, from first detection)
```

### `Span`

Character position in source text.

```python
@dataclass(frozen=True)
class Span:
    start_pos: int   # Inclusive start index
    end_pos: int     # Exclusive end index
    # overlaps(other: Span) -> bool
```

!!! note "Immutability"
    All models are **frozen dataclasses** (`frozen=True`) they are thread-safe and hashable.

---

## Exceptions

Module: `piighost.exceptions`

### `CacheMissError`

Raised when a cache lookup finds no entry for the given key. Used by the middleware to fall back from `pipeline.deanonymize()` to `pipeline.deanonymize_with_ent()`.

```python
from piighost.exceptions import CacheMissError
```
