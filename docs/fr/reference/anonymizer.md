---
icon: lucide/scan-text
---

# Reference Anonymizer

Module : `piighost.anonymizer`

---

## `Anonymizer`

Effectue le remplacement de texte par spans en utilisant une placeholder factory. Classe **stateless** aucun etat interne entre les appels.

### Constructeur

```python
Anonymizer(ph_factory: AnyPlaceholderFactory)
```

| Parametre | Type | Description |
|-----------|------|-------------|
| `ph_factory` | `AnyPlaceholderFactory` | Factory de placeholders pour la generation de tokens (requis) |

### Methodes

#### `anonymize(text, entities) -> str`

Remplace chaque detection dans `text` par le token de son entite. Les remplacements sont appliques de droite a gauche.

```python
from piighost.anonymizer import Anonymizer
from piighost.placeholder import CounterPlaceholderFactory
from piighost.models import Detection, Entity, Span

anonymizer = Anonymizer(CounterPlaceholderFactory())

entity = Entity(detections=(
    Detection(text="Patrick", label="PERSON", position=Span(0, 7), confidence=0.9),
))

result = anonymizer.anonymize("Patrick est gentil", [entity])
# '<<PERSON_1>> est gentil'
```

#### `deanonymize(anonymized_text, entities) -> str`

Restaure le texte original en remplacant les tokens par les textes de detection originaux.

```python
original = anonymizer.deanonymize("<<PERSON_1>> est gentil", [entity])
# 'Patrick est gentil'
```

---

## Detecteurs

Module : `piighost.detector`

### `AnyDetector` (Protocole)

Interface pour tous les detecteurs d'entites. Tous les detecteurs sont **async**.

```python
class AnyDetector(Protocol):
    async def detect(self, text: str) -> list[Detection]: ...
```

### `GlinerDetector`

Implementation utilisant le modele **GLiNER2**.

```python
GlinerDetector(
    model: GLiNER2,
    labels: list[str],
    threshold: float = 0.5,
    flat_ner: bool = True,
)
```

| Parametre | Type | Defaut | Description |
|-----------|------|--------|-------------|
| `model` | `GLiNER2` | | Instance du modele GLiNER2 (requis) |
| `labels` | `list[str]` | | Types d'entites a detecter (requis) |
| `threshold` | `float` | `0.5` | Score de confiance minimum (0.0–1.0) |
| `flat_ner` | `bool` | `True` | Mode NER sans entites imbriquees |

### `ExactMatchDetector`

Detection par correspondance exacte de mots avec regex word-boundary. Utile pour les tests.

```python
ExactMatchDetector(
    bag_of_words: list[tuple[str, str]],
    flags: re.RegexFlag = re.IGNORECASE,
)
```

### `RegexDetector`

Detection par patterns regex, un pattern par label.

```python
RegexDetector(patterns: dict[str, str])
```

### `CompositeDetector`

Chaine plusieurs detecteurs et fusionne leurs resultats.

```python
CompositeDetector(detectors: list[AnyDetector])
```

---

## Placeholder Factories

Module : `piighost.placeholder`

### `AnyPlaceholderFactory` (Protocole)

```python
class AnyPlaceholderFactory(Protocol):
    def create(self, entities: list[Entity]) -> dict[Entity, str]: ...
```

### `CounterPlaceholderFactory`

Tags sequentiels `<<LABEL_N>>`.

```python
factory = CounterPlaceholderFactory()
tokens = factory.create([person, location])
# {person: '<<PERSON_1>>', location: '<<LOCATION_1>>'}
```

### `HashPlaceholderFactory`

Tags opaques deterministes bases sur SHA-256.

```python
factory = HashPlaceholderFactory(hash_length=8)
tokens = factory.create([person])
# {person: '<PERSON:a1b2c3d4>'}
```

### `RedactPlaceholderFactory`

Toutes les entites du meme label partagent le meme token `<LABEL>`.

```python
factory = RedactPlaceholderFactory()
tokens = factory.create([person, location])
# {person: '<PERSON>', location: '<LOCATION>'}
```

---

## Modeles de donnees

Module : `piighost.models`

### `Detection`

Resultat de detection NER.

```python
@dataclass(frozen=True)
class Detection:
    text: str           # Forme de surface : "Patrick"
    label: str          # Type d'entite : "PERSON"
    position: Span      # Position dans le texte
    confidence: float   # Score (0.0–1.0)
```

### `Entity`

Groupe de detections referant au meme PII.

```python
@dataclass(frozen=True)
class Entity:
    detections: tuple[Detection, ...]
    # label: str (propriete, depuis la premiere detection)
```

### `Span`

Position dans le texte source.

```python
@dataclass(frozen=True)
class Span:
    start_pos: int   # Index de debut (inclus)
    end_pos: int     # Index de fin (exclus)
    # overlaps(other: Span) -> bool
```

---

## Exceptions

Module : `piighost.exceptions`

### `CacheMissError`

Levee quand une recherche en cache ne trouve pas d'entree. Utilisee par le middleware pour basculer de `pipeline.deanonymize()` vers `pipeline.deanonymize_with_ent()`.
