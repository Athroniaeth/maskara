---
icon: lucide/scan-text
---

# Référence Anonymizer

Module : `piighost.anonymizer`

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

**Lève** : `IrreversibleAnonymizationError` si le placeholder factory n'est pas réversible.

#### `reversible` (propriété)

Retourne `True` si le placeholder factory supporte la désanonymisation.

```python
anonymizer = Anonymizer(detector=detector)
anonymizer.reversible  # True (CounterPlaceholderFactory par défaut)
anonymizer.check_reversible()  # no-op

anonymizer = Anonymizer(detector=detector, placeholder_factory=RedactPlaceholderFactory())
anonymizer.reversible  # False
anonymizer.check_reversible()  # lève IrreversibleAnonymizationError
```

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
from piighost.anonymizer import GlinerDetector

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

Voir [Étendre PIIGhost](../extending.md#créer-un-entitydetector-personnalisé) pour des exemples.

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

## `PlaceholderFactory` (ABC)

Classe de base abstraite pour toutes les placeholder factories. Fournit deux méthodes polymorphiques pour vérifier la réversibilité — pas besoin de `isinstance`.

```python
class PlaceholderFactory(ABC):
    def get_or_create(self, original: str, label: str) -> Placeholder:
        ...

    def reset(self) -> None:
        ...

    @property
    def reversible(self) -> bool:
        """Retourne False par défaut."""

    def check_reversible(self) -> None:
        """Lève IrreversibleAnonymizationError par défaut."""
```

Utilisez `factory.reversible` pour vérifier au runtime, ou `factory.check_reversible()` pour lever une exception si non supporté.

### `ReversiblePlaceholderFactory` (ABC)

Classe de base pour les factories qui produisent des tags de remplacement **uniques et distinguables**. Les factories héritant de cette classe garantissent que chaque paire `(original, label)` reçoit un tag distinct, rendant la désanonymisation possible.

`CounterPlaceholderFactory` et `HashPlaceholderFactory` héritent de `ReversiblePlaceholderFactory`.

Override `reversible` pour retourner `True` et `check_reversible()` pour ne rien faire.

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

### `HashPlaceholderFactory`

Génère des tags opaques et déterministes basés sur un hash SHA-256 — identique à la stratégie utilisée par le middleware de redaction PII intégré à LangChain.

```python
HashPlaceholderFactory(
    digest_length: int = 8,
    template: str = "<{label}:{digest}>",
)
```

| Paramètre | Défaut | Description |
|-----------|--------|-------------|
| `digest_length` | `8` | Nombre de caractères hex du digest SHA-256 |
| `template` | `"<{label}:{digest}>"` | Template avec `{label}` et `{digest}` |

```python
from piighost.anonymizer import HashPlaceholderFactory

factory = HashPlaceholderFactory()
factory.get_or_create("Patrick", "PERSON").replacement  # '<PERSON:3b4c5d6e>'
factory.get_or_create("Patrick", "PERSON").replacement  # '<PERSON:3b4c5d6e>' (même hash)
factory.get_or_create("Marie", "PERSON").replacement    # '<PERSON:9f2a1c7b>' (différent)
factory.reset()  # efface le cache
```

Le hash est calculé uniquement à partir du texte original — la même entité produit toujours le même placeholder, quel que soit l'ordre de rencontre.

**Utilisation avec `Anonymizer` :**

```python
anonymizer = Anonymizer(
    detector=detector,
    placeholder_factory=HashPlaceholderFactory(digest_length=12),
)
```

### `RedactPlaceholderFactory`

Remplace **toutes** les entités par le même tag opaque (`[REDACTED]`). Pas d'index, pas de label, pas de distinction entre entités — confidentialité maximale, zéro fuite d'information.

```python
RedactPlaceholderFactory(tag: str = "[REDACTED]")
```

| Paramètre | Défaut | Description |
|-----------|--------|-------------|
| `tag` | `"[REDACTED]"` | La chaîne de remplacement pour toutes les entités |

```python
from piighost.anonymizer import RedactPlaceholderFactory

factory = RedactPlaceholderFactory()
factory.get_or_create("Patrick", "PERSON").replacement   # '[REDACTED]'
factory.get_or_create("Paris", "LOCATION").replacement    # '[REDACTED]'
factory.get_or_create("alice@exemple.fr", "EMAIL").replacement  # '[REDACTED]'
```

**Utilisation avec `Anonymizer` :**

```python
anonymizer = Anonymizer(
    detector=detector,
    placeholder_factory=RedactPlaceholderFactory(),
)
result = anonymizer.anonymize("Patrick habite à Paris.")
print(result.anonymized_text)
# [REDACTED] habite à [REDACTED].
```

!!! warning "Non réversible"
    `RedactPlaceholderFactory` n'hérite **pas** de `ReversiblePlaceholderFactory`. Appeler `anonymizer.deanonymize(result)` lèvera `IrreversibleAnonymizationError`. Elle ne peut pas être utilisée avec `AnonymizationPipeline` (qui nécessite la désanonymisation pour les appels d'outils).

---

### Réversible vs irréversible

PIIGhost distingue deux catégories de placeholder factories :

| | Réversible | Irréversible |
|---|---|---|
| **Classe de base** | `ReversiblePlaceholderFactory` | `PlaceholderFactory` directement |
| **`reversible`** | `True` | `False` |
| **`check_reversible()`** | No-op | Lève `IrreversibleAnonymizationError` |
| **Tags uniques** | Chaque entité reçoit un tag distinct | Toutes les entités partagent le même tag |
| **Désanonymisation** | Supportée | Lève `IrreversibleAnonymizationError` |
| **Fuite d'information** | Révèle le nombre d'entités et les co-références | Zéro fuite |
| **Avec Pipeline** | Oui | Non |
| **Avec Middleware** | Oui | Non |
| **Implémentations** | `CounterPlaceholderFactory`, `HashPlaceholderFactory` | `RedactPlaceholderFactory` |

**Quand utiliser chacune :**

- **Réversible** (par défaut) — quand vous avez besoin d'anonymisation bidirectionnelle, ex: conversations d'agents LLM où les appels d'outils doivent être désanonymisés avant exécution.
- **Irréversible** — quand vous voulez uniquement supprimer le PII sans jamais le récupérer, ex: logging, analytics, export de données, conformité RGPD.

---

## Exceptions

### `IrreversibleAnonymizationError`

Levée lors d'une tentative de désanonymisation d'un résultat produit par une factory non réversible.

```python
from piighost.anonymizer import IrreversibleAnonymizationError

anonymizer = Anonymizer(
    detector=detector,
    placeholder_factory=RedactPlaceholderFactory(),
)
result = anonymizer.anonymize("Patrick habite à Paris.")

try:
    anonymizer.deanonymize(result)
except IrreversibleAnonymizationError as e:
    print(e)
    # RedactPlaceholderFactory is not reversible. Deanonymization requires
    # a ReversiblePlaceholderFactory (e.g. CounterPlaceholderFactory or HashPlaceholderFactory).
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
