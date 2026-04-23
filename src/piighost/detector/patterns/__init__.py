"""Curated regex packs for common PII by region.

Each constant is a ``dict[str, str]`` mapping an entity label to a regex
pattern. Pass them to :class:`~piighost.detector.RegexDetector` directly,
or merge several packs:

    from piighost.detector import RegexDetector
    from piighost.detector.patterns import FR_PATTERNS, GENERIC_PATTERNS

    detector = RegexDetector(patterns={**GENERIC_PATTERNS, **FR_PATTERNS})

Some patterns are syntactic only (IBAN, CREDIT_CARD, FR_NIR). Pair them
with the matching validator from :mod:`piighost.validators` to filter
out format-valid but checksum-invalid false positives.
"""

from piighost.detector.patterns.eu import EU_PATTERNS
from piighost.detector.patterns.fr import FR_PATTERNS
from piighost.detector.patterns.generic import GENERIC_PATTERNS
from piighost.detector.patterns.us import US_PATTERNS

__all__ = [
    "EU_PATTERNS",
    "FR_PATTERNS",
    "GENERIC_PATTERNS",
    "US_PATTERNS",
]
