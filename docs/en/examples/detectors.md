---
icon: lucide/scan-search
tags:
  - Detector
  - Regex
---

# Pre-built detectors usage

`piighost` ships ready-to-use regex pattern sets for the most common PII: emails, IPs, URLs, API keys, phone numbers, SSNs, IBANs... You can use them as-is, combine them together, or extend them with your own patterns.

This page walks through the usage recipes. For the full catalog of available labels (Common, US, Europe), see [Reference Pre-built detectors](../reference/detectors.md).

---

## Single region

```python
from examples.detectors.common import create_detector

from piighost.anonymizer import Anonymizer
from piighost.linker.entity import ExactEntityLinker
from piighost.resolver import MergeEntityConflictResolver, ConfidenceSpanConflictResolver
from piighost.pipeline import AnonymizationPipeline
from piighost.placeholder import LabelCounterPlaceholderFactory

detector = create_detector()

entity_linker = ExactEntityLinker()
entity_resolver = MergeEntityConflictResolver()
span_resolver = ConfidenceSpanConflictResolver()

ph_factory = LabelCounterPlaceholderFactory()
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
# Email me at <<EMAIL:1>>, server <<IP_V4_1>>.
```

---

## Combine common + regional patterns

```python
from examples.detectors.us import create_full_detector

detector = create_full_detector()
# create_full_detector() merges common + US patterns via CompositeDetector
span_resolver = ConfidenceSpanConflictResolver()
entity_linker = ExactEntityLinker()
entity_resolver = MergeEntityConflictResolver()
anonymizer = Anonymizer(LabelCounterPlaceholderFactory())

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
# SSN <<US_SSN:1>>, email <<EMAIL:1>>, card <<CREDIT_CARD:1>>.
```

---

## Mix-and-match with `PATTERNS` dicts

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

---

## Combine with an NER (NER + regex)

```python
from gliner2 import GLiNER2

from piighost.detector import CompositeDetector
from piighost.detector.gliner2 import Gliner2Detector
from examples.detectors.common import create_detector as create_regex

model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")

ner_detector = Gliner2Detector(model=model, labels=["PERSON", "LOCATION"], threshold=0.5)
regex_detector = create_regex()  # emails, IPs, URLs, API keys, etc.
detector = CompositeDetector(detectors=[ner_detector, regex_detector])

span_resolver = ConfidenceSpanConflictResolver()
entity_linker = ExactEntityLinker()
entity_resolver = MergeEntityConflictResolver()
anonymizer = Anonymizer(LabelCounterPlaceholderFactory())

pipeline = AnonymizationPipeline(
    detector=detector,
    span_resolver=span_resolver,
    entity_linker=entity_linker,
    entity_resolver=entity_resolver,
    anonymizer=anonymizer,
)

anonymized, _ = await pipeline.anonymize("Patrick at alice@example.com, IP 10.0.0.1.")
print(anonymized)
# <<PERSON:1>> at <<EMAIL:1>>, IP <<IP_V4_1>>.
```

---

## Adding your own patterns

The pattern sets are plain dictionaries, extend them or create your own:

```python
from examples.detectors.common import PATTERNS as COMMON

my_patterns = {
    **COMMON,
    "LICENSE_PLATE_FR": r"\b[A-Z]{2}-\d{3}-[A-Z]{2}\b",
    "CUSTOM_ID": r"\bCUST-\d{6}\b",
}
```

See also [Extending PIIGhost](../extending.md) for creating fully custom detector classes.
