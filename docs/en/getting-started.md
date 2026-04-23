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
model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")

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

model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")
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

## Usage 3: LangChain middleware

Reusing the `pipeline` built above (Usage 2), just wrap it in `PIIAnonymizationMiddleware` and pass it to `create_agent`:

```python
from langchain.agents import create_agent
from piighost.middleware import PIIAnonymizationMiddleware

middleware = PIIAnonymizationMiddleware(pipeline=pipeline)

agent = create_agent(
    model="openai:gpt-5.4",
    tools=[...],
    middleware=[middleware],
)
```

The middleware automatically intercepts every agent turn: the LLM only sees anonymized text, tools receive real values, and user-facing messages are deanonymized.

For a complete example (tools, system prompt, Langfuse observability, Aegra deployment), see [LangChain integration](examples/langchain.md).

---

## Usage 4: Remote client

`PIIGhostClient` is a thin async HTTP client that delegates every pipeline
operation to a remote `piighost-api` server. Use it when the NER model must
stay off the application host (separate inference pod, GPU node, shared
anonymization service across microservices).

```bash
pip install piighost[client]
```

```python
import asyncio

from piighost.client import PIIGhostClient
from piighost.exceptions import CacheMissError


async def main():
    async with PIIGhostClient(
        base_url="http://piighost-api.internal:8000",
        api_key="ak_v1-...",
    ) as client:
        text, entities = await client.anonymize(
            "Patrick lives in Paris.",
            thread_id="user-42",
        )
        print(text)
        # <<PERSON_1>> lives in <<LOCATION_1>>.

        try:
            original, _ = await client.deanonymize(text, thread_id="user-42")
        except CacheMissError:
            # Server has no cached mapping for this thread (restart,
            # eviction, wrong thread_id). Fall back to entity-based
            # replacement which works on any placeholder-bearing text.
            original = await client.deanonymize_with_ent(text, thread_id="user-42")
        print(original)


asyncio.run(main())
```

The client mirrors the `ThreadAnonymizationPipeline` API (`detect`,
`anonymize`, `deanonymize`, `deanonymize_with_ent`, `override_detections`),
so swapping a local pipeline for a remote one is a one-line change.

!!! warning "Thread isolation is server-side"
    The `thread_id` argument is sent to the server and used to scope the
    cache and conversation memory. Reuse the same `thread_id` across calls
    that belong to the same conversation, otherwise placeholders will not
    be consistent between messages.

---

## Development commands

```bash
uv sync                      # Install dependencies
make lint                    # Format (ruff) + lint (ruff) + type-check (pyrefly)
uv run pytest                # Run all tests
uv run pytest tests/ -k "test_name"  # Run a single test
```
