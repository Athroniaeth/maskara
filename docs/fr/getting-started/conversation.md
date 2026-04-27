---
icon: lucide/messages-square
---

# Pipeline conversationnel

## Pourquoi pas juste `AnonymizationPipeline` ?

Le pipeline standard fonctionne sur un message isolé. Dans une conversation multi-messages, trois problèmes apparaissent :

- **Compteurs non partagés.** Chaque appel à `anonymize` repart de zéro. Le mapping `Patrick → <<PERSON:1>>`{ .placeholder } du message 1 n'est pas réutilisé au message 2.
- **Détections manquées entre messages.** Le NER détecte `Patrick`{ .pii } dans le message 1 mais le rate dans le message 5. Sans mémoire des entités déjà vues, on ne peut pas combler le trou.
- **Conversations concurrentes.** Si plusieurs utilisateurs partagent la même instance de pipeline, leurs entités se mélangent et leurs `<<PERSON:1>>`{ .placeholder } deviennent indiscernables.

Démonstration du bug avec le pipeline standard :

```python
# Avec un AnonymizationPipeline (sans mémoire de conversation)

m1, _ = await pipeline.anonymize("Patrick habite à Paris.")
# <<PERSON:1>> habite à <<LOCATION:1>>.

m2, _ = await pipeline.anonymize("Bob est content.")
# <<PERSON:1>> est content.   ← le compteur est reparti à 1
# Bob hérite donc du même placeholder que Patrick → collision :
# le LLM pense que c'est la même personne.
```

`ThreadAnonymizationPipeline` encapsule le pipeline de base avec une `ConversationMemory` pour accumuler les entités entre les messages et fournir désanonymisation / réanonymisation par remplacement de chaîne. La mémoire et le cache sont scopés par `thread_id`, ce qui isole chaque conversation et permet de réutiliser les entités déjà vues pour rester cohérent au fil des messages.

```python
import asyncio

from piighost.anonymizer import Anonymizer
from piighost.detector.gliner2 import Gliner2Detector
from piighost.linker.entity import ExactEntityLinker
from piighost.resolver import MergeEntityConflictResolver, ConfidenceSpanConflictResolver
from piighost.pipeline import AnonymizationPipeline, ThreadAnonymizationPipeline
from piighost.placeholder import LabelCounterPlaceholderFactory

from gliner2 import GLiNER2

entity_linker = ExactEntityLinker()
entity_resolver = MergeEntityConflictResolver()
span_resolver = ConfidenceSpanConflictResolver()

ph_factory = LabelCounterPlaceholderFactory()
anonymizer = Anonymizer(ph_factory=ph_factory)

model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")
detector = Gliner2Detector(
    model=model,
    threshold=0.5,
    labels=["PERSON", "LOCATION"],
)
pipeline = ThreadAnonymizationPipeline(
    detector=detector,
    span_resolver=span_resolver,
    entity_linker=entity_linker,
    entity_resolver=entity_resolver,
    anonymizer=anonymizer,
)


async def conversation():
    # Premier message : détection NER + enregistrement des entités
    # la pipeline garde en mémoire que l'entrée et la sortie sont liées,
    # et que <<PERSON:1>> correspond à "Patrick" et <<LOCATION:1>> à "Paris"
    anonymized, _ = await pipeline.anonymize("Patrick habite à Paris.")
    print(anonymized)
    # <<PERSON:1>> habite à <<LOCATION:1>>.

    # Désanonymisation via la correspondance stockée dans le cache de la pipeline
    restored = await pipeline.deanonymize("Bonjour <<PERSON:1>> !")
    print(restored)

    # Désanonymisation par remplacement de texte, utilisant les anciennes détections stockées en mémoire
    restored = await pipeline.deanonymize_with_ent("Bonjour <<PERSON:1>> !")
    print(restored)
    # Bonjour Patrick !

    # Réanonymisation par remplacement de texte, utilisant les anciennes détections stockées en mémoire
    reanon = pipeline.anonymize_with_ent("Résultat pour Patrick à Paris")
    print(reanon)
    # Résultat pour <<PERSON:1>> à <<LOCATION:1>>


asyncio.run(conversation())
```

??? info "Cache SHA-256"
    Le pipeline utilise aiocache avec des clés SHA-256. Si le même texte est soumis plusieurs fois, le résultat mis en cache est retourné sans appel au modèle NER.
