"""Tests for :meth:`PIIGhostRAG.astream` streaming with token-safe rehydration."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("langchain_core")

from piighost.integrations.langchain.rag import PIIGhostRAG
from piighost.service.core import PIIGhostService


@pytest.fixture()
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv("PIIGHOST_EMBEDDER", "stub")
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    service = asyncio.run(PIIGhostService.create(vault_dir=tmp_path / "vault"))
    yield service
    asyncio.run(service.close())


class _FakeChunk:
    def __init__(self, content: str):
        self.content = content


class _FakeStreamingLLM:
    """Fake LLM that yields the configured chunks via ``.astream()``."""

    def __init__(self, chunks: list[str]):
        self._chunks = chunks

    async def astream(self, messages):
        for c in self._chunks:
            yield _FakeChunk(c)


def test_astream_yields_rehydrated_chunks(svc, tmp_path):
    """astream yields chunks with PII tokens rehydrated back to original values."""
    rag = PIIGhostRAG(svc, project="default")

    doc = tmp_path / "note.txt"
    doc.write_text("Alice works in Paris.")
    asyncio.run(rag.ingest(doc))

    # Anonymize "Alice" → token, then feed token back through streaming LLM
    anon = asyncio.run(svc.anonymize("Alice", project="default"))
    token = anon.anonymized.strip()  # e.g. "<PERSON:abc123>"
    assert token.startswith("<") and token.endswith(">"), f"expected a token, got {token!r}"

    llm = _FakeStreamingLLM(chunks=[f"The answer is {token}", ". Done."])

    async def _drive() -> list[str]:
        received: list[str] = []
        async for piece in rag.astream("Who works in Paris?", llm=llm):
            received.append(piece)
        return received

    received = asyncio.run(_drive())
    joined = "".join(received)

    # Token must be rehydrated back to original surface form
    assert "Alice" in joined
    # Token must NOT appear in final stream
    assert token not in joined


def test_astream_handles_no_pii_in_response(svc, tmp_path):
    """astream works correctly when the LLM response contains no PII tokens."""
    rag = PIIGhostRAG(svc, project="default")

    doc = tmp_path / "note.txt"
    doc.write_text("Some content here.")
    asyncio.run(rag.ingest(doc))

    llm = _FakeStreamingLLM(chunks=["Hello ", "world", "!"])

    async def _drive() -> list[str]:
        received: list[str] = []
        async for piece in rag.astream("anything", llm=llm):
            received.append(piece)
        return received

    received = asyncio.run(_drive())
    assert "".join(received) == "Hello world!"
