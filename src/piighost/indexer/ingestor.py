from __future__ import annotations

from pathlib import Path

# kreuzberg is an optional dep (``[project.optional-dependencies].index``).
# Import it lazily inside ``extract_text`` so that ``list_document_paths``
# — which only uses the standard library — works without the extras
# installed (and so that tests that don't exercise extraction can be
# collected on slim CI environments).

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
        import kreuzberg  # optional dep — installed via `[index]` extras
    except ImportError as exc:
        raise RuntimeError(
            "extract_text requires the 'index' extras; "
            "install with `pip install piighost[index]`"
        ) from exc
    try:
        result = await kreuzberg.extract_file(path)
        text: str = result.content
        return text.strip() if text and text.strip() else None
    except Exception:
        return None
