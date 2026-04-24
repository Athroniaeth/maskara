"""Tests for piighost.utils helpers."""

from piighost.utils import _word_boundary_pattern, find_all_word_boundary, hash_sha256


class TestHashSha256:
    def test_deterministic(self):
        assert hash_sha256("hello") == hash_sha256("hello")

    def test_different_inputs_different_hashes(self):
        assert hash_sha256("hello") != hash_sha256("world")

    def test_empty_string(self):
        assert hash_sha256("") == hashlib_sha256_expected("")

    def test_unicode(self):
        assert hash_sha256("héllo 日本") == hashlib_sha256_expected("héllo 日本")

    def test_returns_hex_string(self):
        digest = hash_sha256("x")
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)


def hashlib_sha256_expected(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode()).hexdigest()


class TestFindAllWordBoundary:
    def test_simple_word_match(self):
        assert find_all_word_boundary("hello world", "world") == [(6, 11)]

    def test_no_match(self):
        assert find_all_word_boundary("hello world", "foo") == []

    def test_multiple_matches(self):
        assert find_all_word_boundary("abc abc abc", "abc") == [(0, 3), (4, 7), (8, 11)]

    def test_case_insensitive_default(self):
        assert find_all_word_boundary("Patrick and patrick", "patrick") == [
            (0, 7),
            (12, 19),
        ]

    def test_case_sensitive_flag(self):
        matches = find_all_word_boundary("Patrick and patrick", "patrick", flags=0)
        assert matches == [(12, 19)]

    def test_word_boundary_excludes_substring(self):
        """'cat' should not match inside 'category'."""
        assert find_all_word_boundary("category cat", "cat") == [(9, 12)]

    def test_special_char_prefix(self):
        """Fragment starting with special char uses lookaround."""
        assert find_all_word_boundary("price: $100 and $200", "$100") == [(7, 11)]

    def test_special_char_suffix(self):
        """Fragment ending with special char uses lookaround."""
        assert find_all_word_boundary("email: me@x.com ok", "me@x.com") == [(7, 15)]

    def test_unicode_fragment(self):
        assert find_all_word_boundary("café and Café", "café") == [(0, 4), (9, 13)]

    def test_empty_text(self):
        assert find_all_word_boundary("", "foo") == []

    def test_regex_metachars_escaped(self):
        """Metacharacters in fragment must be matched literally."""
        assert find_all_word_boundary("a.b and a.b", "a.b") == [(0, 3), (8, 11)]

    def test_underscore_is_word_char(self):
        """Underscore is treated as alphanumeric for boundary purposes."""
        assert find_all_word_boundary("foo_bar baz", "foo") == []
        assert find_all_word_boundary("foo bar", "foo") == [(0, 3)]

    def test_pattern_compilation_is_cached(self):
        """Repeated calls with the same fragment reuse the compiled pattern."""
        _word_boundary_pattern.cache_clear()
        find_all_word_boundary("abc abc", "abc")
        find_all_word_boundary("abc here", "abc")
        info = _word_boundary_pattern.cache_info()
        assert info.hits >= 1
        assert info.misses == 1
