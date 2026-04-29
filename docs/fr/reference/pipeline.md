---
icon: lucide/database
---

# Référence Pipeline

Module : `piighost.pipeline`

`AnonymizationPipeline` enchaîne les cinq étages detect, resolve spans, link entities, resolve entities et anonymize, avec une étape finale `guard` optionnelle. `ThreadAnonymizationPipeline` y ajoute une mémoire et un cache scopés par `thread_id` pour que le même placeholder reste attribué à la même entité tout au long d'une conversation.

---

## `AnonymizationPipeline`

Pipeline sans état conversationnel. Chaque appel à `anonymize()` est indépendant. Seul le cache (clé SHA-256) sert de continuité entre appels.

### Constructeur

!!! note "Tous les composants sont des protocoles"
    `AnyDetector`, `AnySpanConflictResolver`, `AnyEntityLinker`, `AnyEntityConflictResolver`, `AnyAnonymizer`, `AnyGuardRail`, `AbstractObservationService`. Voir [Étendre PIIGhost](../extending.md) pour les remplacer un par un.

```python
AnonymizationPipeline(
    detector: AnyDetector,
    anonymizer: AnyAnonymizer,
    span_resolver: AnySpanConflictResolver | None = None,
    entity_linker: AnyEntityLinker | None = None,
    entity_resolver: AnyEntityConflictResolver | None = None,
    guard_rail: AnyGuardRail | None = None,
    cache: BaseCache | None = None,
    cache_ttl: int | None = None,
    observation: AbstractObservationService | None = None,
    observe_raw_text: bool = False,
)
```

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `detector` | `AnyDetector` | requis | Détecteur d'entités async |
| `anonymizer` | `AnyAnonymizer` | requis | Moteur de remplacement et placeholder factory |
| `span_resolver` | `AnySpanConflictResolver` | `ConfidenceSpanConflictResolver()` | Résout les détections qui se chevauchent |
| `entity_linker` | `AnyEntityLinker` | `ExactEntityLinker()` | Groupe les détections en entités |
| `entity_resolver` | `AnyEntityConflictResolver` | `MergeEntityConflictResolver()` | Fusionne les entités en conflit |
| `guard_rail` | `AnyGuardRail` | `DisabledGuardRail()` | Étage final qui revalide la sortie. Passer un `DetectorGuardRail` pour lever `PIIRemainingError` quand de la PII résiduelle est détectée |
| `cache` | `BaseCache` | `SimpleMemoryCache()` | Backend aiocache pour les détections et les mappings d'anonymisation |
| `cache_ttl` | `int \| None` | `None` | Durée de vie en secondes appliquée à chaque entrée écrite. `None` laisse le backend gérer l'éviction |
| `observation` | `AbstractObservationService` | `NoOpObservationService()` | Backend d'observation (Langfuse, etc.). Le défaut ne logue rien |
| `observe_raw_text` | `bool` | `False` | Quand `False`, le texte utilisateur brut et les surfaces de PII sont remplacés par `[REDACT]` dans les payloads d'observation. Passer `True` pour désactiver la redaction |

### Méthodes

#### `anonymize(text, *, metadata=None, root_span=None) -> tuple[str, list[Entity]]` *(async)*

Exécute le pipeline complet et stocke le mapping en cache pour une désanonymisation ultérieure.

- `metadata` est transmis au trace d'observation (les valeurs non-string sont coercées pour Langfuse).
- `root_span` permet à l'appelant de fournir un span racine déjà ouvert. Le pipeline imbrique alors ses observations sous ce span au lieu d'en créer un nouveau via le service configuré.

```python
anonymized, entities = await pipeline.anonymize("Patrick habite à Paris.")
# <<PERSON:1>> habite à <<LOCATION:1>>.
```

#### `detect_entities(text) -> list[Entity]` *(async)*

Exécute uniquement detect → resolve spans → link → resolve entities, sans anonymisation ni écriture cache.

#### `deanonymize(anonymized_text) -> tuple[str, list[Entity]]` *(async)*

