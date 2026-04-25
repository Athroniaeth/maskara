---
icon: lucide/messages-square
---

# Conversational pipeline

`ThreadAnonymizationPipeline` wraps the base pipeline with a `ConversationMemory` that accumulates entities across messages and provides string-based deanonymize / reanonymize.

```python
import asyncio

from piighost.anonymizer import Anonymizer
from piighost.detector.gliner2 import Gliner2Detector
from piighost.linker.entity import ExactEntityLinker
from piighost.resolver import MergeEntityConflictResolver, ConfidenceSpanConflictResolver
from piighost.pipeline import AnonymizationPipeline, ThreadAnonymizationPipeline
from piighost.placeholder import LabelCounterPlaceholderFactory

from gliner2 import GLiNER2

entity_linker = ExactEntityLinker()
entity_resolver = MergeEntityConflictResolver()
span_resolver = ConfidenceSpanConflictResolver()

ph_factory = LabelCounterPlaceholderFactory()
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
    # First message: NER detection + entity registration
    # The pipeline remembers that input and output are linked, and that
    # <<PERSON:1>> maps to "Patrick" and <<LOCATION:1>> to "Paris".
    anonymized, _ = await pipeline.anonymize("Patrick lives in Paris.")
    print(anonymized)
    # <<PERSON:1>> lives in <<LOCATION:1>>.

    # Deanonymize via the mapping stored in the pipeline cache
    restored = await pipeline.deanonymize("Hello <<PERSON:1>>!")
    print(restored)

    # Deanonymize by string replacement, using the detections kept in memory
    restored = await pipeline.deanonymize_with_ent("Hello <<PERSON:1>>!")
    print(restored)
    # Hello Patrick!

    # Reanonymize by string replacement, using the detections kept in memory
    reanon = pipeline.anonymize_with_ent("Result for Patrick in Paris")
    print(reanon)
    # Result for <<PERSON:1>> in <<LOCATION:1>>


asyncio.run(conversation())
```

??? info "SHA-256 cache"
    The pipeline uses aiocache with SHA-256 keys. If the same text is submitted more than once, the cached result is returned without calling the NER model.
