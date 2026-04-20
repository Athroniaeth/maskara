import pytest
from piighost.indexer.store import ChunkStore


def test_meta_mode_upsert_and_all_records(tmp_path):
    """NullEmbedder (empty vectors) → meta-mode: in-memory, no LanceDB."""
    store = ChunkStore(tmp_path / "lance")
    store.upsert_chunks("doc1", "/tmp/a.txt", ["chunk A", "chunk B"], [[], []])
    records = store.all_records()
    assert len(records) == 2
    assert records[0]["doc_id"] == "doc1"
    assert records[0]["chunk"] in ("chunk A", "chunk B")


def test_meta_mode_overwrites_doc_on_upsert(tmp_path):
    store = ChunkStore(tmp_path / "lance")
    store.upsert_chunks("doc1", "/tmp/a.txt", ["old"], [[]])
    store.upsert_chunks("doc1", "/tmp/a.txt", ["new"], [[]])
    records = store.all_records()
    assert len(records) == 1
    assert records[0]["chunk"] == "new"


def test_meta_mode_vector_search_returns_empty(tmp_path):
    store = ChunkStore(tmp_path / "lance")
    store.upsert_chunks("doc1", "/tmp/a.txt", ["hello"], [[]])
    results = store.vector_search([0.1, 0.2], k=5)
    assert results == []


def test_vector_mode_upsert_and_search(tmp_path):
    """Real vectors → LanceDB mode."""
    store = ChunkStore(tmp_path / "lance")
    vecs = [[float(i) / 10 for i in range(8)], [float(i + 1) / 10 for i in range(8)]]
    store.upsert_chunks("doc2", "/tmp/b.txt", ["alpha", "beta"], vecs)
    records = store.all_records()
    assert len(records) == 2
    results = store.vector_search([0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7], k=2)
    assert len(results) > 0
    assert "chunk" in results[0]
