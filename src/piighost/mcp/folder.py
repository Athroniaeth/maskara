# src/piighost/mcp/folder.py
"""Deterministic mapping from an absolute folder path to a piighost project name.

Cowork hands us the user's current folder as an absolute path. We need a project
identifier that (a) is stable across runs, (b) differs for distinct folders, (c)
normalises Windows case/separators so the same folder from two different
shells maps to the same project.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(leaf: str) -> str:
    """Lowercase, collapse non-alnum to single '-', strip edges."""
    slug = _SLUG_RE.sub("-", leaf.lower()).strip("-")
    return slug or "root"


def _normalise(path: Path) -> str:
    """Canonical string form used for hashing. Case-insensitive, no trailing sep."""
    # Resolve-free: we only want textual normalisation — the folder may not
    # exist yet at tool-call time (Cowork may open a brand-new folder).
    raw = str(path)
    # Windows: fold case and normalise separators.
    raw = raw.replace("\\", "/").rstrip("/").lower()
    return raw


def project_name_for_folder(path: Path) -> str:
    """Map an absolute folder path to a piighost project name.

    Format: ``<slug>-<hash8>`` where ``slug`` is a kebab-case version of the
    folder's leaf name (``ACME Inc.`` → ``acme-inc``) and ``hash8`` is the first
    8 hex chars of SHA-256 over the normalised full path. The slug keeps names
    human-readable in ``list_projects`` output; the hash guarantees uniqueness
    even when two clients share a leaf name.
    """
    leaf = path.name or path.anchor or "root"
    slug = _slugify(leaf)
    digest = hashlib.sha256(_normalise(path).encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{digest}"
