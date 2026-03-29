---
icon: lucide/scan-search
---

# Pre-built regex detectors

PIIGhost ships with ready-to-use `RegexDetector` pattern sets in `examples/detectors/`. Each file exposes a `PATTERNS` dictionary and a `create_detector()` helper so you can plug them in with zero configuration.

---

## Available pattern sets

### Common (universal)

**File:** `examples/detectors/common.py`

| Label | Example match |
|-------|---------------|
| `EMAIL` | `alice@example.com` |
| `IP_V4` | `192.168.1.42` |
| `IP_V6` | `2001:0db8:85a3::8a2e:0370:7334` |
| `URL` | `https://api.example.com/v1` |
| `CREDIT_CARD` | `4532-1234-5678-9012` |
| `PHONE_INTERNATIONAL` | `+33 6 12 34 56 78` |
| `OPENAI_API_KEY` | `sk-proj-abc123xyz456789ABCDEF` |
| `AWS_ACCESS_KEY` | `AKIAIOSFODNN7EXAMPLE` |
| `GITHUB_TOKEN` | `ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ...` |
| `STRIPE_KEY` | `sk_live_ABCDEFGHIJKLMNOPQR...` |

### US-specific

**File:** `examples/detectors/us.py`

| Label | Example match | Format |
|-------|---------------|--------|
| `US_SSN` | `123-45-6789` | XXX-XX-XXXX |
| `US_PHONE` | `(555) 867-5309` | With optional +1 prefix |
| `US_PASSPORT` | `C12345678` | Letter + 8 digits |
| `US_ZIP_CODE` | `90210-1234` | ZIP or ZIP+4 |
| `US_EIN` | `12-3456789` | Employer Identification Number |
| `US_BANK_ROUTING` | `021000021` | 9-digit ABA routing number |

### Europe

**File:** `examples/detectors/europe.py`

| Label | Example match | Country |
|-------|---------------|---------|
| `EU_IBAN` | `FR7630006000011234567890189` | Pan-EU |
| `EU_VAT` | `FR12345678901` | Pan-EU |
| `FR_SSN` | `185017512345612` | France (INSEE) |
| `FR_PHONE` | `06 12 34 56 78` | France |
| `FR_ZIP` | `75001` | France |
| `DE_PHONE` | `030 1234567` | Germany |
| `DE_ZIP` | `10115` | Germany |
| `UK_NINO` | `AB123456C` | UK (National Insurance) |
| `UK_NHS` | `943-476-5919` | UK (NHS number) |
| `UK_POSTCODE` | `SW1A 1AA` | UK |

---

## Quick start

### Single region

```python
from examples.detectors.common import create_detector

from piighost.anonymizer import Anonymizer
from piighost.linker.entity import ExactEntityLinker
from piighost.resolver import MergeEntityConflictResolver, ConfidenceSpanConflictResolver
from piighost.pipeline import AnonymizationPipeline
from piighost.placeholder import CounterPlaceholderFactory

detector = create_detector()

entity_linker = ExactEntityLinker()
entity_resolver = MergeEntityConflictResolver()
span_resolver = ConfidenceSpanConflictResolver()

ph_factory = CounterPlaceholderFactory()
anonymizer = Anonymizer(ph_factory=ph_factory)

pipeline = AnonymizationPipeline(
    detector=detector,
    span_resolver=span_resolver,
    entity_linker=entity_linker,
    entity_resolver=entity_resolver,
    anonymizer=anonymizer,
)

anonymized, _ = await pipeline.anonymize("Email me at alice@example.com, server 192.168.1.42.")
print(anonymized)
# Email me at <<EMAIL_1>>, server <<IP_V4_1>>.
```

### Combine common + regional patterns

```python
from examples.detectors.us import create_full_detector

detector = create_full_detector()
# create_full_detector() merges common + US patterns via CompositeDetector

entity_linker = ExactEntityLinker()
entity_resolver = MergeEntityConflictResolver()
span_resolver = ConfidenceSpanConflictResolver()

ph_factory = CounterPlaceholderFactory()
anonymizer = Anonymizer(ph_factory=ph_factory)

pipeline = AnonymizationPipeline(
    detector=detector,
    span_resolver=span_resolver,
    entity_linker=entity_linker,
    entity_resolver=entity_resolver,
    anonymizer=anonymizer,
)

anonymized, _ = await pipeline.anonymize(
    "SSN 123-45-6789, email john@example.com, card 4532-1234-5678-9012."
)
print(anonymized)
# SSN <<US_SSN_1>>, email <<EMAIL_1>>, card <<CREDIT_CARD_1>>.
```

### Mix-and-match with `PATTERNS` dicts

```python
from piighost.detector import RegexDetector

from examples.detectors.common import PATTERNS as COMMON
from examples.detectors.europe import PATTERNS as EU

# Cherry-pick only what you need
my_patterns = {
    "EMAIL": COMMON["EMAIL"],
    "URL": COMMON["URL"],
    "EU_IBAN": EU["EU_IBAN"],
    "FR_PHONE": EU["FR_PHONE"],
}

detector = RegexDetector(patterns=my_patterns)
```

### Combine with GLiNER2 (NER + regex)

```python
from gliner2 import GLiNER2

from piighost.detector import CompositeDetector
from piighost.detector.gliner2 import Gliner2Detector
from examples.detectors.common import create_detector as create_regex

model = GLiNER2.from_pretrained("urchade/gliner_multi-v2.1")

detector = CompositeDetector(
    detectors=[
        Gliner2Detector(model=model, labels=["PERSON", "LOCATION"], threshold=0.5),
        create_regex(),  # emails, IPs, URLs, API keys, etc.
    ]
)

entity_linker = ExactEntityLinker()
entity_resolver = MergeEntityConflictResolver()
span_resolver = ConfidenceSpanConflictResolver()

ph_factory = CounterPlaceholderFactory()
anonymizer = Anonymizer(ph_factory=ph_factory)

pipeline = AnonymizationPipeline(
    detector=detector,
    span_resolver=span_resolver,
    entity_linker=entity_linker,
    entity_resolver=entity_resolver,
    anonymizer=anonymizer,
)

anonymized, _ = await pipeline.anonymize("Patrick at alice@example.com, IP 10.0.0.1.")
print(anonymized)
# <<PERSON_1>> at <<EMAIL_1>>, IP <<IP_V4_1>>.
```

---

## Adding your own patterns

The pattern sets are plain dictionaries extend them or create your own:

```python
from examples.detectors.common import PATTERNS as COMMON

my_patterns = {
    **COMMON,
    "LICENSE_PLATE_FR": r"\b[A-Z]{2}-\d{3}-[A-Z]{2}\b",
    "CUSTOM_ID": r"\bCUST-\d{6}\b",
}
```

See also [Extending PIIGhost](../extending.md) for creating fully custom detector classes.
