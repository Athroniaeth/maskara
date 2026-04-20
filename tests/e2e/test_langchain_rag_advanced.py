"""E2E: LangChain RAG with filter + rerank + cache."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("langchain_core")
pytest.importorskip("aiocache")

from piighost.indexer.filters import QueryFilter
from piighost.integrations.langchain.cache import RagCache
from piighost.integrations.langchain.rag import PIIGhostRAG
from piighost.service.core import PIIGhostService


@pytest.fixture()
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv("PIIGHOST_EMBEDDER", "stub")
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    service = asyncio.run(PIIGhostService.create(vault_dir=tmp_path / "vault"))
    yield service
    asyncio.run(service.close())


class _CountingLLM:
    def __init__(self, response: str) -> None:
        self._response = response
        self.call_count = 0

    async def ainvoke(self, messages, config=None, **kwargs):
        from langchain_core.messages import AIMessage
        self.call_count += 1
        return AIMessage(content=self._response)


def test_filter_plus_cache_roundtrip(svc, tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.txt").write_text("Alice works in Paris on GDPR contracts")
    (docs / "b.txt").write_text("Bob works on medical records")

    rag = PIIGhostRAG(svc, project="p", cache=RagCache(ttl=60))
    asyncio.run(rag.ingest(docs))

    llm = _CountingLLM("answer about Alice")
    f = QueryFilter(file_path_prefix=str(docs / "a.txt"))
    # First call — cache miss
    answer_1 = asyncio.run(rag.query("Who works on contracts?", llm=llm, filter=f))
    assert llm.call_count == 1
    # Second call, same filter — cache hit
    answer_2 = asyncio.run(rag.query("Who works on contracts?", llm=llm, filter=f))
    assert llm.call_count == 1
    assert answer_1 == answer_2


def test_different_filters_produce_different_cache_entries(svc, tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.txt").write_text("Alice works in Paris")
    (docs / "b.txt").write_text("Bob works in Berlin")

    rag = PIIGhostRAG(svc, project="p", cache=RagCache(ttl=60))
    asyncio.run(rag.ingest(docs))

    llm = _CountingLLM("answer")
    f_a = QueryFilter(file_path_prefix=str(docs / "a.txt"))
    f_b = QueryFilter(file_path_prefix=str(docs / "b.txt"))
    asyncio.run(rag.query("Who?", llm=llm, filter=f_a))
    asyncio.run(rag.query("Who?", llm=llm, filter=f_b))
    # Different filters → different cache keys → 2 calls
    assert llm.call_count == 2
