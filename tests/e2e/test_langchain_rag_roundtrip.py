"""E2E: LangChain PIIGhostRAG — ingest, query with fake LLM, verify no PII leak."""

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


class _RecordingFakeLLM:
    """Minimal LangChain-compatible LLM that records every input."""

    def __init__(self) -> None:
        self.inputs: list[str] = []

    async def ainvoke(self, messages, config=None, **kwargs):
        from langchain_core.messages import AIMessage

        serialized = "\n".join(
            getattr(m, "content", str(m)) for m in messages
        )
        self.inputs.append(serialized)
        return AIMessage(content="(fake response)")

    def invoke(self, messages, config=None, **kwargs):
        return asyncio.run(self.ainvoke(messages, config, **kwargs))


def test_langchain_rag_roundtrip(svc, tmp_path):
    rag = PIIGhostRAG(svc, project="client-a")
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.txt").write_text("Alice works in Paris on GDPR compliance contracts.")
    (docs_dir / "b.txt").write_text("Paris is the location of the data processing agreement.")

    report = asyncio.run(rag.ingest(docs_dir))
    assert report.indexed >= 1

    llm = _RecordingFakeLLM()
    answer = asyncio.run(rag.query("Where does Alice work?", llm=llm))
    assert isinstance(answer, str)


def test_langchain_rag_no_pii_leak_to_llm(svc, tmp_path):
    rag = PIIGhostRAG(svc, project="client-a")
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.txt").write_text("Alice works in Paris on GDPR compliance contracts.")

    asyncio.run(rag.ingest(docs_dir))

    llm = _RecordingFakeLLM()
    asyncio.run(rag.query("Alice in Paris?", llm=llm))

    assert llm.inputs, "fake LLM received no input — test didn't exercise the path"
    for captured in llm.inputs:
        assert "Alice" not in captured, f"raw PII 'Alice' leaked to LLM input: {captured!r}"
        assert "Paris" not in captured, f"raw PII 'Paris' leaked to LLM input: {captured!r}"
