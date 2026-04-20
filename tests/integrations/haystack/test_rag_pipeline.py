import asyncio

import pytest

pytest.importorskip("haystack")

from piighost.integrations.haystack.rag import PIIGhostRetriever
from piighost.service.core import PIIGhostService


@pytest.fixture()
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv("PIIGHOST_EMBEDDER", "stub")
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    service = asyncio.run(PIIGhostService.create(vault_dir=tmp_path / "vault"))
    yield service
    asyncio.run(service.close())


def test_retriever_construction(svc):
    retriever = PIIGhostRetriever(svc, project="client-a", top_k=5)
    assert retriever is not None


def test_retriever_returns_documents(svc, tmp_path):
    from haystack.dataclasses import Document

    doc = tmp_path / "doc.txt"
    doc.write_text("Alice works on GDPR compliance contracts")
    asyncio.run(svc.index_path(doc, project="client-a"))

    retriever = PIIGhostRetriever(svc, project="client-a", top_k=5)
    result = retriever.run(query="GDPR compliance")
    assert "documents" in result
    assert isinstance(result["documents"], list)
    assert all(isinstance(d, Document) for d in result["documents"])
    assert len(result["documents"]) >= 1


def test_retriever_async_equivalent_to_sync(svc, tmp_path):
    doc = tmp_path / "doc.txt"
    doc.write_text("Alice works in Paris")
    asyncio.run(svc.index_path(doc, project="client-a"))

    retriever = PIIGhostRetriever(svc, project="client-a", top_k=3)
    sync_result = retriever.run(query="Paris")
    async_result = asyncio.run(retriever.run_async(query="Paris"))
    assert len(sync_result["documents"]) == len(async_result["documents"])


def test_retriever_metadata_includes_project(svc, tmp_path):
    doc = tmp_path / "doc.txt"
    doc.write_text("Alice works in Paris")
    asyncio.run(svc.index_path(doc, project="client-a"))

    retriever = PIIGhostRetriever(svc, project="client-a")
    docs = retriever.run(query="Paris")["documents"]
    assert docs[0].meta["project"] == "client-a"
    assert "doc_id" in docs[0].meta
