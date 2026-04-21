from __future__ import annotations

from pathlib import Path

import kreuzberg

_SUPPORTED_EXTENSIONS = {
    # Office / OpenDocument binaries
    ".pdf", ".docx", ".xlsx", ".pptx", ".odt", ".ods",
    # Plain-text / markup
    ".txt", ".md", ".rst", ".html", ".htm",
    # Email containers — .eml is RFC 5322 text, .msg is Outlook CFB binary.
    # Kreuzberg parses both via its native backend.
    ".eml", ".msg",
}


async def list_document_paths(
    path: Path, *, recursive: bool = True
) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix.lower() in _SUPPORTED_EXTENSIONS else []
    pattern = "**/*" if recursive else "*"
    return [
        p for p in path.glob(pattern)
        if p.is_file() and p.suffix.lower() in _SUPPORTED_EXTENSIONS
    ]


async def extract_text(path: Path, *, max_bytes: int = 10_485_760) -> str | None:
    if path.stat().st_size > max_bytes:
        return None
    try:
        result = await kreuzberg.extract_file(path)
        text: str = result.content
        return text.strip() if text and text.strip() else None
    except Exception:
        return None
