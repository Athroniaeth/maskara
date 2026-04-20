from piighost.detector.patterns.credit_card import CREDIT_CARD_PATTERN


def test_matches_visa():
    m = CREDIT_CARD_PATTERN.regex.search("pay 4532 0151 1283 0366 now")
    assert m is not None


def test_matches_no_separators():
    m = CREDIT_CARD_PATTERN.regex.search("card 4532015112830366")
    assert m is not None


def test_validator_accepts_valid_luhn():
    assert CREDIT_CARD_PATTERN.validator("4532 0151 1283 0366") is True


def test_validator_rejects_invalid_luhn():
    assert CREDIT_CARD_PATTERN.validator("4532 0151 1283 0367") is False


def test_validator_rejects_too_short():
    assert CREDIT_CARD_PATTERN.validator("1234567") is False


def test_validator_accepts_amex_15_digits():
    assert CREDIT_CARD_PATTERN.validator("378282246310005") is True


def test_label_is_credit_card():
    assert CREDIT_CARD_PATTERN.label == "CREDIT_CARD"
