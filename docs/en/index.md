---
icon: lucide/shield
---

# PIIGhost

**Transparent PII anonymization for LLM agents.**

`piighost` is a Python library that automatically detects, anonymizes, and deanonymizes sensitive entities (names, locations, etc.) in AI agent conversations. It integrates via a LangChain middleware without modifying your existing agent code.

---

## Features

- **4-stage pipeline**: Detect → Expand → Map → Replace — covers every occurrence of each entity, not just the first
- **Bidirectional**: reliable deanonymization via reverse spans, plus fast string-based reanonymization
- **Session caching**: `PlaceholderStore` protocol for cross-session persistence (SHA-256 keyed)
- **LangChain middleware**: transparent hooks on `abefore_model`, `aafter_model`, and `awrap_tool_call` — zero changes to your agent code
- **Protocol-based DI**: every pipeline stage is a swappable protocol — detector, occurrence finder, placeholder factory, span validator
- **Immutable data models**: frozen dataclasses throughout (`Entity`, `Placeholder`, `Span`, `AnonymizationResult`)

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
from gliner2 import GLiNER2
from piighost.anonymizer import Anonymizer, GlinerDetector

model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")
detector = GlinerDetector(model=model, threshold=0.5, flat_ner=True)
anonymizer = Anonymizer(detector=detector)

result = anonymizer.anonymize(
    "Patrick lives in Paris. Patrick loves Paris.",
    labels=["PERSON", "LOCATION"],
)

print(result.anonymized_text)
# <<PERSON_1>> lives in <<LOCATION_1>>. <<PERSON_1>> loves <<LOCATION_1>>.

original = anonymizer.deanonymize(result)
print(original)
# Patrick lives in Paris. Patrick loves Paris.
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
| [Extending PIIGhost](extending.md) | Build your own modules |
| [API Reference](reference/anonymizer.md) | Full API documentation |
