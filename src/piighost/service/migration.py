"""Schema v2 -> v3 migration: move single-vault state into projects/default/."""

from __future__ import annotations

import shutil
from pathlib import Path

from piighost.vault.project_registry import ProjectRegistry


_LEGACY_TOP_LEVEL = ("vault.db", "audit.log")


def migrate_to_v3(vault_dir: Path) -> None:
    """Idempotently move legacy single-vault state under ``projects/default/``.

    Safe to call on fresh installs (creates an empty default project) and on
    already-migrated vaults (no-op). Also recovers from a partial migration
    where some files were moved but others remain at the top level.
    """
    vault_dir.mkdir(parents=True, exist_ok=True)
    projects_dir = vault_dir / "projects"
    default_dir = projects_dir / "default"
    default_dir.mkdir(parents=True, exist_ok=True)

    for name in _LEGACY_TOP_LEVEL:
        src = vault_dir / name
        if src.exists():
            dst = default_dir / name
            if dst.exists():
                src.unlink()
            else:
                src.rename(dst)

    legacy_piighost = vault_dir / ".piighost"
    if legacy_piighost.exists() and legacy_piighost.is_dir():
        dst = default_dir / ".piighost"
        if dst.exists():
            shutil.rmtree(legacy_piighost)
        else:
            legacy_piighost.rename(dst)

    registry = ProjectRegistry.open(vault_dir / "projects.db")
    try:
        if not registry.exists("default"):
            registry.create(
                "default",
                description="Default project (pre-v3 data migrated here)",
                placeholder_salt="",
            )
    finally:
        registry.close()
