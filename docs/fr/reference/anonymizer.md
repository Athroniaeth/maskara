---
icon: lucide/scan-text
---

# Référence Anonymizer

Module : `maskara.anonymizer`

---

## `Anonymizer`

Orchestrateur du pipeline d'anonymisation en 4 étapes. Classe **stateless** aucun état interne entre les appels.

### Constructeur

```python
Anonymizer(
    detector: EntityDetector,
    occurrence_finder: OccurrenceFinder | None = None,
    placeholder_factory: PlaceholderFactory | None = None,
    replacer: SpanReplacer | None = None,
)
```

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `detector` | `EntityDetector` | | Backend NER (requis) |
| `occurrence_finder` | `OccurrenceFinder \| None` | `RegexOccurrenceFinder()` | Stratégie de localisation des occurrences |
| `placeholder_factory` | `PlaceholderFactory \| None` | `CounterPlaceholderFactory()` | Stratégie de génération de tags |
| `replacer` | `SpanReplacer \| None` | `SpanReplacer()` | Moteur de remplacement par spans |

### Méthodes

#### `anonymize(text, labels) → AnonymizationResult`

Anonymise `text` en détectant et remplaçant les entités sensibles.

```python
result = anonymizer.anonymize(
    "Patrick habite à Paris. Patrick aime Paris.",
    labels=["PERSON", "LOCATION"],
)
```

| Paramètre | Type | Description |
|-----------|------|-------------|
| `text` | `str` | Texte source |
| `labels` | `Sequence[str]` | Types d'entités à détecter (ex: `["PERSON", "LOCATION"]`) |

**Retourne** : `AnonymizationResult`

#### `deanonymize(result) → str`

Restaure le texte original depuis un `AnonymizationResult` (basé sur les spans inverses précalculés).

```python
original = anonymizer.deanonymize(result)
```

| Paramètre | Type | Description |
|-----------|------|-------------|
| `result` | `AnonymizationResult` | Résultat retourné par `anonymize` |

**Retourne** : `str` le texte original

---

## `GlinerDetector`

Implémentation de `EntityDetector` utilisant le modèle **GLiNER2**.

### Constructeur

```python
@dataclass
GlinerDetector(
    model: GLiNER2,
    threshold: float = 0.5,
    flat_ner: bool = True,
)
```

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `model` | `GLiNER2` | | Instance du modèle GLiNER2 (requis) |
| `threshold` | `float` | `0.5` | Score de confiance minimum (0.0–1.0) |
| `flat_ner` | `bool` | `True` | Mode NER sans entités imbriquées |

### Utilisation

```python
from gliner2 import GLiNER2
from maskara.anonymizer import GlinerDetector

model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")
detector = GlinerDetector(model=model, threshold=0.5, flat_ner=True)

entities = detector.detect("Patrick habite à Paris", ["PERSON", "LOCATION"])
# [Entity(text='Patrick', label='PERSON', start=0, end=7, score=0.97),
#  Entity(text='Paris', label='LOCATION', start=18, end=23, score=0.99)]
```

---

## `EntityDetector` (Protocole)

Interface à implémenter pour créer un détecteur personnalisé.

```python
class EntityDetector(Protocol):
    def detect(self, text: str, labels: Sequence[str]) -> list[Entity]:
        ...
```

Voir [Étendre Maskara](../extending.md#créer-un-entitydetector-personnalisé) pour des exemples.

---

## `OccurrenceFinder` (Protocole)

Interface pour trouver toutes les positions d'un fragment dans un texte.

```python
class OccurrenceFinder(Protocol):
    def find_all(self, text: str, fragment: str) -> list[tuple[int, int]]:
        ...
```

### `RegexOccurrenceFinder`

Implémentation par défaut : utilise `\bFRAGMENT\b` avec `re.IGNORECASE`.

```python
RegexOccurrenceFinder(flags: re.RegexFlag = re.IGNORECASE)
```

```python
finder = RegexOccurrenceFinder()
finder.find_all("Salut Patrick, APatrick", "Patrick")
# [(6, 13)]  "APatrick" n'est PAS retourné (pas de word-boundary)
```

---

## `PlaceholderFactory` (Protocole)

Interface pour générer des tags de remplacement.

```python
class PlaceholderFactory(Protocol):
    def get_or_create(self, original: str, label: str) -> Placeholder:
        ...

    def reset(self) -> None:
        ...
```

### `CounterPlaceholderFactory`

Implémentation par défaut : génère des tags `<<LABEL_N>>` séquentiels.

```python
CounterPlaceholderFactory(template: str = "<<{label}_{index}>>")
```

```python
factory = CounterPlaceholderFactory()
factory.get_or_create("Patrick", "PERSON").replacement  # '<<PERSON_1>>'
factory.get_or_create("Marie", "PERSON").replacement    # '<<PERSON_2>>'
factory.get_or_create("Patrick", "PERSON").replacement  # '<<PERSON_1>>' (mis en cache)
factory.reset()  # efface compteurs et cache
```

---

## Modèles de données

### `Entity`

Entité nommée détectée par le modèle NER.

```python
@dataclass(frozen=True)
class Entity:
    text: str    # Surface form : "Patrick"
    label: str   # Type : "PERSON"
    start: int   # Index de début (inclus)
    end: int     # Index de fin (exclus)
    score: float # Score de confiance (0.0–1.0)
```

### `Placeholder`

Lien entre un fragment original et son tag de remplacement.

```python
@dataclass(frozen=True)
class Placeholder:
    original: str     # "Patrick"
    label: str        # "PERSON"
    replacement: str  # "<<PERSON_1>>"
```

### `AnonymizationResult`

Sortie complète d'une passe d'anonymisation.

```python
@dataclass(frozen=True)
class AnonymizationResult:
    original_text: str              # Texte source
    anonymized_text: str            # Texte avec placeholders
    placeholders: tuple[Placeholder, ...]  # Tous les placeholders créés
    reverse_spans: tuple            # Spans inverses pour désanonymisation
```

!!! note "Immutabilité"
    Tous les modèles sont des **dataclasses gelées** (`frozen=True`) ils sont thread-safe et hashables.
