---
icon: lucide/layers
---

# Architecture

PIIGhost is organized in distinct layers: a **stateless anonymizer** at the core, wrapped in a **pipeline** with caching and entity resolution, extended by a **conversation pipeline** with memory, adapted to LangChain via a **middleware**.

---

## Overview

```mermaid
---
title: "piighost layered architecture"
---
flowchart TB
    classDef hook fill:#BBDEFB,stroke:#1565C0,color:#000
    classDef layer fill:#90CAF9,stroke:#1565C0,color:#000
    classDef core fill:#A5D6A7,stroke:#2E7D32,color:#000
    classDef protocol fill:#FFF9C4,stroke:#F9A825,color:#000
    classDef ext fill:#E1BEE7,stroke:#6A1B9A,color:#000

    subgraph MW ["PIIAnonymizationMiddleware : LangChain layer"]
        direction LR
        HBEF["abefore_model"]:::hook
        HAFT["aafter_model"]:::hook
        HTOOL["awrap_tool_call"]:::hook
    end

    subgraph THREAD ["ThreadAnonymizationPipeline : memory & string ops"]
        direction LR
        MEM["ConversationMemory"]:::layer
        DEANO_ENT["deanonymize_with_ent"]:::layer
        ANON_ENT["anonymize_with_ent"]:::layer
    end

    subgraph PIPE ["AnonymizationPipeline : cache & orchestration"]
        direction LR
        DETECT_API["detect_entities"]:::core
        ANON_API["anonymize"]:::core
        DEANON_API["deanonymize"]:::core
    end

    subgraph PROTO ["Component protocols : 5-stage pipeline"]
        direction LR
        P_DETECT["AnyDetector"]:::protocol
        P_SPANS["AnySpanConflictResolver"]:::protocol
        P_LINK["AnyEntityLinker"]:::protocol
        P_ENT["AnyEntityConflictResolver"]:::protocol
        P_ANON["AnyAnonymizer"]:::protocol
        P_DETECT --> P_SPANS --> P_LINK --> P_ENT --> P_ANON
    end

    CACHE[("aiocache")]:::ext
    LLM(["LLM provider"]):::ext
    TOOLS(["Agent tools"]):::ext

    HBEF --> MEM
    HAFT --> DEANO_ENT
    HTOOL --> ANON_ENT
    HTOOL --> DEANO_ENT

    MEM --> ANON_API
    DEANO_ENT --> DEANON_API
    ANON_ENT --> ANON_API

    ANON_API --> P_DETECT
    DETECT_API --> P_DETECT
    ANON_API <--> CACHE
    DEANON_API <--> CACHE

    MW <--> LLM
    MW <--> TOOLS
```

*Layered architecture: from protocol to LangChain middleware.*
{ .figure-caption }

---

## 5-stage pipeline

!!! tip "Everything is swappable"
    Each stage lives behind a protocol. See [Extending PIIGhost](extending.md) to plug your own detector, linker, resolver or factory.

The core of PIIGhost is `AnonymizationPipeline`, which orchestrates 5 stages each implemented by a swappable protocol.

