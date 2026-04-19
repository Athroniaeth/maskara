"""Read input text from a path or stdin."""

from __future__ import annotations

import sys
from pathlib import Path


def read_input(spec: str) -> tuple[str, str]:
    """Return ``(doc_id, text)``.

    ``spec == "-"`` reads stdin, ``doc_id = "<stdin>"``.
    Otherwise ``spec`` is treated as a file path (UTF-8); ``doc_id`` is the path.
    """
    if spec == "-":
        return "<stdin>", sys.stdin.read()
    p = Path(spec)
    return str(p), p.read_text(encoding="utf-8")
