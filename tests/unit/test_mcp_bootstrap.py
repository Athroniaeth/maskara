"""Idempotent bootstrap for a Cowork client folder."""
from __future__ import annotations

from pathlib import Path

import pytest

from piighost.mcp.bootstrap import ensure_data_dir, ensure_vault_key


class TestEnsureDataDir:
    def test_creates_when_missing(self, tmp_path: Path) -> None:
        target = tmp_path / ".hacienda"
        assert not target.exists()
        ensure_data_dir(target)
        assert target.is_dir()
        assert (target / "sessions").is_dir()

    def test_idempotent(self, tmp_path: Path) -> None:
        target = tmp_path / ".hacienda"
        ensure_data_dir(target)
        ensure_data_dir(target)  # must not raise
        assert target.is_dir()


class TestEnsureVaultKey:
    def test_returns_existing_key(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("CLOAKPIPE_VAULT_KEY", "abc123" * 10)
        key = ensure_vault_key(data_dir=tmp_path)
        assert key == "abc123" * 10

    def test_generates_and_persists_when_missing(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.delenv("CLOAKPIPE_VAULT_KEY", raising=False)
        key = ensure_vault_key(data_dir=tmp_path)
        assert len(key) >= 32
        # Second call returns the same key.
        assert ensure_vault_key(data_dir=tmp_path) == key
