"""Pan-European PII regex patterns.

Targets values whose structure is standardised across EU member states
(e.g. the ISO 13616 IBAN). For country-specific numbers, use the
per-country packs (``FR_PATTERNS`` etc.) instead.
"""

from __future__ import annotations

EU_PATTERNS: dict[str, str] = {
    # Generic IBAN: 2-letter country + 2 check digits + 11-30 alphanumerics.
    # Total length 15-34 per ISO 13616. Validate with validate_iban().
    "IBAN": r"\b[A-Z]{2}\d{2}(?:[\s-]?[A-Z0-9]){11,30}\b",
}
