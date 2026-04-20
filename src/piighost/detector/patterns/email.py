from __future__ import annotations

import re

from piighost.detector.patterns._base import Pattern

_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)

EMAIL_PATTERN = Pattern(label="EMAIL_ADDRESS", regex=_EMAIL_RE)
