"""E2E: index → query → rehydrate, token identity, PII-zero-leak."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import httpx
import pytest

from piighost.service.core import PIIGhostService


@pytest.fixture()
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv("PIIGHOST_EMBEDDER", "stub")
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    vault_dir = tmp_path / "vault"
    service = asyncio.run(PIIGhostService.create(vault_dir=vault_dir))
    yield service
    asyncio.run(service.close())


@pytest.fixture()
def docs(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    # Use "Alice" and "Paris" which the stub detector recognizes
    (docs_dir / "contract.txt").write_text(
        "Alice is a legal consultant working on GDPR compliance contracts. "
        "The project is based in Paris and runs through Q4."
    )
    (docs_dir / "report.txt").write_text(
        "The data processing agreement was submitted to the Paris DPA office. "
        "Alice reviewed and approved the privacy policy amendments."
    )
    (docs_dir / "memo.txt").write_text(
        "A meeting between the legal team in Paris concluded with approval. "
        "Alice will follow up on the compliance timeline."
    )
    return docs_dir


def test_roundtrip_index_query_rehydrate(svc, docs):
    """Index 3 docs -> query -> verify chunks contain no raw PII tokens."""
    report = asyncio.run(svc.index_path(docs))
    assert report.indexed == 3
    assert report.errors == []

    result = asyncio.run(svc.query("legal compliance contract", k=3))
    assert len(result.hits) >= 1

    for hit in result.hits:
        # Chunks must be anonymized -- stub detects "Alice" and "Paris"
        assert "Alice" not in hit.chunk
        assert "Paris" not in hit.chunk

        # Rehydration must work without unknown tokens
        rehydrated = asyncio.run(svc.rehydrate(hit.chunk))
        assert rehydrated.unknown_tokens == []


def test_token_identity_bm25_retrieval(svc, tmp_path):
    """Same entity yields same token -> BM25 matches anonymized query."""
    doc_dir = tmp_path / "tok_docs"
    doc_dir.mkdir()
    # "Alice" appears twice in the first doc -- both should get the same token.
    # Two additional docs with no PII ensure the IDF for that token is positive
    # (BM25Okapi assigns negative IDF when a term appears in ALL documents).
    (doc_dir / "employee.txt").write_text(
        "Alice is a senior software engineer. "
        "Alice joined the company in January 2023."
    )
    (doc_dir / "project.txt").write_text(
        "The quarterly project report was submitted on schedule with no issues."
    )
    (doc_dir / "policy.txt").write_text(
        "The data retention policy outlines procedures for document archival."
    )
    asyncio.run(svc.index_path(doc_dir))

    # Anonymize the query -- "Alice" should get the same token as in the doc
    anon = asyncio.run(svc.anonymize("What does Alice work on?"))
    anon_query = anon.anonymized
    # The same token must appear in the indexed doc and the query → public query surface returns hits
    result = asyncio.run(svc.query(anon_query, k=5))
    assert len(result.hits) >= 1, (
        f"query() found no hits for anonymized query '{anon_query}'. "
        "HashPlaceholderFactory must produce identical tokens for the same entity."
    )


def test_pii_zero_leak_to_mistral(tmp_path, monkeypatch):
    """No raw PII values must appear in Mistral embedding requests."""
    captured_bodies: list[str] = []

    class _CapturingTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            captured_bodies.append(request.content.decode("utf-8", errors="replace"))
            payload = {"data": [{"embedding": [0.1] * 8, "index": 0}], "usage": {"prompt_tokens": 1}}
            return httpx.Response(200, json=payload)

    import piighost.indexer.embedder as emb_mod

    class _PatchedMistralEmbedder(emb_mod.MistralEmbedder):
        async def embed(self, texts: list[str]) -> list[list[float]]:
            async with httpx.AsyncClient(transport=_CapturingTransport()) as client:
                resp = await client.post(
                    "https://api.mistral.ai/v1/embeddings",
                    json={"model": self._model, "input": texts},
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    timeout=30.0,
                )
                resp.raise_for_status()
                data = resp.json()
                return [item["embedding"] for item in data["data"]]

    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    monkeypatch.delenv("PIIGHOST_EMBEDDER", raising=False)
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    monkeypatch.setattr(emb_mod, "MistralEmbedder", _PatchedMistralEmbedder)

    from piighost.service.config import EmbedderSection, ServiceConfig

    vault_dir = tmp_path / "leak_vault"
    config = ServiceConfig(embedder=EmbedderSection(backend="mistral"))

    leak_svc = asyncio.run(PIIGhostService.create(vault_dir=vault_dir, config=config))

    doc_dir = tmp_path / "leak_docs"
    doc_dir.mkdir()
    # Use names the stub detector actually detects
    (doc_dir / "sensitive.txt").write_text(
        "Alice signed a contract in Paris for a GDPR compliance project."
    )
    asyncio.run(leak_svc.index_path(doc_dir))

    assert captured_bodies, (
        "No embed calls were captured — kreuzberg may have failed to extract the document. "
        "Cannot prove PII did not leak."
    )
    pii_values = ["Alice", "Paris"]
    for body in captured_bodies:
        for pii in pii_values:
            assert pii not in body, (
                f"RAW PII '{pii}' found in Mistral embed request body: {body[:200]}"
            )

    asyncio.run(leak_svc.close())
