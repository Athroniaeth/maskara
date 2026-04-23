"""Country-agnostic PII regex patterns.

These patterns target PII whose syntax is not country-specific:
e-mail, URL, IPv4, credit card. Import and pass them to
:class:`~piighost.detector.RegexDetector`::

    from piighost.detector import RegexDetector
    from piighost.detector.patterns import GENERIC_PATTERNS
    from piighost.validators import validate_luhn

    detector = RegexDetector(
        patterns=GENERIC_PATTERNS,
        validators={"CREDIT_CARD": validate_luhn},
    )

The credit-card pattern deliberately accepts any 13-19 digit sequence;
pair it with ``validate_luhn`` to filter false positives.
"""

from __future__ import annotations

GENERIC_PATTERNS: dict[str, str] = {
    # Simplified RFC 5322 (not the full grammar, but tight enough to avoid
    # matching everything containing an "@").
    "EMAIL": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    # Plain http(s) URL up to the first whitespace or quote/angle.
    "URL": r"https?://[^\s<>\"']+",
    # IPv4 with per-octet 0-255 constraint (no plain r"\d{1,3}\.").
    "IPV4": (
        r"(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
        r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)"
    ),
    # 13-19 digits with optional spaces/dashes. Must be checksum-validated.
    "CREDIT_CARD": r"\b(?:\d[ -]?){12,18}\d\b",
}
