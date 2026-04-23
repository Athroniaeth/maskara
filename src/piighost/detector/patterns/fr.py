"""French PII regex patterns.

Labels are prefixed with ``FR_`` so they do not collide with US / pan-EU
packs when used together.

Usage::

    from piighost.detector import RegexDetector
    from piighost.detector.patterns import FR_PATTERNS
    from piighost.validators import validate_iban, validate_nir

    detector = RegexDetector(
        patterns=FR_PATTERNS,
        validators={
            "FR_IBAN": validate_iban,
            "FR_NIR": validate_nir,
        },
    )

The IBAN and NIR patterns are permissive on structure (they tolerate
separators and variants); pair them with their matching validator to
eliminate false positives.
"""

from __future__ import annotations

FR_PATTERNS: dict[str, str] = {
    # +33 or 0 prefix, 1-digit area code (1-9), then four pairs.
    # Use (?<!\d) instead of \b because \b does not match between a
    # non-word char and "+" (both are non-word in regex terms).
    "FR_PHONE": r"(?<!\d)(?:\+33|0)[1-9](?:[\s.-]?\d{2}){4}(?!\d)",
    # IBAN FR: FR + 2 check digits + 23 alphanumerics (optional separators).
    # Validate with validate_iban() to confirm the mod-97 checksum.
    "FR_IBAN": r"\bFR\d{2}(?:[\s-]?[A-Z0-9]){23}\b",
    # NIR: sex(1|2) + YY + MM (01-12, 2A, 2B) + dep(2) + com(3) + order(3) + key(2).
    # Validate with validate_nir() to confirm the key.
    "FR_NIR": (
        r"\b[12][\s.-]?\d{2}[\s.-]?(?:0[1-9]|1[0-2])[\s.-]?"
        r"(?:2A|2B|\d{2})[\s.-]?\d{3}[\s.-]?\d{3}[\s.-]?\d{2}\b"
    ),
    # SIRET: 9-digit SIREN + 5-digit establishment number, optional grouping.
    "FR_SIRET": r"\b\d{3}[\s-]?\d{3}[\s-]?\d{3}[\s-]?\d{5}\b",
}
