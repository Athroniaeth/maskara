"""Proof: when wired correctly, the Mistral embedder never sees raw PII."""

import os

import pytest

pytest.importorskip("langchain_core")
pytest.importorskip("langchain_mistralai")
pytest.importorskip("httpx")

pytestmark = [pytest.mark.asyncio, pytest.mark.slow]

import httpx  # noqa: E402
from langchain_core.documents import Document  # noqa: E402

from piighost.integrations.langchain.transformers import (  # noqa: E402
    PIIGhostDocumentAnonymizer,
    PIIGhostQueryAnonymizer,
)


async def test_no_raw_pii_in_outbound_request_body(pipeline) -> None:
    from langchain_mistralai import MistralAIEmbeddings

    captured: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(bytes(request.content))
        import json as _json

        body = _json.loads(request.content.decode("utf-8")) if request.content else {}
        inputs = body.get("input", [])
        n = len(inputs) if isinstance(inputs, list) else 1
        return httpx.Response(
            200,
            json={
                "id": "embd-test",
                "object": "list",
                "model": "mistral-embed",
                "data": [
                    {"object": "embedding", "index": i, "embedding": [0.0] * 1024}
                    for i in range(n)
                ],
                "usage": {"prompt_tokens": 0, "total_tokens": 0},
            },
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    async_client = httpx.AsyncClient(transport=transport)

    os.environ.setdefault("MISTRAL_API_KEY", "test-key")
    embeddings = MistralAIEmbeddings(
        model="mistral-embed", client=client, async_client=async_client
    )

    anonymizer = PIIGhostDocumentAnonymizer(pipeline=pipeline)
    raw = [Document(page_content="Alice visited Paris", metadata={"source": "a"})]
    anonymized = await anonymizer.atransform_documents(raw)

    embeddings.embed_documents([d.page_content for d in anonymized])

    query_anon = PIIGhostQueryAnonymizer(pipeline=pipeline)
    qresult = await query_anon.ainvoke("Where did Alice go?")
    embeddings.embed_query(qresult["query"])

    assert captured, "mock transport should have captured at least one request"
    for body in captured:
        text = body.decode("utf-8", errors="replace")
        assert "Alice" not in text, "raw PII leaked to Mistral embedder"
        assert "Paris" not in text, "raw PII leaked to Mistral embedder"
