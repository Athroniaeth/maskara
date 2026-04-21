---
icon: lucide/book-a
---

# Glossary

Key terms used throughout the `piighost` documentation. Keep this page open if you are new to the library or to NER.

## PII

**P**ersonally **I**dentifiable **I**nformation. Any piece of data that can identify a person: name, address, phone
number, email, location, organization, account number. `piighost` detects and anonymizes PII so that third-party
LLMs never see the raw values.

## LLM

**L**arge **L**anguage **M**odel. A neural network trained on large text corpora to generate or reason about text
(GPT, Claude, Gemini, Mistral, etc.). In this project, an LLM is the downstream consumer that should only receive
anonymized input.

## NER

**N**amed **E**ntity **R**ecognition. A machine-learning task that finds named entities (persons, locations,
organizations, dates, etc.) in text. `piighost` uses [GLiNER2](https://github.com/fastino-ai/gliner2) as its default
NER backend through the `GlinerDetector` class.

## Detector

A component that finds PII in text. Detectors implement the `AnyDetector` protocol. Built-in implementations:
`GlinerDetector` (NER), `RegexDetector` (patterns), `ExactMatchDetector` (fixed dictionary), `CompositeDetector`
(chain of detectors).

## Span

An interval of character positions inside a text: `(start_pos, end_pos)`. Each detection carries a `Span` to pinpoint
where the PII appears. Overlapping spans from multiple detectors are resolved by the span resolver.

## Detection

The output of a detector: a `(text, label, span, confidence)` tuple. For example, detecting `"Patrick"` as `PERSON`
at position `(0, 7)` with confidence `0.95` produces one `Detection`.

## Entity

A logical PII that may appear multiple times in the text. Produced by the entity linker by grouping related
detections (typo variants, case variants, partial mentions). Different from a `Detection`, which is one spotted
occurrence.

## Entity linking

The step that groups detections referring to the same real-world PII. For example, linking `"Patrick"` at position
`(0, 7)` and `"patrick"` at position `(34, 41)` into one `Entity`, so both occurrences share the same placeholder.

## Placeholder

The token that replaces a PII in the anonymized text. Defaults look like `<<PERSON_1>>`, `<<LOCATION_1>>`. The
naming strategy is controlled by a `PlaceholderFactory` (counter-based, UUID, hashed, redacted, masked).

## Pipeline

The 5-stage orchestration that transforms raw text into anonymized text: Detect, Resolve Spans, Link Entities,
Resolve Entities, Anonymize. Implemented by `AnonymizationPipeline` (stateless) and `ThreadAnonymizationPipeline`
(conversation-scoped).

## Resolver

A component that arbitrates conflicts. Two kinds: `SpanConflictResolver` (overlapping detections) and
`EntityConflictResolver` (linked entity groups that share a mention).

## Middleware

A LangChain extension point that runs before and after every LLM call and every tool call. `PIIAnonymizationMiddleware`
hooks into it to intercept and transform messages, so anonymization applies without changing agent code.

## Thread

A conversation scope identified by a `thread_id`. Memory and cache are isolated per thread so two parallel
conversations do not share PII state.
