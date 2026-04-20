from piighost.detector.patterns.email import EMAIL_PATTERN


def test_matches_simple_email():
    m = EMAIL_PATTERN.regex.search("contact alice@example.com today")
    assert m is not None
    assert m.group(0) == "alice@example.com"


def test_matches_email_with_subdomain():
    m = EMAIL_PATTERN.regex.search("Send to bob.smith@mail.company.co.uk please")
    assert m is not None
    assert m.group(0) == "bob.smith@mail.company.co.uk"


def test_matches_plus_addressing():
    m = EMAIL_PATTERN.regex.search("alice+filter@example.com")
    assert m is not None
    assert m.group(0) == "alice+filter@example.com"


def test_does_not_match_plain_text():
    assert EMAIL_PATTERN.regex.search("no email here") is None


def test_label_is_email_address():
    assert EMAIL_PATTERN.label == "EMAIL_ADDRESS"
