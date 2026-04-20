from __future__ import annotations

import re

from piighost.detector.patterns._base import Pattern

_CC_RE = re.compile(r"\b(?:\d[ \-]?){12,18}\d\b")


def _luhn_valid(text: str) -> bool:
    digits = [int(c) for c in text if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


CREDIT_CARD_PATTERN = Pattern(
    label="CREDIT_CARD",
    regex=_CC_RE,
    validator=_luhn_valid,
)
