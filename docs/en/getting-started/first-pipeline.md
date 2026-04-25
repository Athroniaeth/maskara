---
icon: lucide/play
---

# First pipeline

The simplest usage: create an `AnonymizationPipeline` and call it directly on text.

```python
import asyncio

from gliner2 import GLiNER2

from piighost.anonymizer import Anonymizer
from piighost.detector import Gliner2Detector
from piighost.linker.entity import ExactEntityLinker
from piighost.entity_resolver import MergeEntityConflictResolver
from piighost.pipeline import AnonymizationPipeline
from piighost.placeholder import LabelCounterPlaceholderFactory
from piighost.span_resolver import ConfidenceSpanConflictResolver

# 1. Load the NER model
model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")

# 2. Instantiate each component
detector = Gliner2Detector(model=model, labels=["PERSON", "LOCATION"], threshold=0.5)
span_resolver = ConfidenceSpanConflictResolver()
entity_linker = ExactEntityLinker()
entity_resolver = MergeEntityConflictResolver()
anonymizer = Anonymizer(LabelCounterPlaceholderFactory())

# 3. Assemble the pipeline
pipeline = AnonymizationPipeline(
    detector=detector,
    span_resolver=span_resolver,
    entity_linker=entity_linker,
    entity_resolver=entity_resolver,
    anonymizer=anonymizer,
)


async def main():
    # 4. Anonymize
    anonymized, entities = await pipeline.anonymize(
        "Patrick lives in Paris. Patrick loves Paris.",
    )
    print(anonymized)
    # <<PERSON:1>> lives in <<LOCATION:1>>. <<PERSON:1>> loves <<LOCATION:1>>.

    # 5. Deanonymize
    original, _ = await pipeline.deanonymize(anonymized)
    print(original)
    # Patrick lives in Paris. Patrick loves Paris.


asyncio.run(main())
```

!!! info "Available labels"
    The supported labels depend on the NER model used. Common labels include `"PERSON"`, `"LOCATION"`, `"ORGANIZATION"`, `"EMAIL"`, `"PHONE"`.

To chain several messages in a conversation with shared memory, see [Conversational pipeline](conversation.md).
