---
icon: lucide/code
---

# Usage basique

Cette page presente les usages fondamentaux de la bibliotheque sans integration LangChain.

---

## Anonymisation simple avec le pipeline

```python
import asyncio

from gliner2 import GLiNER2

from piighost.anonymizer import Anonymizer
from piighost.detector import Gliner2Detector
from piighost.linker.entity import ExactEntityLinker
from piighost.entity_resolver import MergeEntityConflictResolver
from piighost.pipeline import AnonymizationPipeline
from piighost.placeholder import CounterPlaceholderFactory
from piighost.span_resolver import ConfidenceSpanConflictResolver

# Charger le modele GLiNER2
model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")

# Construire le pipeline
pipeline = AnonymizationPipeline(
    detector=Gliner2Detector(model=model, labels=["PERSON", "LOCATION"], threshold=0.5),
    span_resolver=ConfidenceSpanConflictResolver(),
    entity_linker=ExactEntityLinker(),
    entity_resolver=MergeEntityConflictResolver(),
    anonymizer=Anonymizer(CounterPlaceholderFactory()),
)


async def main():
    # Anonymiser un texte
    anonymized, entities = await pipeline.anonymize(
        "Patrick habite a Paris. Patrick aime Paris.",
    )
    print(anonymized)
    # <<PERSON_1>> habite a <<LOCATION_1>>. <<PERSON_1>> aime <<LOCATION_1>>.

    # Desanonymiser
    original, _ = await pipeline.deanonymize(anonymized)
    print(original)
    # Patrick habite a Paris. Patrick aime Paris.


asyncio.run(main())
```

---

## Inspection des entites

Le pipeline retourne les entites utilisees pour l'anonymisation :

```python
async def main():
    anonymized, entities = await pipeline.anonymize(
        "Marie Dupont travaille chez Acme Corp a Lyon.",
    )
    print(anonymized)
    # <<PERSON_1>> travaille chez <<ORGANIZATION_1>> a <<LOCATION_1>>.

    for entity in entities:
        canonical = entity.detections[0].text
        print(f"'{canonical}' [{entity.label}] {len(entity.detections)} detection(s)")

asyncio.run(main())
```

---

## Pipeline conversationnel avec memoire

Pour les scenarios multi-messages (conversation), `ConversationAnonymizationPipeline` accumule les entites entre les messages et fournit desanonymisation/reanonymisation par remplacement de chaine.

```python
import asyncio

from piighost.anonymizer import Anonymizer
from piighost.conversation_memory import ConversationMemory
from piighost.conversation_pipeline import ConversationAnonymizationPipeline
from piighost.detector import Gliner2Detector
from piighost.linker.entity import ExactEntityLinker
from piighost.entity_resolver import MergeEntityConflictResolver
from piighost.placeholder import CounterPlaceholderFactory
from piighost.span_resolver import ConfidenceSpanConflictResolver

conv_pipeline = ConversationAnonymizationPipeline(
    detector=Gliner2Detector(model=model, labels=["PERSON", "LOCATION"], threshold=0.5),
    span_resolver=ConfidenceSpanConflictResolver(),
    entity_linker=ExactEntityLinker(),
    entity_resolver=MergeEntityConflictResolver(),
    anonymizer=Anonymizer(CounterPlaceholderFactory()),
    memory=ConversationMemory(),
)


async def conversation():
    # Premier message : detection NER + mise en cache
    r1, _ = await conv_pipeline.anonymize("Patrick est a Paris.")
    print(r1)
    # <<PERSON_1>> est a <<LOCATION_1>>.

    # Meme texte : cache hit (pas de second appel NER)
    r2, _ = await conv_pipeline.anonymize("Patrick est a Paris.")
    print(r2)
    # <<PERSON_1>> est a <<LOCATION_1>>.

    # Desanonymiser n'importe quelle chaine avec tokens (async)
    restored = await conv_pipeline.deanonymize_with_ent("Bonjour, <<PERSON_1>> !")
    print(restored)
    # Bonjour, Patrick !

    # Reanonymiser (original → token)
    reanon = conv_pipeline.anonymize_with_ent("Reponse pour Patrick a Paris")
    print(reanon)
    # Reponse pour <<PERSON_1>> a <<LOCATION_1>>


asyncio.run(conversation())
```

---

## Differentes placeholder factories

Par defaut, `CounterPlaceholderFactory` genere des tags `<<LABEL_N>>`. Vous pouvez changer de strategie :

```python
from piighost.placeholder import HashPlaceholderFactory, RedactPlaceholderFactory

# Hash : tags opaques deterministes
pipeline_hash = AnonymizationPipeline(
    ...,
    anonymizer=Anonymizer(HashPlaceholderFactory()),
)
# Produit : <PERSON:a1b2c3d4>

# Redact : toutes les entites recoivent <LABEL> (pas de compteur)
pipeline_redact = AnonymizationPipeline(
    ...,
    anonymizer=Anonymizer(RedactPlaceholderFactory()),
)
# Produit : <PERSON>
```

---

## Tester sans charger GLiNER2

En test, utilisez `ExactMatchDetector` pour eviter de telecharger le modele :

```python
from piighost.anonymizer import Anonymizer
from piighost.detector import ExactMatchDetector
from piighost.linker.entity import ExactEntityLinker
from piighost.entity_resolver import MergeEntityConflictResolver
from piighost.pipeline import AnonymizationPipeline
from piighost.placeholder import CounterPlaceholderFactory
from piighost.span_resolver import ConfidenceSpanConflictResolver

pipeline = AnonymizationPipeline(
    detector=ExactMatchDetector([("Patrick", "PERSON"), ("Paris", "LOCATION")]),
    span_resolver=ConfidenceSpanConflictResolver(),
    entity_linker=ExactEntityLinker(),
    entity_resolver=MergeEntityConflictResolver(),
    anonymizer=Anonymizer(CounterPlaceholderFactory()),
)

# Detection deterministe sans modele NER
anonymized, entities = await pipeline.anonymize("Patrick habite a Paris.")
assert anonymized == "<<PERSON_1>> habite a <<LOCATION_1>>."
```

Voir aussi la [page Etendre PIIGhost](../extending.md) pour creer d'autres composants personnalises.