Recherche le texte anonymisé dans le cache par hash SHA-256 et reconstruit l'original via remplacement par positions.

**Lève** `CacheMissError` si le texte n'a jamais été produit par ce pipeline.

#### `ph_factory` (propriété)

La placeholder factory utilisée par l'anonymizer.

---

## `ThreadAnonymizationPipeline`

Pipeline conversationnel. La mémoire et le cache sont isolés par `thread_id`, donc la même entité conserve le même placeholder sur tous les messages d'un thread, et il n'y a pas de fuite inter-threads.

### Constructeur

```python
ThreadAnonymizationPipeline(
    detector: AnyDetector,
    anonymizer: AnyAnonymizer,
    entity_linker: AnyEntityLinker | None = None,
    entity_resolver: AnyEntityConflictResolver | None = None,
    span_resolver: AnySpanConflictResolver | None = None,
    guard_rail: AnyGuardRail | None = None,
    cache: BaseCache | None = None,
    cache_ttl: int | None = None,
    max_threads: int | None = None,
    observation: AbstractObservationService | None = None,
    observe_raw_text: bool = False,
)
```

En plus de tous les paramètres de `AnonymizationPipeline` :

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `max_threads` | `int \| None` | `None` | Nombre maximum de mémoires de conversation gardées en RAM. Quand le plafond est atteint, la mémoire la moins récemment utilisée est évincée. `None` désactive le plafond |

!!! warning "Factory réversible obligatoire"
    Le constructeur rejette toute placeholder factory non taguée `PreservesIdentity`. Utiliser `LabelCounterPlaceholderFactory` ou `LabelHashPlaceholderFactory`, les deux factories réversibles fournies.

!!! note "Déploiement multi-instance"
    Le défaut `SimpleMemoryCache` est local au processus. En déploiement multi-worker, basculer sur un backend partagé (Redis) pour que les placeholders restent cohérents d'un worker à l'autre. Le constructeur émet un avertissement une fois par processus dans ce cas. Voir [Déploiement multi-instance](../multi-instance.md).

### Méthodes

#### `anonymize(text, thread_id="default", *, metadata=None, root_span=None) -> tuple[str, list[Entity]]` *(async)*

Détecte les entités, les enregistre dans la mémoire de `thread_id`, puis anonymise en utilisant l'ensemble des entités déjà connues du thread. Les compteurs restent stables d'un message à l'autre.

