import asyncio
from pathlib import Path
import pytest
from piighost.service.core import PIIGhostService


@pytest.fixture()
def vault_dir(tmp_path):
    return tmp_path / "vault"


def _make_svc(vault_dir, monkeypatch):
    monkeypatch.setenv("PIIGHOST_EMBEDDER", "stub")
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    return asyncio.run(PIIGhostService.create(vault_dir=vault_dir))


def test_index_report_has_unchanged_field(vault_dir, monkeypatch, tmp_path):
    svc = _make_svc(vault_dir, monkeypatch)
    f = tmp_path / "doc.txt"
    f.write_text("Alice works in Paris")
    report = asyncio.run(svc.index_path(f))
    assert hasattr(report, "unchanged")
    assert report.unchanged == 0
    asyncio.run(svc.close())


def test_second_index_unchanged(vault_dir, monkeypatch, tmp_path):
    svc = _make_svc(vault_dir, monkeypatch)
    f = tmp_path / "doc.txt"
    f.write_text("Alice works in Paris")
    asyncio.run(svc.index_path(f))
    report2 = asyncio.run(svc.index_path(f))
    assert report2.indexed == 0
    assert report2.unchanged == 1
    asyncio.run(svc.close())


def test_force_reindexes_unchanged(vault_dir, monkeypatch, tmp_path):
    svc = _make_svc(vault_dir, monkeypatch)
    f = tmp_path / "doc.txt"
    f.write_text("Alice works in Paris")
    asyncio.run(svc.index_path(f))
    report2 = asyncio.run(svc.index_path(f, force=True))
    assert report2.indexed == 1
    assert report2.unchanged == 0
    asyncio.run(svc.close())


def test_doc_id_is_content_hash(vault_dir, monkeypatch, tmp_path):
    from piighost.indexer.identity import content_hash
    svc = _make_svc(vault_dir, monkeypatch)
    f = tmp_path / "doc.txt"
    f.write_text("Alice works in Paris")
    asyncio.run(svc.index_path(f))
    inner = asyncio.run(svc._get_project("default"))
    rec = inner._vault.get_indexed_file_by_path(str(f))
    assert rec is not None
    assert rec.doc_id == content_hash(f)
    asyncio.run(svc.close())
