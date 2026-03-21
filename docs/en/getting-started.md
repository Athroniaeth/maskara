---
icon: lucide/rocket
---

# Getting started

## Installation

### Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Basic installation

=== "uv"

    ```bash
    uv add maskara
    ```

=== "pip"

    ```bash
    pip install maskara
    ```

### Development installation

```bash
git clone https://github.com/Athroniaeth/maskara.git
cd maskara
uv sync
```

---

## Usage 1 — Standalone anonymization

The simplest usage: create an `Anonymizer` and call it directly.

```python
from gliner2 import GLiNER2
from maskara.anonymizer import Anonymizer, GlinerDetector

# 1. Load the NER model
model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")

# 2. Create the detector
detector = GlinerDetector(model=model, threshold=0.5, flat_ner=True)

# 3. Create the anonymizer
anonymizer = Anonymizer(detector=detector)

# 4. Anonymize
result = anonymizer.anonymize(
    "Patrick lives in Paris. Patrick loves Paris.",
    labels=["PERSON", "LOCATION"],
)

print(result.anonymized_text)
# <<PERSON_1>> lives in <<LOCATION_1>>. <<PERSON_1>> loves <<LOCATION_1>>.

# 5. Deanonymize
original = anonymizer.deanonymize(result)
print(original)
# Patrick lives in Paris. Patrick loves Paris.
```

!!! info "Available labels"
    The supported labels depend on the GLiNER2 model. `"fastino/gliner2-multi-v1"` supports `"PERSON"`, `"LOCATION"`, `"ORGANIZATION"`, `"EMAIL"`, `"PHONE"`, among others.

---

## Usage 2 — Session pipeline with caching

`AnonymizationPipeline` wraps the `Anonymizer` with a session cache to reuse placeholders across multiple messages.

```python
import asyncio
from maskara.pipeline import AnonymizationPipeline

pipeline = AnonymizationPipeline(
    anonymizer=anonymizer,
    labels=["PERSON", "LOCATION"],
)

async def main():
    # Anonymize (async, with caching)
    result = await pipeline.anonymize("Patrick lives in Paris.")
    print(result.anonymized_text)
    # <<PERSON_1>> lives in <<LOCATION_1>>.

    # Synchronous deanonymization via string replacement
    restored = pipeline.deanonymize_text("<<PERSON_1>> lives in <<LOCATION_1>>.")
    print(restored)
    # Patrick lives in Paris.

    # Reanonymize (inverse: original → placeholder)
    reanon = pipeline.reanonymize_text("Result for Patrick in Paris")
    print(reanon)
    # Result for <<PERSON_1>> in <<LOCATION_1>>

asyncio.run(main())
```

??? info "SHA-256 caching"
    The pipeline computes a SHA-256 hash of the source text. If the same text is submitted multiple times, the cached result is returned immediately without calling the NER model.

---

## Usage 3 — LangChain middleware

To integrate anonymization into a LangGraph agent, use `PIIAnonymizationMiddleware`:

```python
from langchain.agents import create_agent
from langchain_core.tools import tool

from maskara.anonymizer import Anonymizer, GlinerDetector
from maskara.middleware import PIIAnonymizationMiddleware
from maskara.pipeline import AnonymizationPipeline

@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email to the given address."""
    return f"Email sent to {to}."

# Build the anonymization stack
detector = GlinerDetector(model=model, threshold=0.5, flat_ner=True)
anonymizer = Anonymizer(detector=detector)
pipeline = AnonymizationPipeline(anonymizer=anonymizer, labels=["PERSON", "LOCATION"])
middleware = PIIAnonymizationMiddleware(pipeline=pipeline)

# Create the agent with the middleware
agent = create_agent(
    model="openai:gpt-4o-mini",
    system_prompt="You are a helpful assistant.",
    tools=[send_email],
    middleware=[middleware],
)
```

The middleware automatically intercepts every agent turn — the LLM only sees anonymized text, tools receive real values, and user-facing messages are deanonymized.

---

## Development commands

```bash
uv sync                      # Install dependencies
make lint                    # Format (ruff) + lint (ruff) + type-check (pyrefly)
uv run pytest                # Run all tests
uv run pytest tests/ -k "test_name"  # Run a single test
```
