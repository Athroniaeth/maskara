---
icon: lucide/zap
---

# Quickstart

The shortest path to see `piighost` in action: no model download, no inference, just a fixed dictionary. Ideal to try the library in under a minute.

```python
import asyncio

from piighost import Anonymizer, ExactMatchDetector
from piighost.pipeline import AnonymizationPipeline

detector = ExactMatchDetector([("Patrick", "PERSON"), ("Paris", "LOCATION")])
pipeline = AnonymizationPipeline(detector=detector, anonymizer=Anonymizer())


async def main():
    anonymized, _ = await pipeline.anonymize("Patrick lives in Paris.")
    print(anonymized)
    # <<PERSON_1>> lives in <<LOCATION_1>>.


asyncio.run(main())
```

`ExactMatchDetector` finds exact word-boundary occurrences of the `(text, label)` pairs you provide. `AnonymizationPipeline` applies sensible defaults for the three intermediate stages: span conflict resolution, entity linking, and group merging. That is enough for a first run.

!!! tip "What's next?"
    - For real automatic detection (arbitrary names and locations), move on to the [First pipeline](first-pipeline.md) with an NER like GLiNER2.
    - To detect structured formats (emails, IPs, card numbers) without NER, see the [Pre-built detectors](../examples/detectors.md).
    - To anonymize across a conversation with persistent memory, see the [Conversational pipeline](conversation.md).
