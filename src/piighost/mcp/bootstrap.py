"""First-run helpers for hacienda folders.

Idempotent by design — every hacienda skill calls ``bootstrap_client_folder``
on every invocation. Re-running must be cheap and must never rotate the
vault key (doing so would orphan every placeholder in the existing index).
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path


def ensure_data_dir(root: Path) -> None:
    """Create ``<root>/`` and ``<root>/sessions/`` if missing. Idempotent."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "sessions").mkdir(parents=True, exist_ok=True)


_KEY_FILE = "vault.key"


def ensure_vault_key(*, data_dir: Path) -> str:
    """Return the vault key, generating and persisting if absent.

    Priority: ``CLOAKPIPE_VAULT_KEY`` env var → ``<data_dir>/vault.key`` file
    → new random key written to the file. The file is chmod 0600 on Unix.

    **Never** rotates: existing keys are returned untouched. Rotating would
    orphan the encrypted vault entries and break rehydration of prior
    placeholders.
    """
    env_key = os.environ.get("CLOAKPIPE_VAULT_KEY")
    if env_key:
        return env_key

    data_dir.mkdir(parents=True, exist_ok=True)
    key_path = data_dir / _KEY_FILE
    if key_path.exists():
        return key_path.read_text(encoding="utf-8").strip()

    new_key = secrets.token_urlsafe(48)  # 64-char url-safe
    key_path.write_text(new_key, encoding="utf-8")
    try:
        os.chmod(key_path, 0o600)
    except OSError:  # Windows — ignore permission errors
        pass
    return new_key
