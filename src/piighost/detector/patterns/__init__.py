from __future__ import annotations

from piighost.detector.patterns._base import Pattern
from piighost.detector.patterns.email import EMAIL_PATTERN

DEFAULT_PATTERNS: list[Pattern] = [EMAIL_PATTERN]
