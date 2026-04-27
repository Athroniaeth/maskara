"""Guard rail stage: re-detection on the anonymized output.

A guard rail re-runs a detector on the anonymized text produced by the
pipeline.  If anything is still detected, the guard rail raises a
``PIIRemainingError``.  This catches cases where a misconfigured
detector, a NER miss, or a placeholder that did not match left raw
PII in the output.

The protocol is binary: pass or fail, no threshold to tune.  For a
graded view of remaining risk, see ``AnyRiskAssessor`` (roadmap).
"""

from __future__ import annotations

from typing import Protocol

from piighost.detector import AnyDetector
from piighost.exceptions import PIIRemainingError


class AnyGuardRail(Protocol):
    """Protocol for the final pipeline stage.

    Implementations decide whether the anonymized text is safe to
    return.  ``check`` returns ``None`` on success and raises
    ``PIIRemainingError`` (or a subclass) on failure.
    """

    async def check(self, anonymized_text: str) -> None:
        """Validate that ``anonymized_text`` no longer contains PII.

        Args:
            anonymized_text: The text produced by ``Anonymizer``.

        Raises:
            PIIRemainingError: If residual PII is detected.
        """
        ...


class DisabledGuardRail:
    """Default no-op guard rail.

    Mirrors the ``Disabled*`` family used by the other pipeline stages
    so that pipelines built without a custom guard rail keep their
    current behaviour: the anonymized text is returned as-is.
    """

    async def check(self, anonymized_text: str) -> None:
        return None


class DetectorGuardRail:
    """Guard rail backed by an ``AnyDetector``.

    Re-runs a detector on the anonymized output.  If the detector
    produces any detection, the guard rail raises
    ``PIIRemainingError`` carrying the residual detections so callers
    can log or surface them.

    The wrapped detector is independent from the pipeline detector:
    typical pairings include a strict regex detector after a permissive
    NER (catch leftover IBANs / emails the NER missed) or a tighter
    NER after a regex pass (catch unusual names).

    Args:
        detector: Any ``AnyDetector`` implementation.

    Example:
        >>> import asyncio
        >>> from piighost.detector.base import RegexDetector
        >>> guard = DetectorGuardRail(
        ...     detector=RegexDetector(patterns={"EMAIL": r"\\S+@\\S+"}),
        ... )
        >>> asyncio.run(guard.check("Hello <<PERSON:1>>"))  # passes
    """

    _detector: AnyDetector

    def __init__(self, detector: AnyDetector) -> None:
        self._detector = detector

    async def check(self, anonymized_text: str) -> None:
        residual = await self._detector.detect(anonymized_text)
        if residual:
            raise PIIRemainingError(
                f"{len(residual)} residual detection(s) found in anonymized text",
                detections=list(residual),
            )


__all__ = [
    "AnyGuardRail",
    "DetectorGuardRail",
    "DisabledGuardRail",
]