Quand le pipeline ouvre lui-même son span racine (pas d'argument `root_span=`), le `thread_id` est transmis au backend d'observation comme `session_id` (sauf pour la valeur littérale `"default"`).

```python
a1, _ = await pipeline.anonymize("Patrick habite à Paris.", thread_id="user-A")
a2, _ = await pipeline.anonymize("Patrick a écrit à Marie.", thread_id="user-A")
# Patrick conserve <<PERSON:1>> sur les deux tours.
```

#### `deanonymize(anonymized_text, thread_id="default") -> tuple[str, list[Entity]]` *(async)*

Renvoie le texte original directement depuis le cache. Contrairement à la version base, ne rejoue pas le remplacement par positions, qui ne marcherait pas avec des positions provenant de messages différents.

**Lève** `CacheMissError` si le texte n'a jamais été produit dans ce thread.

#### `anonymize_with_ent(text, thread_id="default") -> str`

Remplacement synchrone, en une passe, de toutes les surfaces connues d'entités (et de leurs variantes) par leur placeholder. Marche sur du texte qui n'est pas passé par le pipeline (arguments d'outil, sortie LLM intermédiaire).

#### `deanonymize_with_ent(text, thread_id="default") -> str` *(async)*

Inverse. Remplace tous les placeholders connus par leur surface originale. Le résultat est aussi mis en cache pour qu'un appel ultérieur à `deanonymize()` puisse le retrouver.

#### `override_detections(text, detections, thread_id="default") -> None` *(async)*

Écrase les détections cachées pour *text*. Utile quand l'utilisateur corrige ce que le détecteur a trouvé. Le prochain `anonymize()` sur ce texte réutilisera les détections corrigées au lieu de relancer le détecteur.

#### `get_memory(thread_id="default") -> ConversationMemory`

Renvoie la mémoire du thread, créée à la première demande. Rafraîchit la position LRU quand `max_threads` est défini.

#### `get_resolved_entities(thread_id="default") -> list[Entity]`

Toutes les entités du thread, fusionnées par l'entity resolver.

#### `clear_memory(thread_id) -> None`

Supprime la mémoire d'un thread. À appeler à la fin d'une conversation pour ne pas accumuler les entités.

#### `clear_all_memories() -> None`

Supprime toutes les mémoires de conversation suivies par le pipeline.

---

## `ConversationMemory`

Module : `piighost.pipeline`

Implémentation par défaut de `AnyConversationMemory`. Accumule les entités d'un thread et les déduplique par `(text.lower(), label)`. Les variantes orthographiques d'une même entité canonique (par exemple `"france"` après `"France"`) sont fusionnées dans l'entité existante pour que `anonymize_with_ent` puisse remplacer toutes les graphies observées.

### Protocole

```python
class AnyConversationMemory(Protocol):
    entities_by_hash: dict[str, list[Entity]]

    @property
    def all_entities(self) -> list[Entity]: ...

    def record(self, text_hash: str, entities: list[Entity]) -> None: ...
```

### Membres

- `record(text_hash, entities)` enregistre les entités d'un message et fusionne les variantes.
- `all_entities` (propriété) renvoie la liste plate dédupliquée, dans l'ordre d'insertion.

---

## Cache

Les pipelines utilisent **aiocache** avec des backends configurables. Les clés portent un préfixe stable :

- `detect:<sha256>` pour les détections d'un texte donné.
- `anon:anonymized:<sha256>` pour le mapping `texte anonymisé → (original, entities)` exploité par `deanonymize`.

`ThreadAnonymizationPipeline` ajoute en plus le préfixe `<thread_id>:` à chaque clé pour isoler les conversations.

```python
from aiocache import RedisCache

pipeline = ThreadAnonymizationPipeline(
    detector=detector,
    anonymizer=anonymizer,
    cache=RedisCache(endpoint="redis", port=6379),
    cache_ttl=86_400,  # un jour
)
```

---

## Observation

Tout `AbstractObservationService` produit une trace à 4 étages enfants (`detect`, `link`, `placeholder`, `guard`) sous un span parent `piighost.anonymize_pipeline`. Le défaut `NoOpObservationService` ne logue rien et n'a aucun coût. L'implémentation fournie est `LangfuseObservationService(client)`.

Par défaut le pipeline rédige tout texte utilisateur brut, tout champ `text` de `Detection` et tout champ `text` d'`Entity` dans les payloads d'observation, en les remplaçant par `[REDACT]`. Les payloads déjà anonymisés (`placeholder.output`, `guard.input/output`, `output` du span racine) passent inchangés. Passer `observe_raw_text=True` pour désactiver la redaction. Voir [Sécurité](../security.md) pour le détail du modèle de menaces.

---

## Exemple complet

```python
import asyncio

from gliner2 import GLiNER2

from piighost.anonymizer import Anonymizer
from piighost.detector.gliner2 import Gliner2Detector
from piighost.pipeline import ThreadAnonymizationPipeline
from piighost.placeholder import LabelCounterPlaceholderFactory

model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")
detector = Gliner2Detector(model=model, threshold=0.5, labels=["PERSON", "LOCATION"])
anonymizer = Anonymizer(ph_factory=LabelCounterPlaceholderFactory())

pipeline = ThreadAnonymizationPipeline(detector=detector, anonymizer=anonymizer)


async def main():
    a1, _ = await pipeline.anonymize("Patrick est à Lyon.", thread_id="user-A")
    print(a1)  # <<PERSON:1>> est à <<LOCATION:1>>.

    original, _ = await pipeline.deanonymize(a1, thread_id="user-A")
    print(original)  # Patrick est à Lyon.


asyncio.run(main())
```
