---
icon: lucide/scan-search
tags:
  - Détecteur
  - Regex
---

# Utiliser les détecteurs prêts à l'emploi

`piighost` fournit des ensembles de patterns regex prêts à l'emploi pour les PII les plus courants : emails, IPs, URLs, clés d'API, numéros de téléphone, SSN, IBAN... Vous pouvez les utiliser tels quels, les combiner entre eux ou les étendre avec vos propres patterns.

Cette page en détaille les recettes d'usage. Pour le catalogue complet des labels disponibles (Communs, US, Europe), voir [Référence Détecteurs prêts à l'emploi](../reference/detectors.md).

---

## Une seule région

```python
from examples.detectors.common import create_detector

from piighost.anonymizer import Anonymizer
from piighost.linker.entity import ExactEntityLinker
from piighost.entity_resolver import MergeEntityConflictResolver
from piighost.pipeline import AnonymizationPipeline
from piighost.placeholder import LabelCounterPlaceholderFactory
from piighost.span_resolver import ConfidenceSpanConflictResolver

detector = create_detector()
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

anonymized, _ = await pipeline.anonymize("Écrivez-moi à alice@example.com, serveur 192.168.1.42.")
print(anonymized)
# Écrivez-moi à <<EMAIL:1>>, serveur <<IP_V4_1>>.
```

---

## Combiner commun + régional

```python
from examples.detectors.europe import create_full_detector

detector = create_full_detector()
# create_full_detector() fusionne les patterns communs + européens via CompositeDetector
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
    "IBAN FR7630006000011234567890189, email marie@exemple.fr, tel 06 12 34 56 78."
)
print(anonymized)
# IBAN <<EU_IBAN:1>>, email <<EMAIL:1>>, tel <<FR_PHONE:1>>.
```

---

## Sélectionner des patterns à la carte

```python
from piighost.detector import RegexDetector

from examples.detectors.common import PATTERNS as COMMON
from examples.detectors.europe import PATTERNS as EU

# Choisissez uniquement ce dont vous avez besoin
my_patterns = {
    "EMAIL": COMMON["EMAIL"],
    "URL": COMMON["URL"],
    "EU_IBAN": EU["EU_IBAN"],
    "FR_PHONE": EU["FR_PHONE"],
}

detector = RegexDetector(patterns=my_patterns)
```

---

## Combiner avec un NER (NER + regex)

```python
from gliner2 import GLiNER2

from piighost.detector import Gliner2Detector, CompositeDetector
from examples.detectors.common import create_detector as create_regex

model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")

ner_detector = Gliner2Detector(model=model, labels=["PERSON", "LOCATION"], threshold=0.5)
regex_detector = create_regex()  # emails, IPs, URLs, clés API, etc.
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

anonymized, _ = await pipeline.anonymize("Patrick à alice@example.com, IP 10.0.0.1.")
print(anonymized)
# <<PERSON:1>> à <<EMAIL:1>>, IP <<IP_V4_1>>.
```

---

## Ajouter vos propres patterns

Les ensembles de patterns sont de simples dictionnaires, étendez-les ou créez les vôtres :

```python
from examples.detectors.common import PATTERNS as COMMON

my_patterns = {
    **COMMON,
    "LICENSE_PLATE_FR": r"\b[A-Z]{2}-\d{3}-[A-Z]{2}\b",
    "CUSTOM_ID": r"\bCUST-\d{6}\b",
}
```

Voir aussi [Étendre PIIGhost](../extending.md) pour créer des classes de détecteur entièrement personnalisées.
