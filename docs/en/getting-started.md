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
from piighost.detector import Gliner2Detector
from piighost.linker.entity import ExactEntityLinker
from piighost.entity_resolver import MergeEntityConflictResolver
from piighost.pipeline import AnonymizationPipeline
from piighost.placeholder import CounterPlaceholderFactory
from piighost.span_resolver import ConfidenceSpanConflictResolver

# 1. Load the NER model
model = GLiNER2.from_pretrained("urchade/gliner_multi_pii-v1")

# 2. Build the pipeline
pipeline = AnonymizationPipeline(
    detector=Gliner2Detector(model=model, labels=["PERSON", "LOCATION"], threshold=0.5),
    span_resolver=ConfidenceSpanConflictResolver(),
    entity_linker=ExactEntityLinker(),
    entity_resolver=MergeEntityConflictResolver(),
    anonymizer=Anonymizer(CounterPlaceholderFactory()),
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

`ConversationAnonymizationPipeline` wraps the base pipeline with a `ConversationMemory` to accumulate entities across messages and provide string-based deanonymization/reanonymization.

```python
import asyncio

from piighost.anonymizer import Anonymizer
from piighost.conversation_memory import ConversationMemory
from piighost.conversation_pipeline import ConversationAnonymizationPipeline
from piighost.detector import Gliner2Detector
from piighost.linker.entity import ExactEntityLinker
from piighost.entity_resolver import MergeEntityConflictResolver
from piighost.placeholder import CounterPlaceholderFactory
from piighost.span_resolver import ConfidenceSpanConflictResolver

conv_pipeline = ConversationAnonymizationPipeline(
    detector=Gliner2Detector(model=model, labels=["PERSON", "LOCATION"], threshold=0.5),
    span_resolver=ConfidenceSpanConflictResolver(),
    entity_linker=ExactEntityLinker(),
    entity_resolver=MergeEntityConflictResolver(),
    anonymizer=Anonymizer(CounterPlaceholderFactory()),
    memory=ConversationMemory(),
)


async def conversation():
    # First message: NER detection + entity recording
    anonymized, _ = await conv_pipeline.anonymize("Patrick lives in Paris.")
    print(anonymized)
    # <<PERSON_1>> lives in <<LOCATION_1>>.

    # String-based deanonymization (works on any text with tokens)
    restored = await conv_pipeline.deanonymize_with_ent("Hello <<PERSON_1>>!")
    print(restored)
    # Hello Patrick!

    # String-based reanonymization (original values → tokens)
    reanon = conv_pipeline.anonymize_with_ent("Result for Patrick in Paris")
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
from piighost.conversation_memory import ConversationMemory
from piighost.conversation_pipeline import ConversationAnonymizationPipeline
from piighost.detector import Gliner2Detector
from piighost.linker.entity import ExactEntityLinker
from piighost.entity_resolver import MergeEntityConflictResolver
from piighost.middleware import PIIAnonymizationMiddleware
from piighost.placeholder import CounterPlaceholderFactory
from piighost.span_resolver import ConfidenceSpanConflictResolver


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email to the given address."""
    return f"Email sent to {to}."


# Build the conversation pipeline
pipeline = ConversationAnonymizationPipeline(
    detector=Gliner2Detector(model=model, labels=["PERSON", "LOCATION"], threshold=0.5),
    span_resolver=ConfidenceSpanConflictResolver(),
    entity_linker=ExactEntityLinker(),
    entity_resolver=MergeEntityConflictResolver(),
    anonymizer=Anonymizer(CounterPlaceholderFactory()),
    memory=ConversationMemory(),
)
middleware = PIIAnonymizationMiddleware(pipeline=pipeline)

# Create the agent with the middleware
agent = create_agent(
    model="openai:gpt-4o-mini",
    system_prompt="You are a helpful assistant.",
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
