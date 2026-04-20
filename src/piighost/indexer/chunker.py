from __future__ import annotations


def chunk_text(
    text: str,
    *,
    chunk_size: int = 512,
    overlap: int = 64,
) -> list[str]:
    if overlap >= chunk_size:
        raise ValueError(f"overlap ({overlap}) must be less than chunk_size ({chunk_size})")
    if not text or not text.strip():
        return []
    if len(text) <= chunk_size:
        return [text]
    step = chunk_size - overlap
    chunks: list[str] = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + chunk_size])
        start += step
    return chunks
