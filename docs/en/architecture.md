---
icon: lucide/layers
---

# Architecture

PIIGhost is organized in distinct layers: a **stateless anonymizer** at the core, wrapped in a **pipeline** with caching and entity resolution, extended by a **conversation pipeline** with memory, adapted to LangChain via a **middleware**.

---

## Overview

```
┌─────────────────────────────────────────────────────────┐
│                  PIIAnonymizationMiddleware              │  ← LangChain layer
│  abefore_model · aafter_model · awrap_tool_call         │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│            ThreadAnonymizationPipeline             │  ← Memory & string ops
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
│               Component protocols                        │  ← 5-stage pipeline
│  Detect → Resolve Spans → Link → Resolve Entities       │
│  → Anonymize                                            │
└─────────────────────────────────────────────────────────┘
```

---

## 5-stage pipeline

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
    _'<<PERSON_1>> lives in <<LOCATION_1>>.
    <<PERSON_1>> loves <<LOCATION_1>>.'_`"]):::data

    INPUT --> DETECT
    DETECT -- "list[Detection]" --> RESOLVE_SPANS
    RESOLVE_SPANS -- "deduplicated" --> LINK
    LINK -- "list[Entity]" --> RESOLVE_ENTITIES
    RESOLVE_ENTITIES -- "merged" --> ANONYMIZE
    ANONYMIZE --> OUTPUT

    P_DETECT["`GlinerDetector
    _(GLiNER2 NER)_`"]:::protocol
    P_RESOLVE_SPANS["`ConfidenceSpanConflictResolver
    _(highest confidence wins)_`"]:::protocol
    P_LINK["`ExactEntityLinker
    _(word-boundary regex)_`"]:::protocol
    P_RESOLVE_ENTITIES["`MergeEntityConflictResolver
    _(union-find merge)_`"]:::protocol
    P_ANONYMIZE["`Anonymizer + CounterPlaceholderFactory
    _(<<LABEL_N>> tags)_`"]:::protocol

    P_DETECT -. "implements" .-> DETECT
    P_RESOLVE_SPANS -. "implements" .-> RESOLVE_SPANS
    P_LINK -. "implements" .-> LINK
    P_RESOLVE_ENTITIES -. "implements" .-> RESOLVE_ENTITIES
    P_ANONYMIZE -. "implements" .-> ANONYMIZE
```

### Stage 1 Detect

`AnyDetector` runs async NER detection on the source text and returns a list of `Detection` objects (text, label, position, confidence).

The provided implementations include `GlinerDetector` (wraps GLiNER2), `ExactMatchDetector` (word-boundary regex), `RegexDetector` (pattern-based), and `CompositeDetector` (chains multiple detectors).

### Stage 2 Resolve Spans

`AnySpanConflictResolver` handles overlapping detections by keeping the highest-confidence detection when spans overlap.

### Stage 3 Link Entities

`AnyEntityLinker` expands and groups detections into `Entity` objects. `ExactEntityLinker` finds all occurrences of each detected text using word-boundary search and groups them by normalized text.

### Stage 4 Resolve Entities

`AnyEntityConflictResolver` merges entities that refer to the same PII. `MergeEntityConflictResolver` uses a union-find algorithm to merge entities sharing common detections. `FuzzyEntityConflictResolver` merges entities with similar canonical text using Jaro-Winkler similarity.

### Stage 5 Anonymize

`AnyAnonymizer` uses a `AnyPlaceholderFactory` to generate tokens (`<<PERSON_1>>`, `<<LOCATION_1>>`) and performs span-based replacement from right to left.

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
    M->>L: "Send an email to <<PERSON_1>> in <<LOCATION_1>>"
    L->>M: tool_call(send_email, to=<<PERSON_1>>)
    M->>M: awrap_tool_call()<br/>deanonymize args
    M->>T: send_email(to="Patrick")
    T->>M: "Email sent to Patrick"
    M->>M: awrap_tool_call()<br/>reanonymize result
    M->>L: "Email sent to <<PERSON_1>>"
    L->>M: "Done! Email sent to <<PERSON_1>>."
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
# Both use <<PERSON_1>> for "Patrick"

# String-based deanonymization on any text
await conv_pipeline.deanonymize_with_ent("Hello <<PERSON_1>>")
# → "Hello Patrick"
```

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
anonymizer = Anonymizer(ph_factory=CounterPlaceholderFactory())  # AnyAnonymizer

pipeline = AnonymizationPipeline(
    detector=detector,
    span_resolver=span_resolver,
    entity_linker=entity_linker,
    entity_resolver=entity_resolver,
    anonymizer=anonymizer,
)
```

To replace a component, simply provide an object that implements the corresponding protocol. See [Extending PIIGhost](extending.md).
