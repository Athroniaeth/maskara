from piighost.detector.patterns.iban import IBAN_PATTERN


def test_matches_french_iban():
    m = IBAN_PATTERN.regex.search("IBAN FR76 3000 6000 0112 3456 7890 189 please")
    assert m is not None


def test_matches_german_iban():
    m = IBAN_PATTERN.regex.search("DE89370400440532013000 on file")
    assert m is not None


def test_validator_accepts_valid_iban():
    assert IBAN_PATTERN.validator("DE89370400440532013000") is True


def test_validator_rejects_invalid_checksum():
    assert IBAN_PATTERN.validator("DE89370400440532013099") is False


def test_validator_rejects_too_short():
    assert IBAN_PATTERN.validator("DE12") is False


def test_label_is_iban_code():
    assert IBAN_PATTERN.label == "IBAN_CODE"
