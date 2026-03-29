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
    uv add piighost
    ```

=== "pip"

    ```bash
    pip install piighost
    ```

### Development installation

```bash
git clone https://github.com/Athroniaeth/piighost.git
cd piighost
uv sync
```

---

## Usage 1 Standalone pipeline

The simplest usage: create an `AnonymizationPipeline` and call it directly.

```python
import asyncio

from gliner2 import GLiNER2

from piighost.anonymizer import Anonymizer
from piighost.detector.gliner2 import Gliner2Detector
from piighost.linker.entity import ExactEntityLinker
from piighost.resolver import MergeEntityConflictResolver, ConfidenceSpanConflictResolver
from piighost.pipeline import AnonymizationPipeline
from piighost.placeholder import CounterPlaceholderFactory

# 1. Load the NER model
model = GLiNER2.from_pretrained("urchade/gliner_multi-v2.1")

# 2. Build the pipeline
entity_linker = ExactEntityLinker()
entity_resolver = MergeEntityConflictResolver()
span_resolver = ConfidenceSpanConflictResolver()

ph_factory = CounterPlaceholderFactory()
anonymizer = Anonymizer(ph_factory=ph_factory)

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
    # 3. Anonymize
    anonymized, entities = await pipeline.anonymize(
        "Patrick lives in Paris. Patrick loves Paris.",
    )
    print(anonymized)
    # <<PERSON_1>> lives in <<LOCATION_1>>. <<PERSON_1>> loves <<LOCATION_1>>.

    # 4. Deanonymize
    original, _ = await pipeline.deanonymize(anonymized)
    print(original)
    # Patrick lives in Paris. Patrick loves Paris.


asyncio.run(main())
```

!!! info "Available labels"
    The supported labels depend on the GLiNER2 model. Common labels include `"PERSON"`, `"LOCATION"`, `"ORGANIZATION"`, `"EMAIL"`, `"PHONE"`.

---

## Usage 2 Conversation pipeline with memory

`ThreadAnonymizationPipeline` wraps the base pipeline with a `ConversationMemory` to accumulate entities across messages and provide string-based deanonymization/reanonymization.

```python
import asyncio

from piighost.anonymizer import Anonymizer
from piighost.detector.gliner2 import Gliner2Detector
from piighost.linker.entity import ExactEntityLinker
from piighost.resolver import MergeEntityConflictResolver, ConfidenceSpanConflictResolver
from piighost.pipeline import AnonymizationPipeline, ThreadAnonymizationPipeline
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
pipeline = ThreadAnonymizationPipeline(
    detector=detector,
    span_resolver=span_resolver,
    entity_linker=entity_linker,
    entity_resolver=entity_resolver,
    anonymizer=anonymizer,
)


async def conversation():
    # First message: NER detection + entity recording
    # The pipeline remembers that input and output are linked,
    # and that <<PERSON_1>> corresponds to "Patrick" and <<LOCATION_1>> to "Paris"
    anonymized, _ = await pipeline.anonymize("Patrick lives in Paris.")
    print(anonymized)
    # <<PERSON_1>> lives in <<LOCATION_1>>.

    # Deanonymization via the mapping stored in the pipeline cache
    restored = await pipeline.deanonymize("Hello <<PERSON_1>>!")
    print(restored)

    # Deanonymization by text replacement, using previous detections stored in memory
    restored = await pipeline.deanonymize_with_ent("Hello <<PERSON_1>>!")
    print(restored)
    # Hello Patrick!

    # Reanonymization by text replacement, using previous detections stored in memory
    reanon = pipeline.anonymize_with_ent("Result for Patrick in Paris")
    print(reanon)
    # Result for <<PERSON_1>> in <<LOCATION_1>>


asyncio.run(conversation())
```

??? info "SHA-256 caching"
    The pipeline uses aiocache with SHA-256 keys. If the same text is submitted multiple times, the cached result is returned without calling the NER model.

---

## Usage 3 LangChain middleware

To integrate anonymization into a LangGraph agent, use `PIIAnonymizationMiddleware`:

```python
from langchain.agents import create_agent
from langchain_core.tools import tool

from piighost.anonymizer import Anonymizer
from piighost.detector.gliner2 import Gliner2Detector
from piighost.linker.entity import ExactEntityLinker
from piighost.resolver import MergeEntityConflictResolver, ConfidenceSpanConflictResolver
from piighost.pipeline import AnonymizationPipeline, ThreadAnonymizationPipeline
from piighost.placeholder import CounterPlaceholderFactory
from piighost.middleware import PIIAnonymizationMiddleware

from gliner2 import GLiNER2



@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email to the given address."""
    return f"Email sent to {to}."


# Build the conversation pipeline
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
pipeline = ThreadAnonymizationPipeline(
    detector=detector,
    span_resolver=span_resolver,
    entity_linker=entity_linker,
    entity_resolver=entity_resolver,
    anonymizer=anonymizer,
)
middleware = PIIAnonymizationMiddleware(pipeline=pipeline)

system_prompt = """\
You are a helpful assistant. Some inputs may contain anonymized placeholders that replace real values for privacy reasons.

Rules:
1. Treat every placeholder as if it were the real value, never comment on its format, never say it is a token, never ask the user to reveal it.
2. Placeholders can be passed directly to tools use them as-is as input arguments. This preserves the user's privacy while \
still allowing tools to operate.
3. If the user asks for a specific detail about a token (e.g. "what is the first letter?"), reply briefly: "I cannot answer that question \
as the data has been anonymized to protect your personal information."
"""

# Create the agent with the middleware
agent = create_agent(
    model="openai:gpt-5.4",
    system_prompt=system_prompt,
    tools=[send_email],
    middleware=[middleware],
)
```

The middleware automatically intercepts every agent turn the LLM only sees anonymized text, tools receive real values, and user-facing messages are deanonymized.

---

## Development commands

```bash
uv sync                      # Install dependencies
make lint                    # Format (ruff) + lint (ruff) + type-check (pyrefly)
uv run pytest                # Run all tests
uv run pytest tests/ -k "test_name"  # Run a single test
```
