---
icon: lucide/network
---

# Déploiement multi-instance

Cette page explique pourquoi le cache par défaut (`SimpleMemoryCache`) casse silencieusement la cohérence des placeholders dès que votre application tourne sur plus d'un worker, et comment configurer un backend partagé pour rétablir la cohérence.

!!! abstract "Résumé"
    En multi-instance derrière un load balancer, chaque worker maintient son propre `SimpleMemoryCache`. Le même `thread_id` routé vers deux workers verra `Patrick` assigné à `<<PERSON:1>>`{ .placeholder } au tour 1 puis `<<PERSON:2>>`{ .placeholder } au tour 2, et le LLM ne peut plus relier les deux. La parade est un cache partagé (Redis, Memcached) passé explicitement au pipeline.

---

## Le piège

`SimpleMemoryCache` est un excellent défaut pour le développement et les déploiements single-instance. Il est rapide, sans dépendance externe, et n'exige aucune configuration. C'est aussi le défaut implicite quand vous instanciez `ThreadAnonymizationPipeline` sans préciser de backend.

Le problème apparaît dès qu'un load balancer route un même `thread_id` vers plusieurs workers. Chaque worker possède son propre cache `placeholder ↔ PII`, et ces caches ne communiquent pas.

```text
Tour 1 (routé vers worker A)
  Mémoire worker A : { Patrick → <<PERSON:1>> }
  Mémoire worker B : {}

Tour 2 (routé vers worker B, "Patrick" toujours dans le contexte)
  Mémoire worker A : { Patrick → <<PERSON:1>> }
  Mémoire worker B : { Patrick → <<PERSON:1>> }   # nouveau compteur, collision possible

Tour 3 (worker B reçoit "Marie")
  Mémoire worker B : { Patrick → <<PERSON:1>>, Marie → <<PERSON:2>> }

Tour 4 (worker A reçoit "Marie", l'ignore de son point de vue)
  Mémoire worker A : { Patrick → <<PERSON:1>>, Marie → <<PERSON:2>> }
  # Sur worker A, Marie aurait pu hériter d'un autre numéro si une autre PII l'avait précédée.
```

Le bug est silencieux. Aucune exception n'est levée, le pipeline produit du texte anonymisé valide, et l'incohérence ne devient visible que dans la qualité de réponse du LLM, qui perd le fil entre les tours.

---

## Le warning

À la première instanciation de `ThreadAnonymizationPipeline` sans backend explicite, la librairie émet un `PIIGhostConfigWarning` une fois par processus.

```text
PIIGhostConfigWarning: ThreadAnonymizationPipeline is using a process-local
cache (SimpleMemoryCache). In a multi-instance deployment behind a load
balancer, the placeholder mapping is not shared across workers...
```

Le warning parle de **correctness**, pas de performance. Le risque n'est pas que le pipeline soit lent, c'est qu'il produise des placeholders incohérents sans que rien ne le signale.

Si vous tournez en single-instance et que vous voulez supprimer le bruit, ajoutez un filtre :

```python
import warnings
from piighost import PIIGhostConfigWarning

warnings.filterwarnings("ignore", category=PIIGhostConfigWarning)
```

---

## Configurer un backend partagé

Le constructeur de `ThreadAnonymizationPipeline` accepte n'importe quelle instance `aiocache.BaseCache`. Pour le multi-instance, utilisez `RedisCache` ou `MemcachedCache`.

### Avec Redis

```python
from aiocache import RedisCache
from piighost.anonymizer import Anonymizer
from piighost.detector.gliner2 import Gliner2Detector
from piighost.pipeline.thread import ThreadAnonymizationPipeline
from piighost.placeholder import LabelCounterPlaceholderFactory

cache = RedisCache(
    endpoint="redis.internal",
    port=6379,
    namespace="piighost",
)

pipeline = ThreadAnonymizationPipeline(
    detector=Gliner2Detector(...),
    anonymizer=Anonymizer(LabelCounterPlaceholderFactory()),
    cache=cache,
    cache_ttl=3600,  # purger après 1 h sans usage
)
```

Tous les workers qui pointent sur le même Redis voient les mêmes mappings. Le `thread_id` reste l'unité d'isolation, et les conversations restent étanches entre utilisateurs.

### Avec Memcached

```python
from aiocache import MemcachedCache

cache = MemcachedCache(
    endpoint="memcached.internal",
    port=11211,
    namespace="piighost",
)
```

Les sémantiques sont les mêmes que Redis pour notre usage. Memcached évince automatiquement les entrées les moins récentes quand la mémoire est saturée, ce qui peut convenir si vous acceptez qu'une conversation idle assez longtemps perde son mapping.

---

## Cohérence avec LangGraph

Le piège n'est pas spécifique à `piighost`. LangGraph rencontre exactement le même problème avec son `checkpointer`, et propose `MemorySaver` (process-local, défaut) ou `PostgresSaver` / `RedisSaver` (partagé) pour les déploiements multi-instance. Si vous utilisez déjà un de ces savers, alignez le backend de `piighost` sur la même infrastructure.

```python
from langchain.agents import create_agent
from langgraph.checkpoint.redis import RedisSaver
from aiocache import RedisCache

# Réutilisez la même instance Redis pour les deux couches
checkpointer = RedisSaver.from_conn_string("redis://redis.internal:6379")
cache = RedisCache(endpoint="redis.internal", port=6379, namespace="piighost")

pipeline = ThreadAnonymizationPipeline(
    detector=...,
    anonymizer=...,
    cache=cache,
)
agent = create_agent(model="...", tools=[...], middleware=[...], checkpointer=checkpointer)
```

Garder les deux couches sur le même Redis garantit qu'un `thread_id` qui a un état checkpointé a aussi son mapping `placeholder ↔ PII` accessible, sur n'importe quel worker.

---

## Voir aussi

- [Pipeline conversationnel](getting-started/conversation.md) : usage de base de `ThreadAnonymizationPipeline`.
- [Sécurité](security.md) : modèle de menace et garanties offertes par le mapping cache.
- [Déploiement](deployment.md) : cache des wheels et stratégies pour `piighost-api`.
