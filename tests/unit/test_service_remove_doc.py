import asyncio
import pytest
from pathlib import Path
from piighost.service.core import PIIGhostService


@pytest.fixture()
def indexed_svc(tmp_path, monkeypatch):
    monkeypatch.setenv("PIIGHOST_EMBEDDER", "stub")
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    vault_dir = tmp_path / "vault"
    svc = asyncio.run(PIIGhostService.create(vault_dir=vault_dir))
    f = tmp_path / "doc.txt"
    f.write_text("Alice works in Paris on legal contracts.")
    asyncio.run(svc.index_path(f))
    return svc, f


def test_remove_doc_returns_true_when_found(indexed_svc):
    svc, f = indexed_svc
    removed = asyncio.run(svc.remove_doc(f))
    assert removed is True
    asyncio.run(svc.close())


def test_remove_doc_returns_false_when_not_found(indexed_svc):
    svc, _ = indexed_svc
    removed = asyncio.run(svc.remove_doc(Path("/nonexistent/file.txt")))
    assert removed is False
    asyncio.run(svc.close())


def test_remove_doc_removes_from_indexed_files(indexed_svc):
    svc, f = indexed_svc
    asyncio.run(svc.remove_doc(f))
    assert svc._vault.get_indexed_file_by_path(str(f)) is None
    asyncio.run(svc.close())


def test_remove_doc_removes_chunks(indexed_svc):
    svc, f = indexed_svc
    assert len(svc._chunk_store.all_records()) >= 1
    asyncio.run(svc.remove_doc(f))
    assert svc._chunk_store.all_records() == []
    asyncio.run(svc.close())


def test_remove_doc_removes_doc_entities(indexed_svc):
    svc, f = indexed_svc
    # Verify entities were linked during indexing
    from piighost.indexer.identity import content_hash
    doc_id = content_hash(f)
    rows_before = svc._vault._conn.execute(
        "SELECT COUNT(*) FROM doc_entities WHERE doc_id = ?", (doc_id,)
    ).fetchone()[0]
    assert rows_before >= 1, "stub detector should have linked at least 1 entity"

    asyncio.run(svc.remove_doc(f))

    rows_after = svc._vault._conn.execute(
        "SELECT COUNT(*) FROM doc_entities WHERE doc_id = ?", (doc_id,)
    ).fetchone()[0]
    assert rows_after == 0
    asyncio.run(svc.close())
