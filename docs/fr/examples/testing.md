---
icon: lucide/test-tube
tags:
  - Tests
---

# Tests

Comment tester unitairement les pipelines PIIGhost et les composants personnalisés. L'approche recommandée utilise `ExactMatchDetector` pour éviter de télécharger un modèle NER en CI, mais les patterns présentés s'appliquent à n'importe quel détecteur.

---

## Détection déterministe avec `ExactMatchDetector`

`ExactMatchDetector` prend une liste de paires `(texte, label)` et trouve leurs occurrences par frontière de mot. Pas de modèle, pas de réseau, sortie entièrement prédictible.

```python
from piighost.anonymizer import Anonymizer
from piighost.detector import ExactMatchDetector
from piighost.linker.entity import ExactEntityLinker
from piighost.entity_resolver import MergeEntityConflictResolver
from piighost.pipeline import AnonymizationPipeline
from piighost.placeholder import CounterPlaceholderFactory
from piighost.span_resolver import ConfidenceSpanConflictResolver

detector = ExactMatchDetector([("Patrick", "PERSON"), ("Paris", "LOCATION")])
span_resolver = ConfidenceSpanConflictResolver()
entity_linker = ExactEntityLinker()
entity_resolver = MergeEntityConflictResolver()
anonymizer = Anonymizer(CounterPlaceholderFactory())

pipeline = AnonymizationPipeline(
    detector=detector,
    span_resolver=span_resolver,
    entity_linker=entity_linker,
    entity_resolver=entity_resolver,
    anonymizer=anonymizer,
)

anonymized, entities = await pipeline.anonymize("Patrick habite à Paris.")
assert anonymized == "<<PERSON_1>> habite à <<LOCATION_1>>."
```

---

## Pattern pytest

```python
import pytest
from piighost.anonymizer import Anonymizer
from piighost.detector import ExactMatchDetector
from piighost.linker.entity import ExactEntityLinker
from piighost.entity_resolver import MergeEntityConflictResolver
from piighost.pipeline import AnonymizationPipeline
from piighost.placeholder import CounterPlaceholderFactory
from piighost.span_resolver import ConfidenceSpanConflictResolver


@pytest.mark.asyncio
async def test_my_pipeline():
    detector = ExactMatchDetector([("Alice", "PERSON")])
    span_resolver = ConfidenceSpanConflictResolver()
    entity_linker = ExactEntityLinker()
    entity_resolver = MergeEntityConflictResolver()
    anonymizer = Anonymizer(CounterPlaceholderFactory())

    pipeline = AnonymizationPipeline(
        detector=detector,
        span_resolver=span_resolver,
        entity_linker=entity_linker,
        entity_resolver=entity_resolver,
        anonymizer=anonymizer,
    )

    anonymized, entities = await pipeline.anonymize("Alice habite à Lyon.")
    assert "<<PERSON_1>>" in anonymized
    assert "Alice" not in anonymized
```

!!! tip "ExactMatchDetector en CI"
    Utilisez toujours `ExactMatchDetector` (ou équivalent) en CI pour éviter de charger un modèle NER lors des tests automatisés.

---

## Tester des composants personnalisés

Chaque étape du pipeline est un protocole, ce qui rend chaque composant substituable isolément pour les tests. Voir [Étendre PIIGhost](../extending.md) pour les définitions des protocoles, puis injectez votre composant personnalisé aux côtés de `ExactMatchDetector` ci-dessus.
