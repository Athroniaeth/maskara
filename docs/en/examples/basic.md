---
icon: lucide/code
---

# Basic usage

This page covers the fundamental usages of the library without any LangChain integration.

---

## Simple anonymization with the pipeline

```python
import asyncio

from gliner2 import GLiNER2

from piighost.anonymizer import Anonymizer
from piighost.detector import GlinerDetector
from piighost.entity_linker import ExactEntityLinker
from piighost.entity_resolver import MergeEntityConflictResolver
from piighost.pipeline import AnonymizationPipeline
from piighost.placeholder import CounterPlaceholderFactory
from piighost.span_resolver import ConfidenceSpanConflictResolver

# Load the GLiNER2 model
model = GLiNER2.from_pretrained("urchade/gliner_multi_pii-v1")

# Build the pipeline
pipeline = AnonymizationPipeline(
    detector=GlinerDetector(model=model, labels=["PERSON", "LOCATION"], threshold=0.5),
    span_resolver=ConfidenceSpanConflictResolver(),
    entity_linker=ExactEntityLinker(),
    entity_resolver=MergeEntityConflictResolver(),
    anonymizer=Anonymizer(CounterPlaceholderFactory()),
)

async def main():
    # Anonymize a text
    anonymized, entities = await pipeline.anonymize(
        "Patrick lives in Paris. Patrick loves Paris.",
    )
    print(anonymized)
    # <<PERSON_1>> lives in <<LOCATION_1>>. <<PERSON_1>> loves <<LOCATION_1>>.

    # Deanonymize
    original, _ = await pipeline.deanonymize(anonymized)
    print(original)
    # Patrick lives in Paris. Patrick loves Paris.

asyncio.run(main())
```

---

## Inspecting entities

The pipeline returns the entities used for anonymization:

```python
async def main():
    anonymized, entities = await pipeline.anonymize(
        "Mary Smith works at Acme Corp in Lyon.",
    )
    print(anonymized)
    # <<PERSON_1>> works at <<ORGANIZATION_1>> in <<LOCATION_1>>.

    for entity in entities:
        canonical = entity.detections[0].text
        print(f"'{canonical}' [{entity.label}] {len(entity.detections)} detection(s)")

asyncio.run(main())
```

---

## Conversation pipeline with memory

For multi-message scenarios (conversations), `ConversationAnonymizationPipeline` accumulates entities across messages and provides string-based deanonymization/reanonymization.

```python
import asyncio

from piighost.anonymizer import Anonymizer
from piighost.conversation_memory import ConversationMemory
from piighost.conversation_pipeline import ConversationAnonymizationPipeline
from piighost.detector import GlinerDetector
from piighost.entity_linker import ExactEntityLinker
from piighost.entity_resolver import MergeEntityConflictResolver
from piighost.placeholder import CounterPlaceholderFactory
from piighost.span_resolver import ConfidenceSpanConflictResolver

conv_pipeline = ConversationAnonymizationPipeline(
    detector=GlinerDetector(model=model, labels=["PERSON", "LOCATION"], threshold=0.5),
    span_resolver=ConfidenceSpanConflictResolver(),
    entity_linker=ExactEntityLinker(),
    entity_resolver=MergeEntityConflictResolver(),
    anonymizer=Anonymizer(CounterPlaceholderFactory()),
    memory=ConversationMemory(),
)

async def conversation():
    # First message: NER detection + entity recording
    r1, _ = await conv_pipeline.anonymize("Patrick is in Paris.")
    print(r1)
    # <<PERSON_1>> is in <<LOCATION_1>>.

    # Same text again: cache hit (no second NER call)
    r2, _ = await conv_pipeline.anonymize("Patrick is in Paris.")
    print(r2)
    # <<PERSON_1>> is in <<LOCATION_1>>.

    # String-based deanonymization on any text with tokens
    restored = await conv_pipeline.deanonymize_with_ent("Hello, <<PERSON_1>>!")
    print(restored)
    # Hello, Patrick!

    # String-based reanonymization (original → token)
    reanon = conv_pipeline.anonymize_with_ent("Answer for Patrick in Paris")
    print(reanon)
    # Answer for <<PERSON_1>> in <<LOCATION_1>>

asyncio.run(conversation())
```

---

## Different placeholder factories

By default, `CounterPlaceholderFactory` generates `<<LABEL_N>>` tags. You can swap it for other strategies:

```python
from piighost.placeholder import HashPlaceholderFactory, RedactPlaceholderFactory

# Hash-based: deterministic opaque tags
pipeline_hash = AnonymizationPipeline(
    ...,
    anonymizer=Anonymizer(HashPlaceholderFactory()),
)
# Produces: <PERSON:a1b2c3d4>

# Redact: all entities get <LABEL> (no counter)
pipeline_redact = AnonymizationPipeline(
    ...,
    anonymizer=Anonymizer(RedactPlaceholderFactory()),
)
# Produces: <PERSON>
```

---

## Testing without loading GLiNER2

In tests, use `ExactMatchDetector` to avoid downloading the model:

```python
from piighost.anonymizer import Anonymizer
from piighost.detector import ExactMatchDetector
from piighost.entity_linker import ExactEntityLinker
from piighost.entity_resolver import MergeEntityConflictResolver
from piighost.pipeline import AnonymizationPipeline
from piighost.placeholder import CounterPlaceholderFactory
from piighost.span_resolver import ConfidenceSpanConflictResolver

pipeline = AnonymizationPipeline(
    detector=ExactMatchDetector([("Patrick", "PERSON"), ("Paris", "LOCATION")]),
    span_resolver=ConfidenceSpanConflictResolver(),
    entity_linker=ExactEntityLinker(),
    entity_resolver=MergeEntityConflictResolver(),
    anonymizer=Anonymizer(CounterPlaceholderFactory()),
)

# Deterministic detection without an NER model
anonymized, entities = await pipeline.anonymize("Patrick lives in Paris.")
assert anonymized == "<<PERSON_1>> lives in <<LOCATION_1>>."
```

See also [Extending PIIGhost](../extending.md) for creating other custom components.
