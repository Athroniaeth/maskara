import asyncio
import pytest
from piighost.service.core import PIIGhostService


@pytest.fixture()
def svc_with_entities(tmp_path, monkeypatch):
    monkeypatch.setenv("PIIGHOST_DETECTOR", "stub")
    monkeypatch.setenv("PIIGHOST_EMBEDDER", "stub")
    vault_dir = tmp_path / "vault"
    svc = asyncio.run(PIIGhostService.create(vault_dir=vault_dir))
    asyncio.run(svc.anonymize("Alice Smith works at ACME Corporation in Paris."))
    return svc, vault_dir


def test_vault_search_finds_entity(svc_with_entities):
    svc, _ = svc_with_entities
    results = asyncio.run(svc.vault_search("Alice"))
    assert len(results) >= 1
    masked = [r.original_masked for r in results]
    assert any("A***e" in (m or "") for m in masked)
    asyncio.run(svc.close())


def test_vault_search_no_match(svc_with_entities):
    svc, _ = svc_with_entities
    results = asyncio.run(svc.vault_search("zzznomatch99"))
    assert results == []
    asyncio.run(svc.close())


def test_vault_search_masked_hides_original(svc_with_entities):
    svc, _ = svc_with_entities
    results = asyncio.run(svc.vault_search("Alice", reveal=False))
    for r in results:
        assert r.original is None
    asyncio.run(svc.close())
