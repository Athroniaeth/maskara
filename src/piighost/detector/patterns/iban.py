from __future__ import annotations

import re

from piighost.detector.patterns._base import Pattern

_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}\b")


def _iban_mod97(text: str) -> bool:
    normalized = "".join(c for c in text if c.isalnum()).upper()
    if not 15 <= len(normalized) <= 34:
        return False
    if not normalized[:2].isalpha() or not normalized[2:4].isdigit():
        return False
    rearranged = normalized[4:] + normalized[:4]
    converted = "".join(
        str(ord(c) - 55) if c.isalpha() else c for c in rearranged
    )
    try:
        return int(converted) % 97 == 1
    except ValueError:
        return False


IBAN_PATTERN = Pattern(
    label="IBAN_CODE",
    regex=_IBAN_RE,
    validator=_iban_mod97,
)
