import asyncio

import pytest

pytest.importorskip("langchain_core")
pytest.importorskip("aiocache")

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


def test_cache_hit_avoids_second_llm_call(svc, tmp_path):
    rag = PIIGhostRAG(svc, project="p", cache=RagCache(ttl=60))
    doc = tmp_path / "doc.txt"
    doc.write_text("Alice works in Paris")
    asyncio.run(rag.ingest(doc))

    llm = _CountingLLM("answer")
    answer_1 = asyncio.run(rag.query("Who is Alice?", llm=llm))
    assert llm.call_count == 1
    answer_2 = asyncio.run(rag.query("Who is Alice?", llm=llm))
    assert llm.call_count == 1
    assert answer_1 == answer_2


def test_different_projects_do_not_share_cache(svc, tmp_path):
    doc = tmp_path / "doc.txt"
    doc.write_text("Alice works in Paris")

    cache = RagCache(ttl=60)
    rag_a = PIIGhostRAG(svc, project="a", cache=cache)
    rag_b = PIIGhostRAG(svc, project="b", cache=cache)
    asyncio.run(rag_a.ingest(doc))
    asyncio.run(rag_b.ingest(doc))

    llm = _CountingLLM("answer")
    asyncio.run(rag_a.query("Who is Alice?", llm=llm))
    asyncio.run(rag_b.query("Who is Alice?", llm=llm))
    assert llm.call_count == 2


def test_cache_none_means_no_caching(svc, tmp_path):
    rag = PIIGhostRAG(svc, project="p")  # cache=None
    doc = tmp_path / "doc.txt"
    doc.write_text("Alice works here")
    asyncio.run(rag.ingest(doc))

    llm = _CountingLLM("answer")
    asyncio.run(rag.query("Who is Alice?", llm=llm))
    asyncio.run(rag.query("Who is Alice?", llm=llm))
    assert llm.call_count == 2