```mermaid
---
title: "piighost AnonymizationPipeline.anonymize() flow"
---
flowchart LR
    classDef stage fill:#90CAF9,stroke:#1565C0,color:#000
    classDef protocol fill:#FFF9C4,stroke:#F9A825,color:#000
    classDef data fill:#A5D6A7,stroke:#2E7D32,color:#000

    INPUT(["`**Source text**
    _'Patrick lives in Paris.
    Patrick loves Paris.'_`"]):::data

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

    OUTPUT(["`**Output**
    _'<<PERSON:1>> lives in <<LOCATION:1>>.
    <<PERSON:1>> loves <<LOCATION:1>>.'_`"]):::data

    INPUT --> DETECT
    DETECT -- "list[Detection]" --> RESOLVE_SPANS
    RESOLVE_SPANS -- "deduplicated" --> LINK
    LINK -- "list[Entity]" --> RESOLVE_ENTITIES
    RESOLVE_ENTITIES -- "merged" --> ANONYMIZE
    ANONYMIZE --> OUTPUT

    P_DETECT["`GlinerDetector
    _(or RegexDetector, ExactMatchDetector, CompositeDetector…)_`"]:::protocol
    P_RESOLVE_SPANS["`ConfidenceSpanConflictResolver
    _(highest confidence wins)_`"]:::protocol
    P_LINK["`ExactEntityLinker
    _(word-boundary regex)_`"]:::protocol
    P_RESOLVE_ENTITIES["`MergeEntityConflictResolver
    _(union-find merge)_`"]:::protocol
    P_ANONYMIZE["`Anonymizer + LabelCounterPlaceholderFactory
    _(<<LABEL:N>> tags)_`"]:::protocol

    P_DETECT -. "implements" .-> DETECT
    P_RESOLVE_SPANS -. "implements" .-> RESOLVE_SPANS
    P_LINK -. "implements" .-> LINK
    P_RESOLVE_ENTITIES -. "implements" .-> RESOLVE_ENTITIES
    P_ANONYMIZE -. "implements" .-> ANONYMIZE
```

### Stage 1 Detect

`AnyDetector` runs async NER detection on the source text and returns a list of `Detection` objects (text, label, position, confidence).

The provided implementations include `ExactMatchDetector` (word-boundary regex), `RegexDetector` (pattern-based), `GlinerDetector` (NER), and `CompositeDetector` (chains multiple detectors).

### Stage 2 Resolve Spans

`AnySpanConflictResolver` handles overlapping detections by keeping the highest-confidence detection when spans overlap.

### Stage 3 Link Entities

`AnyEntityLinker` expands and groups detections into `Entity` objects. `ExactEntityLinker` finds all occurrences of each detected text using word-boundary search and groups them by normalized text.

### Stage 4 Resolve Entities

`AnyEntityConflictResolver` merges entities that refer to the same PII. `MergeEntityConflictResolver` uses a union-find algorithm to merge entities sharing common detections. `FuzzyEntityConflictResolver` merges entities with similar canonical text using Jaro-Winkler similarity.

### Stage 5 Anonymize

`AnyAnonymizer` uses a `AnyPlaceholderFactory` to generate tokens (`<<PERSON:1>>`, `<<LOCATION:1>>`) and performs span-based replacement from right to left.

---

## LangChain middleware flow

`PIIAnonymizationMiddleware` intercepts the agent loop at 3 key points.

```mermaid
---
title: "piighost PIIAnonymizationMiddleware in the agent loop"
---
sequenceDiagram
    participant U as User
    participant M as Middleware
    participant L as LLM
    participant T as Tool

    U->>M: "Send an email to Patrick in Paris"
    M->>M: abefore_model()<br/>NER detect + anonymize
    M->>L: "Send an email to <<PERSON:1>> in <<LOCATION:1>>"
    L->>M: tool_call(send_email, to=<<PERSON:1>>)
    M->>M: awrap_tool_call()<br/>deanonymize args
    M->>T: send_email(to="Patrick")
    T->>M: "Email sent to Patrick"
    M->>M: awrap_tool_call()<br/>reanonymize result
    M->>L: "Email sent to <<PERSON:1>>"
    L->>M: "Done! Email sent to <<PERSON:1>>."
    M->>M: aafter_model()<br/>deanonymize for user
    M->>U: "Done! Email sent to Patrick."
```

### `abefore_model`

Before each LLM call: runs `pipeline.anonymize()` on all messages. This performs full NER detection on `HumanMessage` content and re-anonymizes `AIMessage` / `ToolMessage` content via string replacement.

### `aafter_model`

After each LLM response: deanonymizes all messages. First tries cache-based `pipeline.deanonymize()`, falls back to entity-based `pipeline.deanonymize_with_ent()` on `CacheMissError`.

### `awrap_tool_call`

Wraps each tool call:

1. Deanonymizes `str` arguments before execution → the tool receives real values
2. Executes the tool
3. Reanonymizes the tool response → the LLM never sees personal data

---

## Conversation layer `ThreadAnonymizationPipeline`

`ThreadAnonymizationPipeline` extends `AnonymizationPipeline` with:

| Mechanism | Description |
|-----------|-------------|
| **`ConversationMemory`** | Accumulates entities across messages, deduplicating by `(text.lower(), label)` |
| **`deanonymize_with_ent()`** | String replacement: tokens → original values (longest-first) |
| **`anonymize_with_ent()`** | String replacement: original values → tokens (longest-first) |

```python
# Entities persist across messages
anonymized_1, _ = await conv_pipeline.anonymize("Patrick lives in Paris.")
anonymized_2, _ = await conv_pipeline.anonymize("Tell me about Patrick.")
# Both use <<PERSON:1>> for "Patrick"

# String-based deanonymization on any text
await conv_pipeline.deanonymize_with_ent("Hello <<PERSON:1>>")
# → "Hello Patrick"
```

### PII lifecycle

From a single PII's point of view, here are the states it flows through between initial detection and the user-facing display, and the transitions available (first pass, cache hit, deanonymization).

<figure markdown="1">

```mermaid
flowchart TB
    classDef state fill:#90CAF9,stroke:#1565C0,color:#000
    classDef cache fill:#FFF9C4,stroke:#F9A825,color:#000
    classDef terminal fill:#E1BEE7,stroke:#6A1B9A,color:#000

    START([Raw text]):::terminal
    DET[Detected]:::state
    VAL[Validated]:::state
    LINK[Grouped into Entity]:::state
    MERGE[Consolidated]:::state
    ANON[Anonymized]:::state
    CACHE[("Cached
    _thread_id scope_")]:::cache
    REST[Restored]:::state
    END([Restored text]):::terminal

    START -->|AnyDetector NER / regex| DET
    DET -->|Resolve Spans| VAL
    VAL -->|Link Entities| LINK
    LINK -->|Resolve Entities| MERGE
    MERGE -->|placeholder factory| ANON
    ANON -->|store SHA-256 key| CACHE
    CACHE -.->|cache hit, same thread| ANON
    ANON -->|deanonymize| REST
    REST --> END
```

<figcaption>PII lifecycle across the pipeline and the conversation cache.</figcaption>

</figure>

`ConversationMemory` shares the mapping of an entity across the whole conversation identified by a `thread_id`. A second message containing the same PII jumps straight to `Anonymized` via the cache, without going through the NER detector again.

---

## Data models

All models are **frozen dataclasses** (immutable, thread-safe):

| Model | Key fields |
|-------|------------|
| `Detection` | `text`, `label`, `position: Span`, `confidence` |
| `Entity` | `detections: tuple[Detection, ...]`, `label` (property) |
| `Span` | `start_pos`, `end_pos`, `overlaps()` method |

---

## Dependency injection

Every stage uses a **protocol** (Python structural subtyping) as its injection point:

```python
detector = GlinerDetector(...)                    # AnyDetector
span_resolver = ConfidenceSpanConflictResolver()  # AnySpanConflictResolver
entity_linker = ExactEntityLinker()               # AnyEntityLinker
entity_resolver = MergeEntityConflictResolver()   # AnyEntityConflictResolver
anonymizer = Anonymizer(ph_factory=LabelCounterPlaceholderFactory())  # AnyAnonymizer

pipeline = AnonymizationPipeline(
    detector=detector,
    span_resolver=span_resolver,
    entity_linker=entity_linker,
    entity_resolver=entity_resolver,
    anonymizer=anonymizer,
)
```

To replace a component, simply provide an object that implements the corresponding protocol. See [Extending PIIGhost](extending.md).
