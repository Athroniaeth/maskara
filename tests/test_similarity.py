"""Tests for ``jaro_winkler_similarity`` and ``levenshtein_similarity``."""

import pytest

from piighost.similarity import (
    JARO_WINKLER_DEFAULT_PREFIX_WEIGHT,
    JARO_WINKLER_PREFIX_MAX,
    jaro_winkler_similarity,
    levenshtein_similarity,
)


# ---------------------------------------------------------------------------
# Jaro-Winkler
# ---------------------------------------------------------------------------


class TestJaroWinklerSimilarity:
    """Jaro-Winkler similarity: bonus for shared prefix, good for names."""

    def test_identical_strings(self) -> None:
        assert jaro_winkler_similarity("patrick", "patrick") == 1.0

    def test_both_empty(self) -> None:
        assert jaro_winkler_similarity("", "") == 1.0

    def test_one_empty(self) -> None:
        assert jaro_winkler_similarity("patrick", "") == 0.0
        assert jaro_winkler_similarity("", "patrick") == 0.0

    def test_similar_names_high_score(self) -> None:
        score = jaro_winkler_similarity("patrick", "patric")
        assert score > 0.85

    def test_different_names_low_score(self) -> None:
        score = jaro_winkler_similarity("patrick", "paris")
        assert score < 0.85

    def test_completely_different(self) -> None:
        score = jaro_winkler_similarity("abc", "xyz")
        assert score < 0.5

    def test_case_sensitive(self) -> None:
        # The function itself is case-sensitive; caller normalizes.
        score_same = jaro_winkler_similarity("patrick", "patrick")
        score_diff = jaro_winkler_similarity("patrick", "Patrick")
        assert score_diff < score_same

    def test_single_char_strings(self) -> None:
        assert jaro_winkler_similarity("a", "a") == 1.0
        assert jaro_winkler_similarity("a", "b") == 0.0

    def test_prefix_bonus(self) -> None:
        # Shared prefix should give higher score than shared suffix.
        score_prefix = jaro_winkler_similarity("abcxyz", "abcdef")
        score_suffix = jaro_winkler_similarity("xyzabc", "defabc")
        assert score_prefix >= score_suffix

    def test_symmetry(self) -> None:
        score_ab = jaro_winkler_similarity("patrick", "patric")
        score_ba = jaro_winkler_similarity("patric", "patrick")
        assert score_ab == pytest.approx(score_ba)

    def test_default_prefix_weight_constant(self) -> None:
        """Default prefix weight used by the function matches the public constant."""
        explicit = jaro_winkler_similarity(
            "patrick", "patric", prefix_weight=JARO_WINKLER_DEFAULT_PREFIX_WEIGHT
        )
        implicit = jaro_winkler_similarity("patrick", "patric")
        assert explicit == implicit

    def test_prefix_max_constant_value(self) -> None:
        """The documented Winkler prefix cap stays at 4 (standard spec)."""
        assert JARO_WINKLER_PREFIX_MAX == 4


# ---------------------------------------------------------------------------
# Levenshtein
# ---------------------------------------------------------------------------


class TestLevenshteinSimilarity:
    """Normalized Levenshtein similarity: 1 - distance/max_len."""

    def test_identical_strings(self) -> None:
        assert levenshtein_similarity("patrick", "patrick") == 1.0

    def test_both_empty(self) -> None:
        assert levenshtein_similarity("", "") == 1.0

    def test_one_empty(self) -> None:
        assert levenshtein_similarity("patrick", "") == 0.0
        assert levenshtein_similarity("", "patrick") == 0.0

    def test_similar_names_high_score(self) -> None:
        # "patrick" vs "patric" = 1 deletion, distance 1, max_len 7
        # similarity = 1 - 1/7 ≈ 0.857
        score = levenshtein_similarity("patrick", "patric")
        assert score == pytest.approx(1 - 1 / 7, abs=0.01)

    def test_different_names_low_score(self) -> None:
        score = levenshtein_similarity("patrick", "xyz")
        assert score < 0.5

    def test_single_substitution(self) -> None:
        # "cat" vs "bat" = 1 substitution, distance 1, max_len 3
        score = levenshtein_similarity("cat", "bat")
        assert score == pytest.approx(1 - 1 / 3, abs=0.01)

    def test_single_char_strings(self) -> None:
        assert levenshtein_similarity("a", "a") == 1.0
        assert levenshtein_similarity("a", "b") == 0.0

    def test_symmetry(self) -> None:
        score_ab = levenshtein_similarity("patrick", "patric")
        score_ba = levenshtein_similarity("patric", "patrick")
        assert score_ab == pytest.approx(score_ba)
