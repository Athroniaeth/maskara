import asyncio

import pytest

pytest.importorskip("haystack")
pytest.importorskip("aiocache")

from haystack import component

from piighost.integrations.haystack.rag import build_piighost_rag
from piighost.integrations.langchain.cache import RagCache
from piighost.service.core import PIIGhostService


@pytest.fixture()
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv("PIIGHOST_EMBEDDER", "stub")
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    service = asyncio.run(PIIGhostService.create(vault_dir=tmp_path / "vault"))
    yield service
    asyncio.run(service.close())


@component
class _CountingGenerator:
    def __init__(self) -> None:
        self.calls = 0

    @component.output_types(replies=list[str])
    def run(self, prompt: str) -> dict:
        self.calls += 1
        return {"replies": ["answer"]}


def test_cache_hit_short_circuits_haystack_pipeline(svc, tmp_path):
    doc = tmp_path / "doc.txt"
    doc.write_text("Alice works in Paris")
    asyncio.run(svc.index_path(doc, project="p"))

    cache = RagCache(ttl=60)
    gen = _CountingGenerator()
    wrapper = build_piighost_rag(svc, project="p", llm_generator=gen, cache=cache)
    inputs = {"query_anonymizer": {"text": "Who is Alice?"}}

    wrapper.run(inputs)
    first_calls = gen.calls

    wrapper.run(inputs)  # Should hit the cache; generator not invoked
    assert gen.calls == first_calls


def test_cache_none_returns_bare_pipeline(svc):
    from haystack import Pipeline
    pipeline = build_piighost_rag(svc, project="p")
    assert isinstance(pipeline, Pipeline)
