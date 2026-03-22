---
icon: lucide/code
---

# Usage basique

Cette page présente les usages fondamentaux de la bibliothèque sans intégration LangChain.

---

## Anonymisation simple

```python
from gliner2 import GLiNER2
from piighost.anonymizer import Anonymizer, GlinerDetector

# Charger le modèle GLiNER2
model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")

# Créer le détecteur avec seuil de confiance
detector = GlinerDetector(model=model, threshold=0.5, flat_ner=True)

# Créer l'anonymiseur
anonymizer = Anonymizer(detector=detector)

# Anonymiser un texte
result = anonymizer.anonymize(
    "Patrick habite à Paris. Patrick aime Paris.",
    labels=["PERSON", "LOCATION"],
)

print(result.anonymized_text)
# <<PERSON_1>> habite à <<LOCATION_1>>. <<PERSON_1>> aime <<LOCATION_1>>.

print(result.original_text)
# Patrick habite à Paris. Patrick aime Paris.

# Inspecter les placeholders créés
for placeholder in result.placeholders:
    print(f"{placeholder.original!r} → {placeholder.replacement!r} ({placeholder.label})")
# 'Patrick' → '<<PERSON_1>>' (PERSON)
# 'Paris' → '<<LOCATION_1>>' (LOCATION)
```

---

## Désanonymisation

```python
# Restaurer le texte original depuis l'AnonymizationResult
original = anonymizer.deanonymize(result)
print(original)
# Patrick habite à Paris. Patrick aime Paris.
```

!!! note "Span-based"
    La désanonymisation de l'`Anonymizer` est basée sur des **spans inverses** précalculés. Elle est précise au caractère près mais nécessite de conserver l'objet `AnonymizationResult`.

---

## Plusieurs types d'entités

```python
result = anonymizer.anonymize(
    "Marie Dupont travaille chez Acme Corp à Lyon.",
    labels=["PERSON", "ORGANIZATION", "LOCATION"],
)

print(result.anonymized_text)
# <<PERSON_1>> travaille chez <<ORGANIZATION_1>> à <<LOCATION_1>>.
```

---

## Pipeline avec cache de session

Pour les scénarios multi-messages (conversation), `AnonymizationPipeline` maintient un registre de placeholders et évite de re-détecter les mêmes entités.

```python
import asyncio
from piighost.pipeline import AnonymizationPipeline

pipeline = AnonymizationPipeline(
    anonymizer=anonymizer,
    labels=["PERSON", "LOCATION"],
)

async def conversation():
    # Premier message : détection NER + mise en cache
    r1 = await pipeline.anonymize("Patrick est à Paris.")
    print(r1.anonymized_text)
    # <<PERSON_1>> est à <<LOCATION_1>>.

    # Second message avec le même texte : résultat depuis le cache
    r2 = await pipeline.anonymize("Patrick est à Paris.")
    print(r2.anonymized_text)
    # <<PERSON_1>> est à <<LOCATION_1>>.  (pas de second appel NER)

    # Désanonymiser n'importe quelle chaîne dérivée (synchrone)
    print(pipeline.deanonymize_text("Bonjour, <<PERSON_1>> !"))
    # Bonjour, Patrick !

    # Reanonymiser (original → placeholder)
    print(pipeline.reanonymize_text("Réponse pour Patrick à Paris"))
    # Réponse pour <<PERSON_1>> à <<LOCATION_1>>

asyncio.run(conversation())
```

---

## Store personnalisé (Redis, PostgreSQL…)

Par défaut, le pipeline utilise un store en mémoire. Pour la persistance inter-processus, implémentez `PlaceholderStore` :

```python
from piighost.pipeline import PlaceholderStore, AnonymizationPipeline
from piighost.anonymizer.models import AnonymizationResult
import pickle

class RedisPlaceholderStore:
    def __init__(self, client):
        self._client = client

    async def get(self, key: str) -> AnonymizationResult | None:
        data = await self._client.get(f"piighost:{key}")
        return pickle.loads(data) if data else None

    async def set(self, key: str, result: AnonymizationResult) -> None:
        await self._client.set(f"piighost:{key}", pickle.dumps(result))

# Injection du store Redis
pipeline = AnonymizationPipeline(
    anonymizer=anonymizer,
    labels=["PERSON", "LOCATION"],
    store=RedisPlaceholderStore(redis_client),
)
```

---

## Inspection des résultats

`AnonymizationResult` expose toutes les informations de la passe d'anonymisation :

```python
result = anonymizer.anonymize(
    "Contactez Jean Martin au bureau de Bordeaux.",
    labels=["PERSON", "LOCATION"],
)

# Texte anonymisé
print(result.anonymized_text)

# Accéder aux placeholders
for p in result.placeholders:
    print(f"'{p.original}' → '{p.replacement}' [{p.label}]")

# Nombre d'entités détectées
print(f"{len(result.placeholders)} entité(s) anonymisée(s)")
```

---

## Tester sans charger GLiNER2

En test, utilisez un `FakeDetector` pour éviter de télécharger le modèle :

```python
from typing import Sequence
from piighost.anonymizer.models import Entity
from piighost.anonymizer import Anonymizer

class FakeDetector:
    def __init__(self, entities: list[Entity]):
        self._entities = entities

    def detect(self, text: str, labels: Sequence[str]) -> list[Entity]:
        return self._entities

# Détection déterministe sans modèle NER
fake = FakeDetector([
    Entity(text="Patrick", label="PERSON", start=0, end=7, score=1.0),
    Entity(text="Paris", label="LOCATION", start=19, end=24, score=1.0),
])
anonymizer = Anonymizer(detector=fake)
```

Voir aussi la [page Étendre PIIGhost](../extending.md) pour créer d'autres composants personnalisés.
