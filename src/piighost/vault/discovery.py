"""Git-style upward walk to locate the nearest `.piighost/` directory."""

from __future__ import annotations

from pathlib import Path

from piighost.exceptions import VaultNotFound


def find_vault_dir(
    *, start: Path | None = None, explicit: Path | None = None
) -> Path:
    """Locate a vault directory.

    Resolution order:
    1. If ``explicit`` is provided and exists, return it.
    2. Walk from ``start`` (default: cwd) upward looking for ``.piighost/``.
    3. Raise ``VaultNotFound``.
    """
    if explicit is not None:
        if not explicit.is_dir():
            raise VaultNotFound(f"--vault {explicit} is not a directory")
        return explicit.resolve()

    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        found = candidate / ".piighost"
        if found.is_dir():
            return found
    raise VaultNotFound(
        "No .piighost/ in cwd or any ancestor directory. "
        "Run `piighost init` here or pass --vault."
    )
