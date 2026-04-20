from pathlib import Path

from piighost.service.migration import migrate_to_v3
from piighost.vault.project_registry import ProjectRegistry


def _seed_v2_vault(vault_dir: Path) -> None:
    vault_dir.mkdir(parents=True, exist_ok=True)
    (vault_dir / "vault.db").write_bytes(b"v2-vault-data")
    (vault_dir / "audit.log").write_text("op=anonymize\n")
    piighost_dir = vault_dir / ".piighost"
    piighost_dir.mkdir()
    lance_dir = piighost_dir / "lance"
    lance_dir.mkdir()
    (lance_dir / "chunks.lance").write_bytes(b"dummy-lance-table")
    (piighost_dir / "bm25.pkl").write_bytes(b"dummy-bm25")


def test_migrates_v2_vault_to_projects_default(tmp_path):
    vault = tmp_path / "vault"
    _seed_v2_vault(vault)

    migrate_to_v3(vault)

    default = vault / "projects" / "default"
    assert (default / "vault.db").read_bytes() == b"v2-vault-data"
    assert (default / "audit.log").read_text() == "op=anonymize\n"
    assert (default / ".piighost" / "lance" / "chunks.lance").exists()
    assert (default / ".piighost" / "bm25.pkl").exists()

    assert not (vault / "vault.db").exists()
    assert not (vault / "audit.log").exists()
    assert not (vault / ".piighost").exists()


def test_default_project_exists_after_migration(tmp_path):
    vault = tmp_path / "vault"
    _seed_v2_vault(vault)

    migrate_to_v3(vault)

    registry = ProjectRegistry.open(vault / "projects.db")
    info = registry.get("default")
    assert info is not None
    assert info.placeholder_salt == ""  # legacy compatibility
    registry.close()


def test_fresh_install_creates_default_project(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()

    migrate_to_v3(vault)

    assert (vault / "projects" / "default").exists()
    registry = ProjectRegistry.open(vault / "projects.db")
    assert registry.exists("default")
    registry.close()


def test_migration_is_idempotent(tmp_path):
    vault = tmp_path / "vault"
    _seed_v2_vault(vault)

    migrate_to_v3(vault)
    vault_bytes_first = (vault / "projects" / "default" / "vault.db").read_bytes()

    migrate_to_v3(vault)
    vault_bytes_second = (vault / "projects" / "default" / "vault.db").read_bytes()
    assert vault_bytes_first == vault_bytes_second


def test_partial_migration_recovers(tmp_path):
    """If a previous run moved some files but not others, the second run completes the move."""
    vault = tmp_path / "vault"
    _seed_v2_vault(vault)
    default = vault / "projects" / "default"
    default.mkdir(parents=True)
    (vault / "vault.db").rename(default / "vault.db")

    migrate_to_v3(vault)

    assert (default / "audit.log").exists()
    assert (default / ".piighost" / "bm25.pkl").exists()
    assert not (vault / "audit.log").exists()
