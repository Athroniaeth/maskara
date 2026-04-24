"""US-specific PII regex patterns.

Covers Social Security Numbers, US phone numbers, passports, ZIP codes,
EIN (Employer Identification Number), and bank routing numbers.

Usage:
    from examples.detectors.us import PATTERNS, create_detector

Combine with common patterns for full coverage:
    from examples.detectors.common import PATTERNS as COMMON
    from examples.detectors.us import PATTERNS as US
    detector = RegexDetector(patterns={**COMMON, **US})
"""

from piighost.anonymizer import Anonymizer
from piighost.detector import CompositeDetector, RegexDetector

from .common import create_detector as create_common_detector

PATTERNS: dict[str, str] = {
    # SSN: XXX-XX-XXXX (excludes 000, 666, 900-999 in first group)
    "US_SSN": r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b",
    # US phone: (XXX) XXX-XXXX or XXX-XXX-XXXX, optional +1 prefix
    "US_PHONE": (
        r"\b(?:\+1[\s.\-]?)?"
        r"\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}\b"
    ),
    # US passport: 1 letter + 8 digits
    "US_PASSPORT": r"\b[A-Z]\d{8}\b",
    # ZIP code: 5 digits or ZIP+4
    "US_ZIP_CODE": r"\b\d{5}(?:-\d{4})?\b",
    # EIN: XX-XXXXXXX
    "US_EIN": r"\b\d{2}-\d{7}\b",
    # ABA bank routing number: exactly 9 digits
    "US_BANK_ROUTING": r"\b\d{9}\b",
}


def create_detector() -> RegexDetector:
    """Create a RegexDetector pre-loaded with US-specific patterns."""
    return RegexDetector(patterns=PATTERNS)


def create_full_detector() -> CompositeDetector:
    """Create a detector combining common + US patterns."""
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
    from piighost.placeholder import CounterPlaceholderFactory
    from piighost.resolver.entity import MergeEntityConflictResolver
    from piighost.resolver.span import ConfidenceSpanConflictResolver

    text = (
        "Applicant John Doe, SSN 123-45-6789, phone (555) 867-5309. "
        "Passport C12345678, ZIP 90210-1234. "
        "Company EIN: 12-3456789. Routing: 021000021. "
        "Email: john.doe@example.com."
    )

    pipeline = AnonymizationPipeline(
        detector=create_full_detector(),
        span_resolver=ConfidenceSpanConflictResolver(),
        entity_linker=ExactEntityLinker(),
        entity_resolver=MergeEntityConflictResolver(),
        anonymizer=Anonymizer(CounterPlaceholderFactory()),
    )

    async def main() -> None:
        anonymized, entities = await pipeline.anonymize(text)

        print("=== US PII Detector (common + US) ===\n")
        print(f"Original:\n  {text}\n")
        print(f"Anonymized:\n  {anonymized}\n")
        print("Detected entities:")

        tokens = pipeline.ph_factory.create(entities)
        for entity, token in tokens.items():
            canonical = entity.detections[0].text
            print(f"  [{entity.label}] {canonical!r} -> {token}")

    asyncio.run(main())
