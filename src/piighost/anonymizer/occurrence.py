"""Strategies for locating every occurrence of a fragment in a text."""

import re
from typing import Protocol


class OccurrenceFinder(Protocol):
    """Interface for finding all positions of a fragment in a text.

    Future implementations may use fuzzy matching (e.g. Levenshtein,
    phonetic similarity) to catch misspellings.  The anonymiser depends
    only on this protocol.
    """

    def find_all(self, text: str, fragment: str) -> list[tuple[int, int]]:
        """Return every ``(start, end)`` pair where *fragment* appears.

        Args:
            text: The source string to search.
            fragment: The substring to look for.

        Returns:
            A sorted list of ``(start, end)`` tuples.  May be empty.
        """
        ...  # pragma: no cover


class RegexOccurrenceFinder:
    r"""Find occurrences using a word-boundary regex.

    Uses ``\b`` anchors around the escaped fragment so that partial
    matches inside longer words are ignored.

    Example:
        >>> finder = RegexOccurrenceFinder()
        >>> finder.find_all("Salut Patrick, APatrick", "Patrick")
        [(6, 13)]

    ``"APatrick"`` is *not* matched because the leading ``A`` prevents
    the word boundary from firing.

    Args:
        flags: Regex flags passed to ``re.compile``.  Defaults to
            ``re.IGNORECASE`` for case-insensitive matching.
    """

    def __init__(self, flags: re.RegexFlag = re.IGNORECASE) -> None:
        self._flags = flags

    def find_all(self, text: str, fragment: str) -> list[tuple[int, int]]:
        """Return word-boundary matches of *fragment* in *text*.

        Args:
            text: The source string.
            fragment: The exact substring to match (regex-escaped).

        Returns:
            Sorted ``(start, end)`` pairs for every match.
        """
        escaped = re.escape(fragment)
        # \b only fires between a word and non-word character, so it
        # fails when the fragment starts/ends with a non-word char
        # (e.g. "+33…").  Fall back to a lookaround in that case.
        prefix = r"\b" if fragment[0:1].isalnum() or fragment[0:1] == "_" else r"(?<!\w)"
        suffix = r"\b" if fragment[-1:].isalnum() or fragment[-1:] == "_" else r"(?!\w)"
        pattern = re.compile(
            f"{prefix}{escaped}{suffix}",
            self._flags,
        )
        return [(m.start(), m.end()) for m in pattern.finditer(text)]
