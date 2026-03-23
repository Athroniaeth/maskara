"""Common PII regex patterns — universal across regions.

Covers emails, IP addresses, URLs, credit cards, international phone numbers,
and cloud provider API keys.  These patterns work regardless of locale.

Usage:
    from examples.detectors.common import PATTERNS, create_detector
"""

from piighost.anonymizer import Anonymizer
from piighost.anonymizer.detector import RegexDetector

PATTERNS: dict[str, str] = {
    "EMAIL": r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    "IP_V4": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    "IP_V6": (
        r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b"
        r"|\b(?:[0-9a-fA-F]{1,4}:){1,7}:\b"
        r"|\b::(?:[0-9a-fA-F]{1,4}:){0,6}[0-9a-fA-F]{1,4}\b"
    ),
    # Trailing punctuation (.,;:!?) is excluded to avoid capturing end-of-sentence marks
    "URL": r"https?://[^\s<>\"']+[^\s<>\"'.,;:!?\)\]}]",
    # Matches common card formats: XXXX-XXXX-XXXX-XXXX, XXXX XXXX XXXX XXXX
    "CREDIT_CARD": r"\b\d{4}[\s\-]\d{4}[\s\-]\d{4}[\s\-]\d{4}\b",
    "PHONE_INTERNATIONAL": r"\+\d{1,3}[\s.\-]?\(?\d{1,4}\)?(?:[\s.\-]?\d{1,4}){1,4}",
    "OPENAI_API_KEY": r"sk-(?:proj-)?[A-Za-z0-9\-_]{20,}",
    "AWS_ACCESS_KEY": r"\bAKIA[0-9A-Z]{16}\b",
    "GITHUB_TOKEN": r"\bgh[ps]_[A-Za-z0-9_]{36,}\b",
    "STRIPE_KEY": r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{24,}\b",
}


def create_detector() -> RegexDetector:
    """Create a RegexDetector pre-loaded with all common patterns."""
    return RegexDetector(patterns=PATTERNS)


if __name__ == "__main__":
    text = (
        "Contact me at alice.smith@example.com or call +33 6 12 34 56 78. "
        "My server is at 192.168.1.42 and also at https://api.example.com/v1. "
        "API key: sk-proj-abc123xyz456789ABCDEFGH. "
        "Card: 4532-1234-5678-9012."
    )

    detector = create_detector()
    anonymizer = Anonymizer(detector=detector)
    result = anonymizer.anonymize(text)

    print("=== Common PII Detector ===\n")
    print(f"Original:\n  {result.original_text}\n")
    print(f"Anonymized:\n  {result.anonymized_text}\n\n")
    print("Detected entities:")
    for p in result.placeholders:
        print(f"  [{p.label}] {p.original!r} -> {p.replacement}")
