"""European PII regex patterns.

Covers IBAN, VAT numbers, and country-specific formats for France (SSN, phone,
postal code), Germany (phone, postal code), and the UK (NINO, NHS, postcode).

Usage:
    from examples.detectors.europe import PATTERNS, create_detector

Combine with common patterns for full coverage:
    from examples.detectors.common import PATTERNS as COMMON
    from examples.detectors.europe import PATTERNS as EU
    detector = RegexDetector(patterns={**COMMON, **EU})
"""

from piighost.anonymizer import Anonymizer
from piighost.detector import CompositeDetector, RegexDetector

from .common import create_detector as create_common_detector

PATTERNS: dict[str, str] = {
    # --- Pan-European ---
    # IBAN: 2 letters + 2 check digits + up to 30 alphanumeric (BBAN)
    "EU_IBAN": r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}[A-Z0-9]{0,16}\b",
    # VAT: 2-letter country code + 8-12 digits
    "EU_VAT": r"\b[A-Z]{2}\d{8,12}\b",
    # --- France ---
    # French SSN (numéro INSEE): 1 or 2 + 12 digits + optional 2-digit key
    "FR_SSN": r"\b[12]\d{2}(?:0[1-9]|1[0-2])\d{2}\d{3}\d{3}\d{2}(?:\s?\d{2})?\b",
    # French phone: +33 X XX XX XX XX or 0X XX XX XX XX
    "FR_PHONE": r"\b(?:\+33|0)[1-9](?:[\s.\-]?\d{2}){4}\b",
    # French postal code: 5 digits (01000-98999)
    "FR_ZIP": r"\b(?:0[1-9]|[1-8]\d|9[0-8])\d{3}\b",
    # --- Germany ---
    # German phone: +49 or 0 prefix
    "DE_PHONE": r"\b(?:\+49|0)\d{2,5}[\s/\-]?\d{3,10}\b",
    # German postal code: 5 digits (01000-99999)
    "DE_ZIP": r"\b(?:0[1-9]|[1-9]\d)\d{3}\b",
    # --- United Kingdom ---
    # UK National Insurance Number: 2 letters + 6 digits + 1 letter
    "UK_NINO": r"\b[A-CEGHJ-PR-TW-Z]{2}\d{6}[A-D]\b",
    # UK NHS number: 3-3-4 digits
    "UK_NHS": r"\b\d{3}[\s\-]?\d{3}[\s\-]?\d{4}\b",
    # UK postcode: A9 9AA, A99 9AA, A9A 9AA, AA9 9AA, AA99 9AA, AA9A 9AA
    "UK_POSTCODE": r"\b[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}\b",
}


def create_detector() -> RegexDetector:
    """Create a RegexDetector pre-loaded with European patterns."""
    return RegexDetector(patterns=PATTERNS)


def create_full_detector() -> CompositeDetector:
    """Create a detector combining common + European patterns."""
    return CompositeDetector(
        detectors=[
            create_common_detector(),
            create_detector(),
        ]
    )


if __name__ == "__main__":
    import asyncio

    from piighost.linker.entity import ExactEntityLinker
    from piighost.pipeline.base import AnonymizationPipeline
    from piighost.placeholder import LabelCounterPlaceholderFactory
    from piighost.resolver.entity import MergeEntityConflictResolver
    from piighost.resolver.span import ConfidenceSpanConflictResolver

    text = (
        "Client: Marie Dupont, INSEE 185017512345612, tél 06 12 34 56 78. "
        "IBAN: FR7630006000011234567890189. TVA: FR12345678901. "
        "UK contact: NINO AB123456C, NHS 943-476-5919, postcode SW1A 1AA. "
        "Berlin office: +49 30 1234567, PLZ 10115. "
        "Email: marie.dupont@exemple.fr."
    )

    pipeline = AnonymizationPipeline(
        detector=create_full_detector(),
        span_resolver=ConfidenceSpanConflictResolver(),
        entity_linker=ExactEntityLinker(),
        entity_resolver=MergeEntityConflictResolver(),
        anonymizer=Anonymizer(LabelCounterPlaceholderFactory()),
    )

    async def main() -> None:
        anonymized, entities = await pipeline.anonymize(text)

        print("=== European PII Detector (common + EU) ===\n")
        print(f"Original:\n  {text}\n")
        print(f"Anonymized:\n  {anonymized}\n")
        print("Detected entities:")

        tokens = pipeline.ph_factory.create(entities)
        for entity, token in tokens.items():
            canonical = entity.detections[0].text
            print(f"  [{entity.label}] {canonical!r} -> {token}")

    asyncio.run(main())
