from piighost.models import Detection, Entity, Span
from piighost.placeholder import HashPlaceholderFactory


def _entity(text: str, label: str = "PERSON") -> Entity:
    return Entity(
        detections=(
            Detection(
                text=text,
                label=label,
                position=Span(start_pos=0, end_pos=len(text)),
                confidence=0.9,
            ),
        )
    )


def test_empty_salt_matches_unsalted_legacy_format():
    """Empty salt must produce identical tokens to the pre-Sprint-5 factory (backward compat)."""
    unsalted = HashPlaceholderFactory()
    empty_salt = HashPlaceholderFactory(salt="")
    e = _entity("Patrick")
    assert unsalted.create([e])[e] == empty_salt.create([e])[e]


def test_non_empty_salt_changes_token():
    a = HashPlaceholderFactory(salt="client-a")
    b = HashPlaceholderFactory(salt="client-b")
    e = _entity("Patrick")
    assert a.create([e])[e] != b.create([e])[e]


def test_same_salt_produces_same_token():
    a1 = HashPlaceholderFactory(salt="client-a")
    a2 = HashPlaceholderFactory(salt="client-a")
    e = _entity("Patrick")
    assert a1.create([e])[e] == a2.create([e])[e]


def test_token_format_unchanged():
    factory = HashPlaceholderFactory(salt="client-a")
    e = _entity("Patrick")
    token = factory.create([e])[e]
    assert token.startswith("<PERSON:")
    assert token.endswith(">")
    assert len(token) == len("<PERSON:12345678>")  # label + 8-char digest


def test_salt_affects_only_hash_not_label_prefix():
    factory = HashPlaceholderFactory(salt="xyz")
    e = _entity("Patrick", label="EMAIL_ADDRESS")
    token = factory.create([e])[e]
    assert token.startswith("<EMAIL_ADDRESS:")
