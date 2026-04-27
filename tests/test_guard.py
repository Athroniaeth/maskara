"""Tests for the guard-rail stage and its pipeline integration."""

from __future__ import annotations

import pytest

from piighost.anonymizer import Anonymizer
from piighost.detector.base import ExactMatchDetector, RegexDetector
from piighost.exceptions import PIIRemainingError
from piighost.guard import DetectorGuardRail, DisabledGuardRail
from piighost.pipeline import AnonymizationPipeline
from piighost.placeholder import LabelCounterPlaceholderFactory

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# DisabledGuardRail
# ---------------------------------------------------------------------------


class TestDisabledGuardRail:
    """DisabledGuardRail is a passthrough by design."""

    async def test_passes_arbitrary_text(self) -> None:
        guard = DisabledGuardRail()
        await guard.check("Patrick lives in Paris.")
        await guard.check("<<PERSON:1>> lives in <<LOCATION:1>>.")
        await guard.check("")


# ---------------------------------------------------------------------------
# DetectorGuardRail
# ---------------------------------------------------------------------------


class TestDetectorGuardRail:
    """DetectorGuardRail re-runs a detector on the anonymized output."""

    async def test_passes_when_no_residual_detections(self) -> None:
        guard = DetectorGuardRail(
            detector=RegexDetector(patterns={"EMAIL": r"\S+@\S+"}),
        )
        await guard.check("Hello <<PERSON:1>>, no email here.")

    async def test_raises_when_residual_pii_present(self) -> None:
        guard = DetectorGuardRail(
            detector=RegexDetector(patterns={"EMAIL": r"\S+@\S+"}),
        )
        with pytest.raises(PIIRemainingError) as exc_info:
            await guard.check("Hello <<PERSON:1>>, contact me at user@example.com.")

        err = exc_info.value
        assert err.detections, "PIIRemainingError should carry the residual detections"
        assert err.detections[0].label == "EMAIL"
        assert err.detections[0].text == "user@example.com."

    async def test_residual_detections_count_in_message(self) -> None:
        guard = DetectorGuardRail(
            detector=RegexDetector(patterns={"DIGITS": r"\d+"}),
        )
        with pytest.raises(PIIRemainingError) as exc_info:
            await guard.check("ref 123 and ref 456")
        assert "2 residual" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Pipeline integration
# ---------------------------------------------------------------------------


def _pipeline_with_guard(
    primary_detector: ExactMatchDetector,
    guard_detector: RegexDetector,
) -> AnonymizationPipeline:
    return AnonymizationPipeline(
        detector=primary_detector,
        anonymizer=Anonymizer(LabelCounterPlaceholderFactory()),
        guard_rail=DetectorGuardRail(detector=guard_detector),
    )


class TestPipelineIntegration:
    """A guard rail wired into the pipeline runs after anonymization."""

    async def test_default_guard_is_noop(self) -> None:
        """Without a guard_rail argument, anonymize behaves as before."""
        pipeline = AnonymizationPipeline(
            detector=ExactMatchDetector([("Patrick", "PERSON")]),
            anonymizer=Anonymizer(LabelCounterPlaceholderFactory()),
        )
        anonymized, _ = await pipeline.anonymize("Patrick lives here.")
        assert anonymized == "<<PERSON:1>> lives here."

    async def test_passes_when_anonymization_is_complete(self) -> None:
        """Primary detector covers all PII the guard would otherwise raise on."""
        pipeline = _pipeline_with_guard(
            primary_detector=ExactMatchDetector(
                [("Patrick", "PERSON"), ("user@example.com", "EMAIL")],
            ),
            guard_detector=RegexDetector(patterns={"EMAIL": r"\S+@\S+"}),
        )
        anonymized, _ = await pipeline.anonymize(
            "Patrick lives here, contact user@example.com."
        )
        assert "user@example.com" not in anonymized

    async def test_raises_when_primary_detector_misses_pii(self) -> None:
        """Guard catches what the primary detector did not anonymize."""
        pipeline = _pipeline_with_guard(
            # Primary only knows about Patrick, misses the email
            primary_detector=ExactMatchDetector([("Patrick", "PERSON")]),
            guard_detector=RegexDetector(patterns={"EMAIL": r"\S+@\S+"}),
        )
        with pytest.raises(PIIRemainingError) as exc_info:
            await pipeline.anonymize("Patrick lives here, contact user@example.com.")
        residual_labels = [d.label for d in exc_info.value.detections]
        assert "EMAIL" in residual_labels

    async def test_no_mapping_cached_when_guard_raises(self) -> None:
        """A raised guard short-circuits before the cache write so that
        subsequent deanonymize() calls cannot return tainted text."""
        from piighost.exceptions import CacheMissError

        pipeline = _pipeline_with_guard(
            primary_detector=ExactMatchDetector([("Patrick", "PERSON")]),
            guard_detector=RegexDetector(patterns={"EMAIL": r"\S+@\S+"}),
        )
        with pytest.raises(PIIRemainingError):
            await pipeline.anonymize("Patrick lives here, contact user@example.com.")

        # The anonymized text the pipeline tried to produce is not in
        # the cache, so deanonymize must fail.
        partial_anonymized = "<<PERSON:1>> lives here, contact user@example.com."
        with pytest.raises(CacheMissError):
            await pipeline.deanonymize(partial_anonymized)
