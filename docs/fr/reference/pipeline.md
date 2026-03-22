---
icon: lucide/database
---

# Référence Pipeline

Module : `piighost.pipeline`

---

## `AnonymizationPipeline`

Pipeline d'anonymisation avec **état de session** et **cache persistant**. Encapsule un `Anonymizer` stateless avec :

- Un `PlaceholderStore` (async) pour la persistance inter-sessions
- Un registre en mémoire `_results` pour les opérations synchrones rapides

### Constructeur

```python
AnonymizationPipeline(
    anonymizer: Anonymizer,
    labels: Sequence[str],
    store: PlaceholderStore | None = None,
)
```

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `anonymizer` | `Anonymizer` | | Moteur d'anonymisation stateless (requis) |
| `labels` | `Sequence[str]` | | Types d'entités à détecter (requis) |
| `store` | `PlaceholderStore \| None` | `InMemoryPlaceholderStore()` | Backend de persistance |

### Méthodes

#### `anonymize(text) → AnonymizationResult` *(async)*

Anonymise `text`, met le résultat en cache et l'enregistre dans le registre de session.

Si le texte exact a déjà été traité (cache hit), le résultat stocké est retourné sans appel au modèle NER.

```python
result = await pipeline.anonymize("Patrick habite à Paris.")
print(result.anonymized_text)
# <<PERSON_1>> habite à <<LOCATION_1>>.
```

!!! note "Cache SHA-256"
    La clé de cache est le hash SHA-256 du texte source. Les textes identiques retournent toujours le même résultat.

#### `deanonymize_text(text) → str`

Remplace tous les tags placeholder connus dans `text` par leurs valeurs originales.

Fonctionne par **remplacement de chaîne** (non basé sur les spans), ce qui permet de désanonymiser n'importe quelle chaîne dérivée d'un texte anonymisé y compris les arguments générés par le LLM.

```python
pipeline.deanonymize_text("Bonjour, <<PERSON_1>> de <<LOCATION_1>> !")
# "Bonjour, Patrick de Paris !"
```

| Paramètre | Type | Description |
|-----------|------|-------------|
| `text` | `str` | Chaîne pouvant contenir des tags placeholder |

**Retourne** : `str`

#### `reanonymize_text(text) → str`

Inverse de `deanonymize_text` : remplace chaque valeur originale connue par son tag.

```python
pipeline.reanonymize_text("Résultat pour Patrick à Paris")
# "Résultat pour <<PERSON_1>> à <<LOCATION_1>>"
```

| Paramètre | Type | Description |
|-----------|------|-------------|
| `text` | `str` | Chaîne pouvant contenir des valeurs originales |

**Retourne** : `str`

#### `results` (propriété)

Tous les résultats enregistrés lors de la session courante (lecture seule).

```python
pipeline.results  # tuple[AnonymizationResult, ...]
```

---

## `PlaceholderStore` (Protocole)

Interface pour le backend de persistance des `AnonymizationResult`.

```python
class PlaceholderStore(Protocol):
    async def get(self, key: str) -> AnonymizationResult | None:
        ...

    async def set(self, key: str, result: AnonymizationResult) -> None:
        ...
```

| Méthode | Description |
|---------|-------------|
| `get(key)` | Récupère un résultat par sa clé SHA-256, ou `None` si absent |
| `set(key, result)` | Persiste un résultat |

La clé est toujours le **hash SHA-256** du texte source original.

---

## `InMemoryPlaceholderStore`

Implémentation par défaut : stockage en mémoire, adapté aux tests et aux déploiements mono-processus.

```python
InMemoryPlaceholderStore()
```

Aucune configuration nécessaire. Non persistant les données sont perdues à l'arrêt du processus.

```python
from piighost.pipeline import InMemoryPlaceholderStore, AnonymizationPipeline

pipeline = AnonymizationPipeline(
    anonymizer=anonymizer,
    labels=["PERSON"],
    store=InMemoryPlaceholderStore(),  # équivalent au comportement par défaut
)
```

---

## Exemple complet

```python
import asyncio
from piighost.anonymizer import Anonymizer, GlinerDetector
from piighost.pipeline import AnonymizationPipeline
from gliner2 import GLiNER2

model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")
detector = GlinerDetector(model=model)
anonymizer = Anonymizer(detector=detector)

pipeline = AnonymizationPipeline(
    anonymizer=anonymizer,
    labels=["PERSON", "LOCATION"],
)

async def main():
    # Anonymisation async
    r1 = await pipeline.anonymize("Patrick est à Lyon.")
    print(r1.anonymized_text)  # <<PERSON_1>> est à <<LOCATION_1>>.

    # Même texte → cache hit (pas de second appel NER)
    r2 = await pipeline.anonymize("Patrick est à Lyon.")
    assert r1 is r2  # même objet

    # Désanonymisation synchrone
    text = pipeline.deanonymize_text("Bonjour <<PERSON_1>>, bienvenue à <<LOCATION_1>>.")
    print(text)  # Bonjour Patrick, bienvenue à Lyon.

    # Reanonymisation synchrone
    text2 = pipeline.reanonymize_text("Patrick a répondu depuis Lyon.")
    print(text2)  # <<PERSON_1>> a répondu depuis <<LOCATION_1>>.

asyncio.run(main())
```

---

## Store personnalisé

Voir [Étendre PIIGhost PlaceholderStore](../extending.md#créer-un-placeholderstore-personnalisé) pour des exemples Redis et PostgreSQL.
