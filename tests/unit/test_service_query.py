import asyncio
import pytest
from pathlib import Path
from piighost.service.core import PIIGhostService


@pytest.fixture()
def indexed_svc(tmp_path, monkeypatch):
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    monkeypatch.setenv("PIIGHOST_EMBEDDER", "stub")
    vault_dir = tmp_path / "vault"
    svc = asyncio.run(PIIGhostService.create(vault_dir=vault_dir))
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.txt").write_text("Alice Smith is a senior engineer at ACME Corp.")
    (docs / "b.txt").write_text("Bob Jones works as a lawyer in Paris.")
    asyncio.run(svc.index_path(docs))
    return svc


def test_query_returns_hits(indexed_svc):
    result = asyncio.run(indexed_svc.query("engineer", k=3))
    assert result.k == 3
    assert len(result.hits) >= 1
    asyncio.run(indexed_svc.close())


def test_query_no_raw_pii_in_chunks(indexed_svc):
    result = asyncio.run(indexed_svc.query("Alice", k=5))
    for hit in result.hits:
        assert "Alice" not in hit.chunk
    asyncio.run(indexed_svc.close())


def test_query_empty_index(tmp_path, monkeypatch):
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    monkeypatch.setenv("PIIGHOST_EMBEDDER", "stub")
    svc = asyncio.run(PIIGhostService.create(vault_dir=tmp_path / "vault"))
    result = asyncio.run(svc.query("anything", k=3))
    assert result.hits == []
    asyncio.run(svc.close())
