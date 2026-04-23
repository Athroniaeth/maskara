"""Sanity tests for the curated regex packs shipped in
``piighost.detector.patterns``.

These tests focus on two things:
- each pattern compiles and matches a realistic positive example;
- each pattern rejects a clearly unrelated negative example;

The goal is not full regex coverage but a regression guard: if a
pattern is edited and breaks, the test fails.
"""

from __future__ import annotations

import re

import pytest

from piighost.detector import RegexDetector
from piighost.detector.patterns import (
    EU_PATTERNS,
    FR_PATTERNS,
    GENERIC_PATTERNS,
    US_PATTERNS,
)
from piighost.validators import validate_iban, validate_luhn, validate_nir


# ---------------------------------------------------------------------------
# Compile sanity (synchronous)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "pack",
    [EU_PATTERNS, FR_PATTERNS, GENERIC_PATTERNS, US_PATTERNS],
    ids=["eu", "fr", "generic", "us"],
)
def test_every_pattern_compiles(pack: dict[str, str]) -> None:
    for label, pattern in pack.items():
        try:
            re.compile(pattern)
        except re.error as exc:
            pytest.fail(f"Pattern {label!r} failed to compile: {exc}")


def test_all_labels_are_uppercase_and_unique_per_pack() -> None:
    for pack in (EU_PATTERNS, FR_PATTERNS, GENERIC_PATTERNS, US_PATTERNS):
        for label in pack:
            assert label == label.upper(), f"label should be uppercase: {label!r}"


# ---------------------------------------------------------------------------
# Generic
# ---------------------------------------------------------------------------


class TestGeneric:
    pytestmark = pytest.mark.asyncio

    async def test_email(self) -> None:
        detector = RegexDetector(patterns=GENERIC_PATTERNS)
        result = await detector.detect("Contactez alice@example.com svp")
        assert any(d.label == "EMAIL" and d.text == "alice@example.com" for d in result)

    async def test_url(self) -> None:
        detector = RegexDetector(patterns=GENERIC_PATTERNS)
        result = await detector.detect("voir https://example.com/path?a=1")
        assert any(d.label == "URL" for d in result)

    async def test_ipv4_accepts_valid_and_rejects_out_of_range(self) -> None:
        detector = RegexDetector(patterns={"IPV4": GENERIC_PATTERNS["IPV4"]})
        valid = await detector.detect("serveur 192.168.1.1 actif")
        assert len(valid) == 1
        rejected = await detector.detect("invalide 999.999.999.999 nope")
        assert rejected == []

    async def test_credit_card_with_luhn_validator_filters_false_positives(
        self,
    ) -> None:
        detector = RegexDetector(
            patterns={"CREDIT_CARD": GENERIC_PATTERNS["CREDIT_CARD"]},
            validators={"CREDIT_CARD": validate_luhn},
        )
        text = "bon: 4111 1111 1111 1111, mauvais: 1234 5678 9012 3456"
        result = await detector.detect(text)
        kept = [d.text for d in result]
        assert "4111 1111 1111 1111" in kept
        assert "1234 5678 9012 3456" not in kept


# ---------------------------------------------------------------------------
# French
# ---------------------------------------------------------------------------


class TestFrench:
    pytestmark = pytest.mark.asyncio

    async def test_phone(self) -> None:
        detector = RegexDetector(patterns={"FR_PHONE": FR_PATTERNS["FR_PHONE"]})
        result = await detector.detect("Appelez au 06 12 34 56 78 ou +33612345678")
        assert len(result) == 2

    async def test_iban_with_validator_filters_wrong_checksum(self) -> None:
        detector = RegexDetector(
            patterns={"FR_IBAN": FR_PATTERNS["FR_IBAN"]},
            validators={"FR_IBAN": validate_iban},
        )
        text = "OK: FR1420041010050500013M02606, KO: FR1420041010050500013M02607"
        result = await detector.detect(text)
        kept = [d.text for d in result]
        assert "FR1420041010050500013M02606" in kept
        assert "FR1420041010050500013M02607" not in kept

    async def test_nir_with_validator(self) -> None:
        detector = RegexDetector(
            patterns={"FR_NIR": FR_PATTERNS["FR_NIR"]},
            validators={"FR_NIR": validate_nir},
        )
        text = "valide 1 84 12 76 451 089 46 et bidon 1 84 12 76 451 089 47"
        result = await detector.detect(text)
        kept = [d.text for d in result]
        assert any("46" in v and "089" in v for v in kept)
        assert not any("47" in v and v.endswith("47") for v in kept)

    async def test_siret(self) -> None:
        detector = RegexDetector(patterns={"FR_SIRET": FR_PATTERNS["FR_SIRET"]})
        result = await detector.detect("SIRET 552 120 222 00013 vu")
        assert len(result) == 1


# ---------------------------------------------------------------------------
# US
# ---------------------------------------------------------------------------


class TestUs:
    pytestmark = pytest.mark.asyncio

    async def test_ssn(self) -> None:
        detector = RegexDetector(patterns={"US_SSN": US_PATTERNS["US_SSN"]})
        result = await detector.detect("SSN 123-45-6789 recorded")
        assert len(result) == 1

    async def test_phone_accepts_common_formats(self) -> None:
        detector = RegexDetector(patterns={"US_PHONE": US_PATTERNS["US_PHONE"]})
        result = await detector.detect("(555) 123-4567 or +1 555-123-4567")
        assert len(result) == 2

    async def test_zip(self) -> None:
        detector = RegexDetector(patterns={"US_ZIP": US_PATTERNS["US_ZIP"]})
        result = await detector.detect("Address ZIP 94103 and 94103-1234")
        assert [d.text for d in result] == ["94103", "94103-1234"]


# ---------------------------------------------------------------------------
# EU
# ---------------------------------------------------------------------------


class TestEu:
    pytestmark = pytest.mark.asyncio

    async def test_iban_matches_multi_country_with_validator(self) -> None:
        detector = RegexDetector(
            patterns=EU_PATTERNS,
            validators={"IBAN": validate_iban},
        )
        text = "DE89 3704 0044 0532 0130 00 and GB82 WEST 1234 5698 7654 32"
        result = await detector.detect(text)
        assert len(result) == 2
        assert all(d.label == "IBAN" for d in result)
