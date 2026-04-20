import asyncio

import pytest

from piighost.indexer.filters import QueryFilter
from piighost.service.core import PIIGhostService


@pytest.fixture()
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv("PIIGHOST_EMBEDDER", "stub")
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    service = asyncio.run(PIIGhostService.create(vault_dir=tmp_path / "vault"))
    yield service
    asyncio.run(service.close())


def test_query_without_filter_returns_all(svc, tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.txt").write_text("Alice works here")
    (docs / "b.txt").write_text("Alice works there")
    asyncio.run(svc.index_path(docs, project="p"))

    result = asyncio.run(svc.query("Alice", project="p", k=5))
    assert len(result.hits) >= 1


def test_query_with_file_prefix_filter_scopes_results(svc, tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.txt").write_text("Alice works here")
    (docs / "b.txt").write_text("Alice works there")
    asyncio.run(svc.index_path(docs, project="p"))

    a_path = docs / "a.txt"
    f = QueryFilter(file_path_prefix=str(a_path))
    result = asyncio.run(svc.query("Alice", project="p", k=5, filter=f))

    assert all(hit.file_path == str(a_path) for hit in result.hits)
