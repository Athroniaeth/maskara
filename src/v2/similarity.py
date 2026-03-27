"""String similarity functions for fuzzy entity matching.

Pure Python implementations — no external dependencies.
Both functions return a float in ``[0.0, 1.0]`` where 1.0 means identical.
"""

from typing import Callable

AnySimilarityFn = Callable[[str, str], float]


def jaro_winkler_similarity(s1: str, s2: str, prefix_weight: float = 0.1) -> float:
    """Jaro-Winkler similarity between two strings.

    Good for short strings like entity names — gives a bonus for a shared
    prefix (up to 4 characters).

    Args:
        s1: First string.
        s2: Second string.
        prefix_weight: Winkler prefix scaling factor (default 0.1).

    Returns:
        Similarity score in [0.0, 1.0].
    """
    if s1 == s2:
        return 1.0

    len1, len2 = len(s1), len(s2)

    if len1 == 0 or len2 == 0:
        return 0.0

    # Maximum distance for matching characters.
    match_distance = max(len1, len2) // 2 - 1
    if match_distance < 0:
        match_distance = 0

    s1_matches = [False] * len1
    s2_matches = [False] * len2

    matches = 0
    transpositions = 0

    # Find matching characters.
    for i in range(len1):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len2)

        for j in range(start, end):
            if s2_matches[j] or s1[i] != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    # Count transpositions.
    k = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1

    jaro = (
        matches / len1 + matches / len2 + (matches - transpositions / 2) / matches
    ) / 3

    # Winkler bonus for shared prefix (up to 4 chars).
    prefix_len = 0
    for i in range(min(4, len1, len2)):
        if s1[i] == s2[i]:
            prefix_len += 1
        else:
            break

    return jaro + prefix_len * prefix_weight * (1 - jaro)


def levenshtein_similarity(s1: str, s2: str) -> float:
    """Normalized Levenshtein similarity.

    Computed as ``1 - distance / max(len(s1), len(s2))``.

    Args:
        s1: First string.
        s2: Second string.

    Returns:
        Similarity score in [0.0, 1.0].
    """
    if s1 == s2:
        return 1.0

    len1, len2 = len(s1), len(s2)

    if len1 == 0 or len2 == 0:
        return 0.0

    # DP matrix for edit distance.
    prev = list(range(len2 + 1))
    curr = [0] * (len2 + 1)

    for i in range(1, len1 + 1):
        curr[0] = i
        for j in range(1, len2 + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            curr[j] = min(
                prev[j] + 1,  # deletion
                curr[j - 1] + 1,  # insertion
                prev[j - 1] + cost,  # substitution
            )
        prev, curr = curr, prev

    distance = prev[len2]
    return 1 - distance / max(len1, len2)
