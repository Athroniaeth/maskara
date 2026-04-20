from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Pattern:
    label: str
    regex: re.Pattern[str]
    validator: Callable[[str], bool] | None = None
    confidence: float = 0.99
