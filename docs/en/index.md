---
icon: lucide/shield
---

# PIIGhost

**Transparent PII anonymization for LLM agents.**

`piighost` is a Python library that automatically detects, anonymizes, and deanonymizes sensitive entities (names, locations, etc.) in AI agent conversations. It integrates via a LangChain middleware without modifying your existing agent code.

---

## Features

- **5-stage pipeline**: Detect → Resolve Spans → Link Entities → Resolve Entities → Anonymize covers every occurrence of each entity
- **Bidirectional**: reliable deanonymization via span-based replacement, plus fast string-based reanonymization
- **Conversation memory**: `ConversationMemory` accumulates entities across messages for consistent placeholders
- **LangChain middleware**: transparent hooks on `abefore_model`, `aafter_model`, and `awrap_tool_call` zero changes to your agent code
- **Protocol-based DI**: every pipeline stage is a swappable protocol detector, span resolver, entity linker, entity resolver, anonymizer, placeholder factory
- **Immutable data models**: frozen dataclasses throughout (`Entity`, `Detection`, `Span`)

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
    anonymized, entities = await pipeline.anonymize(
        "Patrick lives in Paris. Patrick loves Paris.",
    )
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
