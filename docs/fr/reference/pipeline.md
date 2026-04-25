---
icon: lucide/database
---

# Reference Pipeline

Module : `piighost.pipeline`

---

## `AnonymizationPipeline`

Orchestre le pipeline complet d'anonymisation : detect → resolve spans → link entities → resolve entities → anonymize. Utilise aiocache pour le cache des resultats de detection et des mappings d'anonymisation.

### Constructeur

!!! note "Chaque argument est un protocole"
    `AnyDetector`, `AnySpanConflictResolver`, `AnyEntityLinker`, `AnyEntityConflictResolver`, `AnyAnonymizer`. Remplaçables un par un, voir [Étendre PIIGhost](../extending.md).

```python
AnonymizationPipeline(
    detector: AnyDetector,
    span_resolver: AnySpanConflictResolver,
    entity_linker: AnyEntityLinker,
    entity_resolver: AnyEntityConflictResolver,
    anonymizer: AnyAnonymizer,
    cache: BaseCache | None = None,
)
```

| Parametre | Type | Defaut | Description |
|-----------|------|--------|-------------|
| `detector` | `AnyDetector` | | Detecteur async d'entites (requis) |
| `span_resolver` | `AnySpanConflictResolver` | | Gere les detections chevauchantes (requis) |
| `entity_linker` | `AnyEntityLinker` | | Groupe les detections en entites (requis) |
| `entity_resolver` | `AnyEntityConflictResolver` | | Fusionne les entites conflictuelles (requis) |
| `anonymizer` | `AnyAnonymizer` | | Moteur de remplacement de texte (requis) |
| `cache` | `BaseCache \| None` | `Cache(Cache.MEMORY)` | Instance aiocache |

### Methodes

#### `detect_entities(text) -> list[Entity]` *(async)*

Execute le pipeline de detection : detect → resolve spans → link → resolve entities.

#### `anonymize(text) -> tuple[str, list[Entity]]` *(async)*

Execute le pipeline complet et stocke le mapping en cache pour desanonymisation ulterieure.

```python
anonymized, entities = await pipeline.anonymize("Patrick habite a Paris.")
# <<PERSON:1>> habite a <<LOCATION:1>>.
```

#### `deanonymize(anonymized_text) -> tuple[str, list[Entity]]` *(async)*

Desanonymise en utilisant le texte anonymise comme cle de recherche dans le cache.

**Leve** : `CacheMissError` si le texte n'a jamais ete produit par ce pipeline.

---

## `ThreadAnonymizationPipeline`

Étend `AnonymizationPipeline` avec une mémoire de conversation scopée par `thread_id`, pour le suivi cohérent des entités entre les messages d'un même thread.

### Constructeur

```python
ThreadAnonymizationPipeline(
    detector: AnyDetector,
    span_resolver: AnySpanConflictResolver,
    entity_linker: AnyEntityLinker,
    entity_resolver: AnyEntityConflictResolver,
    anonymizer: AnyAnonymizer,
    memory: AnyConversationMemory | None = None,
)
```

### Methodes

#### `anonymize(text) -> tuple[str, list[Entity]]` *(async)*

Detecte les entites, les enregistre en memoire, puis anonymise en utilisant toutes les entites connues.

#### `deanonymize_with_ent(text) -> str` *(async)*

Remplacement de chaine : tokens → valeurs originales (plus long d'abord). Fonctionne sur n'importe quel texte contenant des tokens.

#### `anonymize_with_ent(text) -> str`

Remplacement de chaine : valeurs originales → tokens (plus long d'abord).

#### `resolved_entities` (propriete)

Toutes les entites de la memoire, fusionnees par l'entity resolver.

---

## `ConversationMemory`

Module : `piighost.conversation_memory`

Memoire de conversation en memoire qui accumule les entites entre les messages, dedupliquees par `(text.lower(), label)`.

### Protocole

```python
class AnyConversationMemory(Protocol):
    entities_by_hash: dict[str, list[Entity]]

    @property
    def all_entities(self) -> list[Entity]: ...

    def record(self, text_hash: str, entities: list[Entity]) -> None: ...
```

---

## Cache

Le pipeline utilise **aiocache** avec des backends configurables. Par defaut, `Cache(Cache.MEMORY)` est utilise (en memoire, non persistant).

Cles de cache avec prefixes :

- `detect:<hash>` resultats du detecteur
- `anon:anonymized:<hash>` mappings d'anonymisation

Pour un autre backend (Redis, Memcached), passez une instance `BaseCache` d'aiocache :

```python
from aiocache import Cache

pipeline = AnonymizationPipeline(
    ...,
    cache=Cache(Cache.REDIS, endpoint="localhost", port=6379),
)
```

---

## Exemple complet

```python
import asyncio
from piighost.anonymizer import Anonymizer
from piighost.detector import Gliner2Detector
from piighost.linker.entity import ExactEntityLinker
from piighost.entity_resolver import MergeEntityConflictResolver
from piighost.pipeline import AnonymizationPipeline
from piighost.placeholder import LabelCounterPlaceholderFactory
from piighost.span_resolver import ConfidenceSpanConflictResolver
from gliner2 import GLiNER2

model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")

detector = Gliner2Detector(model=model, labels=["PERSON", "LOCATION"], threshold=0.5)
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


async def main():
    anonymized, entities = await pipeline.anonymize("Patrick est a Lyon.")
    print(anonymized)  # <<PERSON:1>> est a <<LOCATION:1>>.

    original, _ = await pipeline.deanonymize(anonymized)
    print(original)  # Patrick est a Lyon.


asyncio.run(main())
```
