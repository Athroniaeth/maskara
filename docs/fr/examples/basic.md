---
icon: lucide/code
---

# Usage basique

Cette page presente les usages fondamentaux de la bibliotheque sans integration LangChain.

---

## Anonymisation simple avec le pipeline

```python title="pipeline.py" linenums="1" hl_lines="23-30"
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

# Instancier chaque composant
detector = Gliner2Detector(model=model, labels=["PERSON", "LOCATION"], threshold=0.5)
span_resolver = ConfidenceSpanConflictResolver()
entity_linker = ExactEntityLinker()
entity_resolver = MergeEntityConflictResolver()
anonymizer = Anonymizer(CounterPlaceholderFactory())

# Assembler le pipeline
pipeline = AnonymizationPipeline(
    detector=detector,  # (1)!
    span_resolver=span_resolver,  # (2)!
    entity_linker=entity_linker,  # (3)!
    entity_resolver=entity_resolver,  # (4)!
    anonymizer=anonymizer,  # (5)!
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

1. **Détecter** : trouve les PII candidates dans le texte via un détecteur NER (ici GLiNER2, interchangeable avec spaCy ou Transformers).
2. **Résoudre les spans** : arbitre les chevauchements lorsque plusieurs détecteurs rapportent des positions qui se recouvrent.
3. **Lier les entités** : regroupe les occurrences d'une même PII (variantes de casse, typos, mentions partielles).
4. **Résoudre les entités** : fusionne les groupes qui partagent une mention entre détecteurs.
5. **Anonymiser** : remplace chaque entité par un placeholder produit par la factory (ici `<<PERSON_1>>`{ .placeholder }, `<<LOCATION_1>>`{ .placeholder }…).

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

Pour les scénarios multi-messages (conversation), `ThreadAnonymizationPipeline` accumule les entités entre les messages et fournit désanonymisation/réanonymisation par remplacement de chaîne.

```python
import asyncio

from piighost.anonymizer import Anonymizer
from piighost.pipeline import ThreadAnonymizationPipeline
from piighost.detector import Gliner2Detector
from piighost.linker.entity import ExactEntityLinker
from piighost.entity_resolver import MergeEntityConflictResolver
from piighost.placeholder import CounterPlaceholderFactory
from piighost.span_resolver import ConfidenceSpanConflictResolver

detector = Gliner2Detector(model=model, labels=["PERSON", "LOCATION"], threshold=0.5)
span_resolver = ConfidenceSpanConflictResolver()
entity_linker = ExactEntityLinker()
entity_resolver = MergeEntityConflictResolver()
anonymizer = Anonymizer(CounterPlaceholderFactory())

conv_pipeline = ThreadAnonymizationPipeline(
    detector=detector,
    span_resolver=span_resolver,
    entity_linker=entity_linker,
    entity_resolver=entity_resolver,
    anonymizer=anonymizer,
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
from piighost.placeholder import LabeledHashPlaceholderFactory, RedactPlaceholderFactory

# Hash : tags opaques deterministes
pipeline_hash = AnonymizationPipeline(
    ...,
    anonymizer=Anonymizer(LabeledHashPlaceholderFactory()),
)
# Produit : <<PERSON:a1b2c3d4>>

# Redact : toutes les entites recoivent <<LABEL>> (pas de compteur)
pipeline_redact = AnonymizationPipeline(
    ...,
    anonymizer=Anonymizer(RedactPlaceholderFactory()),
)
# Produit : <<PERSON>>
```

---

Pour tester unitairement les pipelines sans charger un modèle NER, voir le guide [Tests](testing.md).

Voir aussi la [page Étendre PIIGhost](../extending.md) pour créer des composants personnalisés.
