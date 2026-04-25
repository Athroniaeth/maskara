---
icon: lucide/cloud
---

# Remote client

`PIIGhostClient` is a lightweight async HTTP client that delegates every pipeline operation to a remote `piighost-api` server. Use it when the NER model has to live outside the application host (dedicated inference pod, GPU node, shared anonymization service across microservices).

## Installation

```bash
pip install piighost[client]
```

## Usage

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
        # <<PERSON:1>> lives in <<LOCATION:1>>.

        try:
            original, _ = await client.deanonymize(text, thread_id="user-42")
        except CacheMissError:
            # The server has no cached mapping for this thread (restart,
            # eviction, wrong thread_id). Fall back to entity-based
            # replacement, which works on any text containing
            # placeholders.
            original = await client.deanonymize_with_ent(text, thread_id="user-42")
        print(original)


asyncio.run(main())
```

The client mirrors the `ThreadAnonymizationPipeline` API (`detect`, `anonymize`, `deanonymize`, `deanonymize_with_ent`, `override_detections`), so swapping a local pipeline for a remote one is a one-liner.

!!! warning "Thread isolation lives on the server"
    The `thread_id` parameter is forwarded to the server and scopes both cache and conversation memory. Reuse the same `thread_id` for every call in a conversation, otherwise placeholders will not stay consistent across messages.

For server deployment, see [Deployment](../deployment.md).
