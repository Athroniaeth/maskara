"""Checksum validators for regex-based PII detections.

These callables complement :class:`~piighost.detector.RegexDetector` by
filtering regex matches that pass a syntactic pattern but fail a
domain-specific checksum (Luhn for credit cards, ISO 13616 mod-97 for
IBAN, the French NIR key).

Each validator returns ``True`` when the value is consistent with the
checksum, ``False`` otherwise. Empty or malformed input always returns
``False`` (never raises).
"""

from __future__ import annotations

import re


def validate_luhn(value: str) -> bool:
    """Validate a numeric sequence with the Luhn (mod-10) checksum.

    Used for credit cards, some national IDs, IMEIs. Spaces and dashes
    are ignored. Input must contain only digits once separators are
    stripped, and be at least 2 digits long.

    Args:
        value: The raw matched text (digits with optional spaces/dashes).

    Returns:
        ``True`` if the Luhn checksum is valid, ``False`` otherwise.

    Example:
        >>> validate_luhn("4111 1111 1111 1111")
        True
        >>> validate_luhn("4111 1111 1111 1112")
        False
    """
    digits = re.sub(r"[\s-]", "", value)
    if len(digits) < 2 or not digits.isdigit():
        return False

    total = 0
    parity = len(digits) % 2
    for i, char in enumerate(digits):
        digit = int(char)
        if i % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def validate_iban(value: str) -> bool:
    """Validate an IBAN using the ISO 13616 mod-97 checksum.

    Steps:
      1. Strip spaces, uppercase.
      2. Check overall length (15 – 34) and country/check-digit prefix.
      3. Move the first four characters to the end.
      4. Replace each letter with two digits (A = 10, B = 11, …, Z = 35).
      5. The integer modulo 97 must equal 1.

    Args:
        value: The raw matched text (IBAN with optional spaces).

    Returns:
        ``True`` if the IBAN passes the mod-97 check, ``False`` otherwise.

    Example:
        >>> validate_iban("FR14 2004 1010 0505 0001 3M02 606")
        True
        >>> validate_iban("FR14 2004 1010 0505 0001 3M02 607")
        False
    """
    iban = re.sub(r"\s", "", value).upper()
    if not 15 <= len(iban) <= 34:
        return False
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]+", iban):
        return False

    rearranged = iban[4:] + iban[:4]
    numeric = "".join(str(ord(c) - 55) if c.isalpha() else c for c in rearranged)
    try:
        return int(numeric) % 97 == 1
    except ValueError:
        return False


def validate_nir(value: str) -> bool:
    """Validate a French NIR (numéro de sécurité sociale) checksum.

    A NIR is 15 digits: a 13-digit body plus a 2-digit key. The key
    equals ``97 - (body % 97)``. Corsican departments use ``2A`` / ``2B``
    instead of a digit pair at positions 5-6; before the modulo they are
    replaced with ``19`` / ``18``.

    Args:
        value: The raw matched text (optional spaces/dots/dashes allowed).

    Returns:
        ``True`` if the NIR key matches the body, ``False`` otherwise.

    Example:
        >>> validate_nir("1 84 12 76 451 089 46")
        True
        >>> validate_nir("1 84 12 76 451 089 47")
        False
    """
    nir = re.sub(r"[\s.-]", "", value).upper()
    # sex(1) + YY(2) + MM(2) + dep(2 chars, digits or 2A/2B) + com(3) + order(3) + key(2)
    if not re.fullmatch(r"[12]\d{4}(?:2A|2B|\d{2})\d{8}", nir):
        return False

    body = nir[:13].replace("2A", "19").replace("2B", "18")
    try:
        key = int(nir[13:15])
        return 97 - (int(body) % 97) == key
    except ValueError:
        return False
