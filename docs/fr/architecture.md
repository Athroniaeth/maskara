---
icon: lucide/layers
---

# Architecture

PIIGhost est organise en couches distinctes : un **anonymiseur stateless** au coeur, encapsule dans un **pipeline** avec cache et resolution d'entites, etendu par un **pipeline conversationnel** avec memoire, adapte au monde LangChain via un **middleware**.

---

## Vue d'ensemble

```
┌─────────────────────────────────────────────────────────┐
│                  PIIAnonymizationMiddleware              │  ← Couche LangChain
│  abefore_model · aafter_model · awrap_tool_call         │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│            ConversationAnonymizationPipeline             │  ← Memoire & ops string
│  ConversationMemory · deanonymize_with_ent              │
│  · anonymize_with_ent                                   │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│                   AnonymizationPipeline                  │  ← Cache & orchestration
│  aiocache · detect_entities · anonymize · deanonymize   │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│                Protocoles composants                     │  ← Pipeline 5 etapes
│  Detect → Resolve Spans → Link → Resolve Entities       │
│  → Anonymize                                            │
└─────────────────────────────────────────────────────────┘
```

---

## Pipeline 5 etapes

Le coeur de PIIGhost est `AnonymizationPipeline` qui orchestre 5 etapes, chacune implementee par un protocole swappable.

