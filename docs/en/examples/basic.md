---
icon: lucide/code
---

# Basic usage

This page covers the fundamental usages of the library without any LangChain integration.

---

## Simple anonymization with the pipeline

```python title="pipeline.py" linenums="1" hl_lines="28-35"
import asyncio

from gliner2 import GLiNER2

from piighost.anonymizer import Anonymizer
from piighost.detector.gliner2 import Gliner2Detector
from piighost.linker.entity import ExactEntityLinker
from piighost.resolver import MergeEntityConflictResolver, ConfidenceSpanConflictResolver
from piighost.pipeline import AnonymizationPipeline
from piighost.placeholder import LabelCounterPlaceholderFactory

# Load the GLiNER2 model
model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")

entity_linker = ExactEntityLinker()
entity_resolver = MergeEntityConflictResolver()
span_resolver = ConfidenceSpanConflictResolver()

ph_factory = LabelCounterPlaceholderFactory()
anonymizer = Anonymizer(ph_factory=ph_factory)

detector = Gliner2Detector(
    model=model,
    threshold=0.5,
    labels=["PERSON", "LOCATION"],
)

# Build the pipeline
pipeline = AnonymizationPipeline(
    detector=detector,  # (1)!
    span_resolver=span_resolver,  # (2)!
    entity_linker=entity_linker,  # (3)!
    entity_resolver=entity_resolver,  # (4)!
    anonymizer=anonymizer,  # (5)!
)


async def main():
    # Anonymize a text
    anonymized, entities = await pipeline.anonymize(
        "Patrick lives in Paris. Patrick loves Paris.",
    )
    print(anonymized)
    # <<PERSON:1>> lives in <<LOCATION:1>>. <<PERSON:1>> loves <<LOCATION:1>>.

    # Deanonymize
    original, _ = await pipeline.deanonymize(anonymized)
    print(original)
    # Patrick lives in Paris. Patrick loves Paris.


asyncio.run(main())
```

1. **Detect**: finds PII candidates in the text via the NER model (here GLiNER2, interchangeable with spaCy or Transformers).
2. **Resolve Spans**: arbitrates overlaps when several detectors report overlapping positions.
3. **Link Entities**: groups occurrences of the same PII (case variants, typos, partial mentions).
4. **Resolve Entities**: merges groups that share a mention across detectors.
5. **Anonymize**: replaces each entity with a placeholder produced by the factory (here `<<PERSON:1>>`{ .placeholder }, `<<LOCATION:1>>`{ .placeholder }…).

---

## Inspecting entities

The pipeline returns the entities used for anonymization:

```python
async def main():
    anonymized, entities = await pipeline.anonymize(
        "Mary Smith works at Acme Corp in Lyon.",
    )
    print(anonymized)
    # <<PERSON:1>> works at <<ORGANIZATION:1>> in <<LOCATION:1>>.

    for entity in entities:
        canonical = entity.detections[0].text
        print(f"'{canonical}' [{entity.label}] {len(entity.detections)} detection(s)")

asyncio.run(main())
```

---

## Conversation pipeline with memory

For multi-message scenarios (conversations), `ThreadAnonymizationPipeline` accumulates entities across messages and provides string-based deanonymization/reanonymization.

```python
import asyncio

from piighost.anonymizer import Anonymizer
from piighost.detector.gliner2 import Gliner2Detector
from piighost.linker.entity import ExactEntityLinker
from piighost.resolver import MergeEntityConflictResolver, ConfidenceSpanConflictResolver
from piighost.pipeline import ThreadAnonymizationPipeline
from piighost.placeholder import LabelCounterPlaceholderFactory

entity_linker = ExactEntityLinker()
entity_resolver = MergeEntityConflictResolver()
span_resolver = ConfidenceSpanConflictResolver()

ph_factory = LabelCounterPlaceholderFactory()
anonymizer = Anonymizer(ph_factory=ph_factory)

detector = Gliner2Detector(
    model=model,
    threshold=0.5,
    labels=["PERSON", "LOCATION"],
)
conv_pipeline = ThreadAnonymizationPipeline(
    detector=detector,
    span_resolver=span_resolver,
    entity_linker=entity_linker,
    entity_resolver=entity_resolver,
    anonymizer=anonymizer,
)


async def conversation():
    # First message: NER detection + entity recording
    r1, _ = await conv_pipeline.anonymize("Patrick is in Paris.")
    print(r1)
    # <<PERSON:1>> is in <<LOCATION:1>>.

    # Same text again: cache hit (no second NER call)
    r2, _ = await conv_pipeline.anonymize("Patrick is in Paris.")
    print(r2)
    # <<PERSON:1>> is in <<LOCATION:1>>.

    # String-based deanonymization on any text with tokens
    restored = await conv_pipeline.deanonymize_with_ent("Hello, <<PERSON:1>>!")
    print(restored)
    # Hello, Patrick!

    # String-based reanonymization (original → token)
    reanon = conv_pipeline.anonymize_with_ent("Answer for Patrick in Paris")
    print(reanon)
    # Answer for <<PERSON:1>> in <<LOCATION:1>>


asyncio.run(conversation())
```

---

## Different placeholder factories

By default, `LabelCounterPlaceholderFactory` generates `<<LABEL:N>>` tags. You can swap it for other strategies:

```python
from piighost.placeholder import LabelHashPlaceholderFactory, LabelPlaceholderFactory

# Hash-based: deterministic opaque tags
pipeline_hash = AnonymizationPipeline(
    ...,
    anonymizer=Anonymizer(LabelHashPlaceholderFactory()),
)
# Produces: <<PERSON:a1b2c3d4>>

# Redact: all entities get <<LABEL>> (no counter)
pipeline_redact = AnonymizationPipeline(
    ...,
    anonymizer=Anonymizer(LabelPlaceholderFactory()),
)
# Produces: <<PERSON>>
```

---

For unit testing pipelines without loading an NER model, see the [Testing](testing.md) guide.

See also [Extending PIIGhost](../extending.md) for creating custom components.
