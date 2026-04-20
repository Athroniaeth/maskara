from piighost.indexer.identity import content_hash


def test_hash_is_16_chars(tmp_path):
    f = tmp_path / "doc.txt"
    f.write_text("hello world")
    assert len(content_hash(f)) == 16


def test_hash_is_consistent(tmp_path):
    f = tmp_path / "doc.txt"
    f.write_text("hello world")
    assert content_hash(f) == content_hash(f)


def test_hash_differs_for_different_content(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("hello")
    b.write_text("world")
    assert content_hash(a) != content_hash(b)


def test_hash_same_content_different_path(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "sub" / "b.txt"
    b.parent.mkdir()
    a.write_text("identical content")
    b.write_text("identical content")
    assert content_hash(a) == content_hash(b)


def test_hash_is_hex_string(tmp_path):
    f = tmp_path / "doc.txt"
    f.write_bytes(b"\x00\x01\x02\xff")
    h = content_hash(f)
    int(h, 16)  # raises ValueError if not valid hex
