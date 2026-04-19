from pathlib import Path

import pytest

from piighost.vault.store import Vault


@pytest.fixture()
def vault(tmp_path: Path) -> Vault:
    v = Vault.open(tmp_path / "vault.db")
    yield v
    v.close()


def test_upsert_and_lookup(vault: Vault) -> None:
    vault.upsert_entity(
        token="<PERSON:a1b2c3d4>",
        original="Alice",
        label="PERSON",
        confidence=0.97,
    )
    entry = vault.get_by_token("<PERSON:a1b2c3d4>")
    assert entry is not None
    assert entry.original == "Alice"
    assert entry.label == "PERSON"
    assert entry.occurrence_count == 1


def test_upsert_increments_occurrence(vault: Vault) -> None:
    vault.upsert_entity("<P:x>", "Bob", "PERSON", 0.9)
    vault.upsert_entity("<P:x>", "Bob", "PERSON", 0.92)
    entry = vault.get_by_token("<P:x>")
    assert entry is not None
    assert entry.occurrence_count == 2


def test_list_filters_by_label(vault: Vault) -> None:
    vault.upsert_entity("<PERSON:1>", "Alice", "PERSON", 0.9)
    vault.upsert_entity("<LOC:2>", "Paris", "LOC", 0.9)
    people = vault.list_entities(label="PERSON")
    assert len(people) == 1
    assert people[0].label == "PERSON"


def test_stats(vault: Vault) -> None:
    vault.upsert_entity("<PERSON:1>", "Alice", "PERSON", 0.9)
    vault.upsert_entity("<LOC:2>", "Paris", "LOC", 0.9)
    stats = vault.stats()
    assert stats.total == 2
    assert stats.by_label["PERSON"] == 1
    assert stats.by_label["LOC"] == 1


def test_link_doc_entity(vault: Vault) -> None:
    vault.upsert_entity("<P:1>", "Alice", "PERSON", 0.9)
    vault.link_doc_entity(doc_id="doc1", token="<P:1>", start_pos=0, end_pos=5)
    hits = vault.entities_for_doc("doc1")
    assert len(hits) == 1
    assert hits[0].original == "Alice"