```mermaid
---
title: "piighost AnonymizationPipeline.anonymize() flow"
---
flowchart LR
    classDef stage fill:#90CAF9,stroke:#1565C0,color:#000
    classDef protocol fill:#FFF9C4,stroke:#F9A825,color:#000
    classDef data fill:#A5D6A7,stroke:#2E7D32,color:#000

    INPUT(["`**Texte source**
    _'Patrick habite a Paris.
    Patrick aime Paris.'_`"]):::data

    DETECT["`**1. Detect**
    _AnyDetector_`"]:::stage
    RESOLVE_SPANS["`**2. Resolve Spans**
    _AnySpanConflictResolver_`"]:::stage
    LINK["`**3. Link Entities**
    _AnyEntityLinker_`"]:::stage
    RESOLVE_ENTITIES["`**4. Resolve Entities**
    _AnyEntityConflictResolver_`"]:::stage
    ANONYMIZE["`**5. Anonymize**
    _AnyAnonymizer_`"]:::stage

    OUTPUT(["`**Sortie**
    _'<<PERSON_1>> habite a <<LOCATION_1>>.
    <<PERSON_1>> aime <<LOCATION_1>>.'_`"]):::data

    INPUT --> DETECT
    DETECT -- "list[Detection]" --> RESOLVE_SPANS
    RESOLVE_SPANS -- "dedupliquees" --> LINK
    LINK -- "list[Entity]" --> RESOLVE_ENTITIES
    RESOLVE_ENTITIES -- "fusionnees" --> ANONYMIZE
    ANONYMIZE --> OUTPUT

    P_DETECT["`GlinerDetector
    _(GLiNER2 NER)_`"]:::protocol
    P_RESOLVE_SPANS["`ConfidenceSpanConflictResolver
    _(plus haute confiance gagne)_`"]:::protocol
    P_LINK["`ExactEntityLinker
    _(regex word-boundary)_`"]:::protocol
    P_RESOLVE_ENTITIES["`MergeEntityConflictResolver
    _(fusion union-find)_`"]:::protocol
    P_ANONYMIZE["`Anonymizer + CounterPlaceholderFactory
    _(tags <<LABEL_N>>)_`"]:::protocol

    P_DETECT -. "implemente" .-> DETECT
    P_RESOLVE_SPANS -. "implemente" .-> RESOLVE_SPANS
    P_LINK -. "implemente" .-> LINK
    P_RESOLVE_ENTITIES -. "implemente" .-> RESOLVE_ENTITIES
    P_ANONYMIZE -. "implemente" .-> ANONYMIZE
```

### Etape 1 Detect

`AnyDetector` execute la detection NER async sur le texte source et retourne une liste d'objets `Detection` (text, label, position, confidence).

Les implementations fournies incluent `GlinerDetector` (GLiNER2), `ExactMatchDetector` (regex word-boundary), `RegexDetector` (patterns), et `CompositeDetector` (chaine plusieurs detecteurs).

### Etape 2 Resolve Spans

`AnySpanConflictResolver` gere les detections qui se chevauchent en gardant celle avec la plus haute confiance.

### Etape 3 Link Entities

`AnyEntityLinker` etend et groupe les detections en objets `Entity`. `ExactEntityLinker` trouve toutes les occurrences de chaque texte detecte par recherche word-boundary et les groupe par texte normalise.

### Etape 4 Resolve Entities

`AnyEntityConflictResolver` fusionne les entites qui referent au meme PII. `MergeEntityConflictResolver` utilise un algorithme union-find pour fusionner les entites partageant des detections communes. `FuzzyEntityConflictResolver` fusionne les entites avec un texte canonique similaire via similarite Jaro-Winkler.

### Etape 5 Anonymize

`AnyAnonymizer` utilise un `AnyPlaceholderFactory` pour generer les tokens (`<<PERSON_1>>`, `<<LOCATION_1>>`) et effectue le remplacement par spans de droite a gauche.

---

## Flux middleware LangChain

Le `PIIAnonymizationMiddleware` intercepte le cycle de l'agent a 3 points cles.

```mermaid
---
title: "piighost PIIAnonymizationMiddleware dans la boucle agent"
---
sequenceDiagram
    participant U as Utilisateur
    participant M as Middleware
    participant L as LLM
    participant T as Outil

    U->>M: "Envoie un email a Patrick a Paris"
    M->>M: abefore_model()<br/>NER detect + anonymise
    M->>L: "Envoie un email a <<PERSON_1>> a <<LOCATION_1>>"
    L->>M: tool_call(send_email, to=<<PERSON_1>>)
    M->>M: awrap_tool_call()<br/>desanonymise les args
    M->>T: send_email(to="Patrick")
    T->>M: "Email envoye a Patrick"
    M->>M: awrap_tool_call()<br/>reanonymise le resultat
    M->>L: "Email envoye a <<PERSON_1>>"
    L->>M: "C'est fait ! Email envoye a <<PERSON_1>>."
    M->>M: aafter_model()<br/>desanonymise pour l'utilisateur
    M->>U: "C'est fait ! Email envoye a Patrick."
```

### `abefore_model`

Avant chaque appel LLM : execute `pipeline.anonymize()` sur tous les messages. Detection NER complete sur `HumanMessage`, reanonymisation sur `AIMessage` / `ToolMessage`.

### `aafter_model`

Apres chaque reponse LLM : desanonymise tous les messages. Essaie d'abord `pipeline.deanonymize()` (cache), puis `pipeline.deanonymize_with_ent()` (entites) en cas de `CacheMissError`.

### `awrap_tool_call`

Enveloppe chaque appel d'outil :

1. Desanonymise les arguments `str` avant l'execution → l'outil recoit les vraies valeurs
2. Execute l'outil
3. Reanonymise la reponse de l'outil → le LLM ne voit pas de vraies donnees

---

## Couche conversation `ConversationAnonymizationPipeline`

`ConversationAnonymizationPipeline` etend `AnonymizationPipeline` avec :

| Mecanisme | Description |
|-----------|-------------|
| **`ConversationMemory`** | Accumule les entites entre les messages, dedupliquees par `(text.lower(), label)` |
| **`deanonymize_with_ent()`** | Remplacement de chaine : tokens → valeurs originales (plus long d'abord) |
| **`anonymize_with_ent()`** | Remplacement de chaine : valeurs originales → tokens (plus long d'abord) |

---

## Modeles de donnees

Tous les modeles sont des **dataclasses gelees** (immutables, thread-safe) :

| Modele | Champs cles |
|--------|-------------|
| `Detection` | `text`, `label`, `position: Span`, `confidence` |
| `Entity` | `detections: tuple[Detection, ...]`, `label` (propriete) |
| `Span` | `start_pos`, `end_pos`, `overlaps()` |

---

## Injection de dependances

Chaque etape utilise un **protocole** (typage structurel Python) comme point d'injection :

```python
AnonymizationPipeline(
    detector=GlinerDetector(...),                    # AnyDetector
    span_resolver=ConfidenceSpanConflictResolver(),  # AnySpanConflictResolver
    entity_linker=ExactEntityLinker(),               # AnyEntityLinker
    entity_resolver=MergeEntityConflictResolver(),   # AnyEntityConflictResolver
    anonymizer=Anonymizer(CounterPlaceholderFactory()),  # AnyAnonymizer
)
```

Pour remplacer un composant, il suffit de fournir un objet implementant le protocole correspondant. Voir [Etendre PIIGhost](extending.md).
