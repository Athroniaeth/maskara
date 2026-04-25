"""Faker-based placeholder factory.

Generates realistic fake data as replacement tokens using the
`Faker <https://faker.readthedocs.io/>`_ library.  Each entity label
is mapped to a Faker provider method via a configurable strategies dict.
"""

import importlib.util
from collections.abc import Callable

from piighost.models import Entity

if importlib.util.find_spec("faker") is None:
    raise ImportError(
        "You must install faker to use FakerPlaceholderFactory, "
        "please install piighost[faker]"
    )

from faker import Faker

from piighost.placeholder import AnyPlaceholderFactory
from piighost.placeholder_tags import PreservesIdentityFaker

FakerFn = Callable[[Faker], str]
"""Signature for faker functions: ``(faker_instance) -> fake_value``."""


def fake_person(faker: Faker) -> str:
    return faker.name()


def fake_location(faker: Faker) -> str:
    return faker.city()


def fake_email(faker: Faker) -> str:
    return faker.email()


def fake_phone(faker: Faker) -> str:
    return faker.phone_number()


def fake_credit_card(faker: Faker) -> str:
    return faker.credit_card_number()


def fake_ssn(faker: Faker) -> str:
    return faker.ssn()


def fake_iban(faker: Faker) -> str:
    return faker.iban()


def fake_ip_address(faker: Faker) -> str:
    return faker.ipv4()


def fake_url(faker: Faker) -> str:
    return faker.url()


def fake_address(faker: Faker) -> str:
    return faker.address()


def fake_country(faker: Faker) -> str:
    return faker.country()


DEFAULT_STRATEGIES: dict[str, FakerFn] = {
    "person": fake_person,
    "location": fake_location,
    "email": fake_email,
    "phone": fake_phone,
    "phone_international": fake_phone,
    "us_phone": fake_phone,
    "fr_phone": fake_phone,
    "de_phone": fake_phone,
    "credit_card": fake_credit_card,
    "ssn": fake_ssn,
    "us_ssn": fake_ssn,
    "fr_ssn": fake_ssn,
    "iban": fake_iban,
    "eu_iban": fake_iban,
    "ip_address": fake_ip_address,
    "url": fake_url,
    "address": fake_address,
    "country": fake_country,
}


class FakerPlaceholderFactory(AnyPlaceholderFactory[PreservesIdentityFaker]):
    """Factory that generates realistic fake data as replacement tokens.

    Uses a configurable ``strategies`` mapping from label (lowercase) to
    a function ``(Faker) -> str``.  Labels not present in the mapping
    produce a generic ``<LABEL>`` redacted token.

    The same entity always produces the same fake value within a single
    ``create()`` call (deterministic per entity via seeding).

    Args:
        faker: Optional pre-configured ``Faker`` instance.  Defaults to
            ``Faker()`` with no locale.
        strategies: Optional dict mapping lowercase labels to faker
            functions.  Replaces the built-in defaults when provided.
        seed: Optional seed for reproducible output.

    Example:
        >>> from piighost.models import Detection, Entity, Span
        >>> factory = FakerPlaceholderFactory(seed=42)
        >>> e = Entity(detections=(Detection(text="Patrick", label="PERSON", position=Span(0, 7), confidence=0.9),))
        >>> token = factory.create([e])[e]
        >>> isinstance(token, str) and len(token) > 0
        True
    """

    _faker: Faker
    _strategies: dict[str, FakerFn]

    def __init__(
        self,
        faker: Faker | None = None,
        strategies: dict[str, FakerFn] | None = None,
        seed: int | None = None,
    ) -> None:
        self._faker = faker or Faker()

        if seed is not None:
            self._faker.seed_instance(seed)

        if strategies is None:
            self._strategies = dict(DEFAULT_STRATEGIES)
        else:
            self._strategies = {k.lower(): v for k, v in strategies.items()}

    def create(self, entities: list[Entity]) -> dict[Entity, str]:
        """Create fake replacement tokens for all entities.

        Each entity is mapped to a fake value via its label. Entities
        sharing the same canonical text and label get the same fake value.

        Args:
            entities: The entities to create tokens for.

        Returns:
            A dict mapping each entity to a realistic fake value.
        """
        cache: dict[tuple[str, str], str] = {}
        result: dict[Entity, str] = {}

        for entity in entities:
            canonical = entity.detections[0].text.lower()
            label_lower = entity.label.lower()
            key = (canonical, label_lower)

            if key not in cache:
                cache[key] = self._fake(label_lower)

            result[entity] = cache[key]

        return result

    def _fake(self, label_lower: str) -> str:
        if label_lower in self._strategies:
            return self._strategies[label_lower](self._faker)
        return f"<{label_lower.upper()}>"
