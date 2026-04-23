"""US PII regex patterns.

Labels are prefixed with ``US_`` so they do not collide with other
packs.

Usage::

    from piighost.detector import RegexDetector
    from piighost.detector.patterns import US_PATTERNS

    detector = RegexDetector(patterns=US_PATTERNS)
"""

from __future__ import annotations

US_PATTERNS: dict[str, str] = {
    # SSN: NNN-NN-NNNN. Does not enforce SSA invalid-ranges (e.g. 000-xx-xxxx);
    # callers who need stricter validation should add a post-filter.
    "US_SSN": r"\b\d{3}-\d{2}-\d{4}\b",
    # US phone: optional +1 prefix, optional parentheses around area code,
    # then 3-3-4 digits with dot/space/dash separators.
    "US_PHONE": (r"\b(?:\+?1[\s.-]?)?\(?[2-9]\d{2}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b"),
    # ZIP code (5 digits) and ZIP+4 (5-4 digits).
    "US_ZIP": r"\b\d{5}(?:-\d{4})?\b",
}
