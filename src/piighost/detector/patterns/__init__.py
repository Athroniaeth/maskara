from __future__ import annotations

from piighost.detector.patterns._base import Pattern
from piighost.detector.patterns.credit_card import CREDIT_CARD_PATTERN
from piighost.detector.patterns.email import EMAIL_PATTERN
from piighost.detector.patterns.iban import IBAN_PATTERN
from piighost.detector.patterns.ip import IPV4_PATTERN, IPV6_PATTERN
from piighost.detector.patterns.phone import PHONE_PATTERN

DEFAULT_PATTERNS: list[Pattern] = [
    EMAIL_PATTERN,
    PHONE_PATTERN,
    IPV4_PATTERN,
    IPV6_PATTERN,
    CREDIT_CARD_PATTERN,
    IBAN_PATTERN,
]
