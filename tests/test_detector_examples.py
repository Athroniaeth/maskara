"""Tests that example detector patterns work with trailing punctuation.

Every PII pattern from the example detectors (common, US, Europe) must
correctly detect AND anonymize entities when followed by '.' or ','
(typical end-of-sentence / list separators).
"""


from piighost.anonymizer.anonymizer import Anonymizer
from piighost.anonymizer.detector import RegexDetector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _anonymize(patterns: dict[str, str], text: str) -> str:
    detector = RegexDetector(patterns=patterns)
    anonymizer = Anonymizer(detector=detector)
    return anonymizer.anonymize(text).anonymized_text


def _assert_anonymized_with_trailing(
    patterns: dict[str, str],
    label: str,
    raw_value: str,
) -> None:
    """Assert *raw_value* is replaced in text ending with '.' and ','."""
    for punct in (".", ","):
        text = f"Value is {raw_value}{punct}"
        result = _anonymize(patterns, text)
        assert raw_value not in result, (
            f"{label!r} not anonymized before {punct!r} in: {result}"
        )
        assert f"<<{label}_1>>" in result, (
            f"<<{label}_1>> missing before {punct!r} in: {result}"
        )


# ---------------------------------------------------------------------------
# Common patterns
# ---------------------------------------------------------------------------

from examples.detectors.common import PATTERNS as COMMON_PATTERNS


class TestCommonPatternsTrailingPunctuation:
    def test_email(self) -> None:
        _assert_anonymized_with_trailing(COMMON_PATTERNS, "EMAIL", "alice@example.com")

    def test_ip_v4(self) -> None:
        _assert_anonymized_with_trailing(COMMON_PATTERNS, "IP_V4", "192.168.1.42")

    def test_url(self) -> None:
        _assert_anonymized_with_trailing(
            COMMON_PATTERNS, "URL", "https://api.example.com/v1"
        )

    def test_credit_card(self) -> None:
        _assert_anonymized_with_trailing(
            COMMON_PATTERNS, "CREDIT_CARD", "4532-1234-5678-9012"
        )

    def test_phone_international(self) -> None:
        _assert_anonymized_with_trailing(
            COMMON_PATTERNS, "PHONE_INTERNATIONAL", "+33 6 12 34 56 78"
        )

    def test_openai_api_key(self) -> None:
        _assert_anonymized_with_trailing(
            COMMON_PATTERNS, "OPENAI_API_KEY", "sk-proj-abc123xyz456789ABCDEFGH"
        )

    def test_aws_access_key(self) -> None:
        _assert_anonymized_with_trailing(
            COMMON_PATTERNS, "AWS_ACCESS_KEY", "AKIAIOSFODNN7EXAMPLE"
        )

    def test_github_token(self) -> None:
        _assert_anonymized_with_trailing(
            COMMON_PATTERNS,
            "GITHUB_TOKEN",
            "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij",
        )

    def test_stripe_key(self) -> None:
        _assert_anonymized_with_trailing(
            COMMON_PATTERNS,
            "STRIPE_KEY",
            "sk_live_ABCDEFGHIJKLMNOPQRSTUVWXyz",
        )


# ---------------------------------------------------------------------------
# US patterns
# ---------------------------------------------------------------------------

from examples.detectors.us import PATTERNS as US_PATTERNS


class TestUSPatternsTrailingPunctuation:
    def test_ssn(self) -> None:
        _assert_anonymized_with_trailing(US_PATTERNS, "US_SSN", "123-45-6789")

    def test_phone(self) -> None:
        _assert_anonymized_with_trailing(US_PATTERNS, "US_PHONE", "555-867-5309")

    def test_passport(self) -> None:
        _assert_anonymized_with_trailing(US_PATTERNS, "US_PASSPORT", "C12345678")

    def test_zip_code(self) -> None:
        _assert_anonymized_with_trailing(US_PATTERNS, "US_ZIP_CODE", "90210-1234")

    def test_ein(self) -> None:
        _assert_anonymized_with_trailing(US_PATTERNS, "US_EIN", "12-3456789")

    def test_bank_routing(self) -> None:
        _assert_anonymized_with_trailing(US_PATTERNS, "US_BANK_ROUTING", "021000021")


# ---------------------------------------------------------------------------
# European patterns
# ---------------------------------------------------------------------------

from examples.detectors.europe import PATTERNS as EU_PATTERNS


class TestEuropePatternsTrailingPunctuation:
    def test_iban(self) -> None:
        _assert_anonymized_with_trailing(
            EU_PATTERNS, "EU_IBAN", "FR7630006000011234567890189"
        )

    def test_vat(self) -> None:
        _assert_anonymized_with_trailing(EU_PATTERNS, "EU_VAT", "FR12345678901")

    def test_fr_ssn(self) -> None:
        _assert_anonymized_with_trailing(EU_PATTERNS, "FR_SSN", "185017512345612")

    def test_fr_phone(self) -> None:
        _assert_anonymized_with_trailing(EU_PATTERNS, "FR_PHONE", "06 12 34 56 78")

    def test_fr_zip(self) -> None:
        _assert_anonymized_with_trailing(EU_PATTERNS, "FR_ZIP", "75001")

    def test_de_phone(self) -> None:
        _assert_anonymized_with_trailing(EU_PATTERNS, "DE_PHONE", "030 1234567")

    def test_de_zip(self) -> None:
        # DE_ZIP and FR_ZIP overlap (both match 5 digits); whichever label
        # wins depends on dict ordering.  We only check the value is gone.
        for punct in (".", ","):
            text = f"Value is 10115{punct}"
            result = _anonymize(EU_PATTERNS, text)
            assert "10115" not in result

    def test_uk_nino(self) -> None:
        _assert_anonymized_with_trailing(EU_PATTERNS, "UK_NINO", "AB123456C")

    def test_uk_nhs(self) -> None:
        _assert_anonymized_with_trailing(EU_PATTERNS, "UK_NHS", "943-476-5919")

    def test_uk_postcode(self) -> None:
        _assert_anonymized_with_trailing(EU_PATTERNS, "UK_POSTCODE", "SW1A 1AA")
