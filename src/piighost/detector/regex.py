from __future__ import annotations

from piighost.detector.patterns import DEFAULT_PATTERNS
from piighost.detector.patterns._base import Pattern
from piighost.models import Detection, Span


class RegexDetector:
    def __init__(self, patterns: list[Pattern] | None = None) -> None:
        self._patterns = patterns if patterns is not None else DEFAULT_PATTERNS

    async def detect(self, text: str) -> list[Detection]:
        out: list[Detection] = []
        for pattern in self._patterns:
            for m in pattern.regex.finditer(text):
                matched = m.group(0)
                if pattern.validator is not None:
                    try:
                        if not pattern.validator(matched):
                            continue
                    except Exception:
                        continue
                out.append(
                    Detection(
                        text=matched,
                        label=pattern.label,
                        position=Span(start_pos=m.start(), end_pos=m.end()),
                        confidence=pattern.confidence,
                    )
                )
        return _resolve_overlaps(out)


def _resolve_overlaps(detections: list[Detection]) -> list[Detection]:
    detections.sort(
        key=lambda d: (
            d.position.start_pos,
            -(d.position.end_pos - d.position.start_pos),
        )
    )
    accepted: list[Detection] = []
    for d in detections:
        if accepted and d.position.start_pos < accepted[-1].position.end_pos:
            continue
        accepted.append(d)
    return accepted
