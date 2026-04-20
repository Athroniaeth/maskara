import pytest
from piighost.indexer.chunker import chunk_text

def test_empty_string():
    assert chunk_text("") == []

def test_whitespace_only():
    assert chunk_text("   \n  ") == []

def test_short_text_single_chunk():
    assert chunk_text("hello world") == ["hello world"]

def test_exact_chunk_size():
    text = "a" * 512
    chunks = chunk_text(text, chunk_size=512, overlap=0)
    assert chunks == [text]

def test_two_chunks_no_overlap():
    text = "a" * 600
    chunks = chunk_text(text, chunk_size=512, overlap=0)
    assert len(chunks) == 2
    assert chunks[0] == "a" * 512
    assert chunks[1] == "a" * 88

def test_overlap_produces_shared_content():
    text = "abcdefghij"  # 10 chars
    chunks = chunk_text(text, chunk_size=6, overlap=2)
    # step = 4; chunk 0: [0:6], chunk 1: [4:10]
    assert chunks[0] == "abcdef"
    assert chunks[1] == "efghij"

def test_invalid_overlap_raises():
    with pytest.raises(ValueError):
        chunk_text("hello", chunk_size=4, overlap=4)
