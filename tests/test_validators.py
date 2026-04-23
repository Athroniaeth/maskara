"""Unit tests for :mod:`piighost.validators`."""

from __future__ import annotations

import pytest

from piighost.validators import validate_iban, validate_luhn, validate_nir


# ---------------------------------------------------------------------------
# Luhn
# ---------------------------------------------------------------------------


class TestLuhn:
    """Luhn mod-10 checksum."""

    @pytest.mark.parametrize(
        "value",
        [
            "4111111111111111",  # Classic Visa test card
            "4111 1111 1111 1111",  # With spaces
            "4111-1111-1111-1111",  # With dashes
            "5500000000000004",  # Mastercard test
            "340000000000009",  # Amex test (15 digits)
            "79927398713",  # Wikipedia Luhn example
        ],
    )
    def test_accepts_valid_numbers(self, value: str) -> None:
        assert validate_luhn(value) is True

    @pytest.mark.parametrize(
        "value",
        [
            "4111111111111112",  # Last digit wrong
            "1234567890123456",  # Random
            "0000000000000001",
            "79927398710",  # Same as Wikipedia but wrong check digit
        ],
    )
    def test_rejects_invalid_numbers(self, value: str) -> None:
        assert validate_luhn(value) is False

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "4",  # Single digit: below 2-digit minimum
            "not-a-number",
            "4111 1111 abcd 1111",
            "   ",
        ],
    )
    def test_rejects_malformed_input(self, value: str) -> None:
        assert validate_luhn(value) is False


# ---------------------------------------------------------------------------
# IBAN mod-97
# ---------------------------------------------------------------------------


class TestIban:
    """ISO 13616 mod-97 checksum."""

    @pytest.mark.parametrize(
        "value",
        [
            "FR14 2004 1010 0505 0001 3M02 606",  # France
            "DE89 3704 0044 0532 0130 00",  # Germany
            "GB82 WEST 1234 5698 7654 32",  # UK
            "CH93 0076 2011 6238 5295 7",  # Switzerland
            "fr1420041010050500013m02606",  # Lowercase, no spaces
        ],
    )
    def test_accepts_valid_ibans(self, value: str) -> None:
        assert validate_iban(value) is True

    @pytest.mark.parametrize(
        "value",
        [
            "FR14 2004 1010 0505 0001 3M02 607",  # Last digit wrong
            "DE89 3704 0044 0532 0130 01",
            "GB82 WEST 1234 5698 7654 33",
        ],
    )
    def test_rejects_invalid_checksum(self, value: str) -> None:
        assert validate_iban(value) is False

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "FR",  # Too short
            "FR14",  # No body
            "F14 2004 1010 0505 0001 3M02 606",  # 1-letter country
            "1234 5678 9012 3456",  # No country prefix
            "FR14 2004 1010 0505 0001 3M02 606 EXTRA TOO LONG FOR ISO",
        ],
    )
    def test_rejects_malformed_input(self, value: str) -> None:
        assert validate_iban(value) is False


# ---------------------------------------------------------------------------
# NIR
# ---------------------------------------------------------------------------


class TestNir:
    """French NIR checksum."""

    @pytest.mark.parametrize(
        "value",
        [
            "184127645108946",  # body=1841276451089 key=46
            "1 84 12 76 451 089 46",  # With spaces
            "1.84.12.76.451.089.46",  # With dots
            "295057510800051",  # body=2950575108000 key=51 (woman)
        ],
    )
    def test_accepts_valid_nir(self, value: str) -> None:
        assert validate_nir(value) is True

    @pytest.mark.parametrize(
        "value",
        [
            "184127645108947",  # Wrong key
            "284127645108946",  # First digit flip changes body → key mismatch
        ],
    )
    def test_rejects_invalid_checksum(self, value: str) -> None:
        assert validate_nir(value) is False

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "12345",
            "3 84 12 76 451 089 46",  # Sex digit must be 1 or 2
            "1 84 13 76 451 089 46",  # Month 13 invalid
            "abcdefghijklmno",
        ],
    )
    def test_rejects_malformed_input(self, value: str) -> None:
        assert validate_nir(value) is False

    def test_corsican_department_2a_accepted(self) -> None:
        # NIR = sex(1) + YY(2) + MM(2) + dep(2) + com(3) + order(3) + key(2) = 15 chars.
        # For Corsica (2A → 19 in the mod-97 computation), the 13-digit body
        # used for the checksum is: 1 84 12 19 764 510 = "1841219764510".
        body = int("1" + "84" + "12" + "19" + "764" + "510")
        key = 97 - (body % 97)
        nir = "1" + "84" + "12" + "2A" + "764" + "510" + f"{key:02d}"
        assert validate_nir(nir) is True

    def test_corsican_department_2b_accepted(self) -> None:
        # Same as 2A but dep "2B" → 18.
        body = int("1" + "84" + "12" + "18" + "764" + "510")
        key = 97 - (body % 97)
        nir = "1" + "84" + "12" + "2B" + "764" + "510" + f"{key:02d}"
        assert validate_nir(nir) is True
