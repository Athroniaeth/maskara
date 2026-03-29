---
icon: lucide/puzzle
---

# Etendre PIIGhost

PIIGhost est concu autour de **protocoles** (typage structurel Python). Chaque etape du pipeline est un point d'injection ou vous pouvez brancher votre propre implementation sans toucher au reste du code.

```mermaid
flowchart LR
    A[AnonymizationPipeline] -->|inject| B[AnyDetector]
    A -->|inject| C[AnySpanConflictResolver]
    A -->|inject| D[AnyEntityLinker]
    A -->|inject| E[AnyEntityConflictResolver]
    A -->|inject| F[AnyAnonymizer]
    F -->|inject| G[AnyPlaceholderFactory]
```

Aucune classe de base a heriter. Il suffit d'implementer la methode requise Python verifie la compatibilite au moment de l'appel.

---

## Creer un `AnyDetector` personnalise

**Quand l'utiliser** : remplacer GLiNER2 par spaCy, un appel API distant, une liste blanche, etc.

### Protocole

```python
class AnyDetector(Protocol):
    async def detect(self, text: str) -> list[Detection]: ...
```

### Exemple Detecteur spaCy

```python
import spacy
from piighost.models import Detection, Span

class SpacyDetector:
    """Detecteur NER base sur spaCy."""

    def __init__(self, model_name: str = "fr_core_news_sm"):
        self._nlp = spacy.load(model_name)

    async def detect(self, text: str) -> list[Detection]:
        doc = self._nlp(text)
        return [
            Detection(
                text=ent.text,
                label=ent.label_,
                position=Span(start_pos=ent.start_char, end_pos=ent.end_char),
                confidence=1.0,
            )
            for ent in doc.ents
        ]
```

### Exemple Detecteur par liste blanche

```python
import re
from piighost.models import Detection, Span

class AllowlistDetector:
    """Detecte les entites d'une liste fixe (utile pour les tests ou les donnees structurees)."""

    def __init__(self, allowlist: dict[str, str]):
        # {"Patrick Dupont": "PERSON", "Paris": "LOCATION"}
        self._allowlist = allowlist

    async def detect(self, text: str) -> list[Detection]:
        detections = []
        for fragment, label in self._allowlist.items():
            for match in re.finditer(re.escape(fragment), text):
                detections.append(Detection(
                    text=match.group(),
                    label=label,
                    position=Span(start_pos=match.start(), end_pos=match.end()),
                    confidence=1.0,
                ))
        return detections
```

### Utilisation

```python
from piighost.pipeline import AnonymizationPipeline

pipeline = AnonymizationPipeline(
    detector=SpacyDetector("fr_core_news_sm"),
    ...,
)
```

---

## Creer un `AnySpanConflictResolver` personnalise

**Quand l'utiliser** : strategie differente pour gerer les detections qui se chevauchent (ex: preferer les spans les plus longs).

### Protocole

```python
class AnySpanConflictResolver(Protocol):
    def resolve(self, detections: list[Detection]) -> list[Detection]: ...
```

---

## Creer un `AnyEntityLinker` personnalise

**Quand l'utiliser** : logique differente pour grouper les detections en entites (ex: correspondance floue, variantes phonetiques).

### Protocole

```python
class AnyEntityLinker(Protocol):
    def link(self, text: str, detections: list[Detection]) -> list[Entity]: ...
```

---

## Creer un `AnyEntityConflictResolver` personnalise

**Quand l'utiliser** : strategie differente pour fusionner les entites qui referent au meme PII.

### Protocole

```python
class AnyEntityConflictResolver(Protocol):
    def resolve(self, entities: list[Entity]) -> list[Entity]: ...
```

Implementations fournies :

- `MergeEntityConflictResolver` algorithme union-find fusionnant les entites avec des detections communes
- `FuzzyEntityConflictResolver` fusionne les entites avec un texte canonique similaire via similarite Jaro-Winkler

---

## Creer un `AnyPlaceholderFactory` personnalise

**Quand l'utiliser** : tags UUID pour l'anonymat total, format personnalise, integration avec un systeme de tokens externe.

### Protocole

```python
class AnyPlaceholderFactory(Protocol):
    def create(self, entities: list[Entity]) -> dict[Entity, str]: ...
```

### Exemple Tags UUID

```python
import uuid
from piighost.models import Entity

class UUIDPlaceholderFactory:
    """Genere des tags UUID opaques, ex: <<a3f2-1b4c>>."""

    def create(self, entities: list[Entity]) -> dict[Entity, str]:
        result: dict[Entity, str] = {}
        seen: dict[str, str] = {}

        for entity in entities:
            canonical = entity.detections[0].text.lower()
            if canonical not in seen:
                seen[canonical] = f"<<{uuid.uuid4().hex[:8]}>>"
            result[entity] = seen[canonical]

        return result
```

### Exemple Format personnalise

```python
from collections import defaultdict
from piighost.models import Entity

class BracketPlaceholderFactory:
    """Genere des tags au format [PERSON:1], [LOCATION:2], etc."""

    def create(self, entities: list[Entity]) -> dict[Entity, str]:
        result: dict[Entity, str] = {}
        counters: dict[str, int] = defaultdict(int)

        for entity in entities:
            label = entity.label
            counters[label] += 1
            result[entity] = f"[{label}:{counters[label]}]"

        return result
```

### Utilisation

```python
from piighost.anonymizer import Anonymizer

anonymizer = Anonymizer(ph_factory=UUIDPlaceholderFactory())
```

---

## Composition complete

Tous les composants sont independants et peuvent etre combines librement :

```python
from piighost.anonymizer import Anonymizer
from piighost.conversation_pipeline import ConversationAnonymizationPipeline
from piighost.linker.entity import ExactEntityLinker
from piighost.entity_resolver import FuzzyEntityConflictResolver
from piighost.middleware import PIIAnonymizationMiddleware
from piighost.span_resolver import ConfidenceSpanConflictResolver

pipeline = ConversationAnonymizationPipeline(
    detector=SpacyDetector("fr_core_news_sm"),  # Votre detecteur
    span_resolver=ConfidenceSpanConflictResolver(),  # Ou votre resolver
    entity_linker=ExactEntityLinker(),  # Ou votre linker
    entity_resolver=FuzzyEntityConflictResolver(),  # Fusion floue
    anonymizer=Anonymizer(UUIDPlaceholderFactory()),  # Tags UUID opaques
)

middleware = PIIAnonymizationMiddleware(pipeline=pipeline)
```

---

## Ecrire des tests pour ses composants

Les protocoles facilitent les tests unitaires. Utilisez `ExactMatchDetector` pour des tests deterministes :

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
    pipeline = AnonymizationPipeline(
        detector=ExactMatchDetector([("Alice", "PERSON")]),
        span_resolver=ConfidenceSpanConflictResolver(),
        entity_linker=ExactEntityLinker(),
        entity_resolver=MergeEntityConflictResolver(),
        anonymizer=Anonymizer(CounterPlaceholderFactory()),
    )

    anonymized, entities = await pipeline.anonymize("Alice habite a Lyon.")
    assert "<<PERSON_1>>" in anonymized
    assert "Alice" not in anonymized
```

!!! tip "ExactMatchDetector en CI"
    Utilisez toujours `ExactMatchDetector` (ou equivalent) en CI pour eviter de charger le modele GLiNER2 (~500 Mo) lors des tests automatises.
