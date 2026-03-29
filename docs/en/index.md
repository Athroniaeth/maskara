---
icon: lucide/shield
---

# PIIGhost

**Transparent PII anonymization for LLM agents.**

`piighost` is a Python library that detects PII (personally identifiable information), extracts them, applies corrections, and automatically anonymizes and deanonymizes sensitive entities (names, locations, etc.). With modules for bidirectional anonymization in AI agent conversations, it integrates via a LangChain middleware without modifying your existing agent code.

---

## Features

- **Detection**: Detect PII with NER models, algorithms, and build your custom configuration with our detector composition component
- **Span resolution**: Resolve overlapping or nested detected spans to guarantee clean, non-redundant entities, especially when using multiple detectors
- **Entity linking**: Link different detections together, enabling typo tolerance and catching mentions that an NER model might miss
- **Entity resolution**: Resolve linked entity conflicts (e.g., one detector links A and B, another links B and C) to guarantee coherent final entities
- **Anonymization**: Anonymize detected entities with customizable placeholders (e.g., `<<PERSON_1>>`, `<<LOCATION_1>>`) to protect privacy while preserving text structure. A cache system remembers the applied anonymization and can reverse it for deanonymization
- **Placeholder Factory**: Create custom placeholders for anonymization, with flexible naming strategies (counters, UUID, etc.) to fit your specific needs
- **Middleware**: Easily integrate `piighost` into your LangChain agents for transparent anonymization before and after model calls, without modifying your existing agent code

---

## Installation

=== "uv"

    ```bash
    uv add piighost
    ```

=== "pip"

    ```bash
    pip install piighost
    ```

---

## Quick example

```python
import asyncio

from piighost.anonymizer import Anonymizer
from piighost.detector.gliner2 import Gliner2Detector
from piighost.linker.entity import ExactEntityLinker
from piighost.resolver import MergeEntityConflictResolver, ConfidenceSpanConflictResolver
from piighost.pipeline import AnonymizationPipeline
from piighost.placeholder import CounterPlaceholderFactory

from gliner2 import GLiNER2

entity_linker = ExactEntityLinker()
entity_resolver = MergeEntityConflictResolver()
span_resolver = ConfidenceSpanConflictResolver()

ph_factory = CounterPlaceholderFactory()
anonymizer = Anonymizer(ph_factory=ph_factory)

model = GLiNER2.from_pretrained("urchade/gliner_multi-v2.1")
detector = Gliner2Detector(
    model=model,
    threshold=0.5,
    labels=["PERSON", "LOCATION"],
)

pipeline = AnonymizationPipeline(
    detector=detector,
    span_resolver=span_resolver,
    entity_linker=entity_linker,
    entity_resolver=entity_resolver,
    anonymizer=anonymizer,
)


async def main():
    text = "Patrick lives in Paris. Patrick loves Paris."
    anonymized, entities = await pipeline.anonymize(text)
    print(anonymized)
    # <<PERSON_1>> lives in <<LOCATION_1>>. <<PERSON_1>> loves <<LOCATION_1>>.


asyncio.run(main())
```

!!! note "Model download"
    The GLiNER2 model is downloaded from HuggingFace on first use (~500 MB).

---

## Navigation

| Section | Description |
|---------|-------------|
| [Getting started](getting-started.md) | Installation and first steps |
| [Architecture](architecture.md) | Pipeline and flow diagrams |
| [Examples](examples/basic.md) | Basic usage and LangChain integration |
| [Pre-built detectors](examples/detectors.md) | Ready-to-use regex patterns for common PII (US & Europe) |
| [Extending PIIGhost](extending.md) | Build your own modules |
| [API Reference](reference/anonymizer.md) | Full API documentation |
