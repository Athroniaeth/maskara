# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 0.10.0 (2026-04-30)

### BREAKING CHANGE

- observe_raw_text was removed. Configure
observation_ph_factory= instead; pass any AnyPlaceholderFactory.

### Feat

- **observation**: add Opik backend for the observation service
- **observation**: redact via placeholder factory instead of [REDACT] sentinel
- **observation**: redact raw user text in observation payloads by default
- **observation**: abstract observation service + Langfuse impl
- **cache**: add SQLAlchemyCache backend for persistent / shared caches
- **guard**: add LLMGuardRail backed by a LangChain chat model
- **pipeline**: add guard-rail stage with DetectorGuardRail
- **placeholder**: add salt and pepper to hash placeholder factories
- **pipeline**: warn when ThreadAnonymizationPipeline uses unshared cache

### Fix

- **ci**: install sqlalchemy extra and skip tests when missing
- **observation**: use propagate_attributes for trace fields in Langfuse v4
- **deps**: include aiosqlite in the sqlalchemy extra

### Refactor

- **models**: drop Detection.__repr__ masking, use standard dataclass repr

## 0.9.1 (2026-04-26)

## 0.9.0 (2026-04-25)

### BREAKING CHANGE

- the four renames above plus the Counter separator
change. Update class imports, factory references, and any code that
parses ``<<LABEL_N>>`` tokens to expect ``<<LABEL:N>>``. The
RealisticHash strategy helpers (``hashed_email``, ``hashed_with_prefix``,
``hashed_template``) are removed; use base/template strings or the new
``fake_*`` callables.
- ConstantPlaceholderFactory (added in the previous
commit) is renamed to RedactPlaceholderFactory, and the existing
RedactPlaceholderFactory is renamed to LabelPlaceholderFactory.
Update imports and class references.
- HashPlaceholderFactory is renamed to
LabeledHashPlaceholderFactory. Update imports and class references.
- HashPlaceholderFactory and RedactPlaceholderFactory
now produce tokens wrapped in <<...>> instead of <...>. Any cache or
LLM prompt that referenced the old format will need to be cleared
or updated. The change is purely cosmetic: the cache mapping logic,
the type system, and the middleware constraint are unaffected.

### Feat

- **placeholder**: add Counter variants, restructure naming as Style+Mechanism
- **placeholder**: add Constant, AnonymousHash, RealisticHash factories; rename Hash
- **pipeline**: allow disabling NER compensator components
- **placeholder**: wrap Hash and Redact tokens in <<...>>
- **placeholder**: tag factories with preservation level for type-safe wiring
- **middleware**: add ToolCallStrategy for tool-call handling
- expose core Protocol types from the top-level package
- expose piighost.labels module with common PII label constants
- **pipeline**: bound ConversationMemory growth via LRU eviction
- **pipeline**: add cache_ttl parameter to bound cache entry lifetime

### Fix

- **lint**: resolve pyrefly errors across src, tests, and examples
- **tests**: replace re.NOFLAG with 0 for Python 3.10 compatibility
- **pipeline**: make ThreadAnonymizationPipeline thread_id propagation concurrency-safe

### Refactor

- **placeholder**: swap Constant and Redact factory names
- **placeholder**: split identity from label via multi-inheritance
- **placeholder**: turn preservation tags into an inheritance hierarchy
- **middleware**: expose tool_strategy as a public attribute
- replace @dataclass with explicit __init__ on behavior classes
- **models**: move Detection and Entity serialization into dataclasses
- **pipeline**: name cache key prefixes as module constants
- **similarity**: extract Jaro-Winkler magic numbers into named constants

### Perf

- **pipeline**: replace token loop with single-pass regex alternation
- **memory**: O(1) canonical lookup in ConversationMemory
- **chunked**: run chunk detections concurrently via asyncio.gather
- pre-compile regex patterns in hot paths

## 0.8.0 (2026-04-24)

### Feat

- **models**: mask raw PII text in Detection repr
- **detector**: add regex packs by region and checksum validators
- expose ExactMatchDetector publicly

### Fix

- **client**: use typing_extensions.Self on Python 3.10
- **test**: restrict pytest to tests/ to skip scripts/ demos

### Refactor

- **test**: drop the unused first setup in roundtrip length test

### Perf

- **test**: disable unused pytest plugins (anyio, faker, langsmith)
- **test**: exclude heavy-dep tests by default and enable asyncio auto mode

## 0.7.0 (2026-04-16)

### Feat

- add detect preview and detection override to pipeline and client

## 0.6.0 (2026-04-16)

### Feat

- add ChunkedDetector for long texts exceeding NER model context windows
- add LLMDetector for entity extraction via structured output
- add BaseNERDetector ABC with internal/external label mapping
- add base classes with min_text_length and confidence_threshold filtering

## 0.5.1 (2026-04-07)

### Fix

- skip ToolMessages in abefore/aafter_model, reject non-reversible factories

## 0.5.0 (2026-03-31)

### Feat

- add transformers detector for hugging face ner models
- add spacy detector for spacy NER model integration
- add piighost[all] optional group and dependency acceptance tests

### Fix

- raise DeanonymizationError instead of silently skipping missing tokens

## 0.4.2 (2026-03-30)

### Fix

- guard optional dependency imports (aiocache, faker, langgraph)

## 0.4.1 (2026-03-30)

### Fix

- impossible to use client because annotation are after import

## 0.4.0 (2026-03-30)

### Feat

- add async http client for piighost-api

## 0.3.0 (2026-03-29)

### Feat

- add cross-message entity linking via linker.link_entities
- add faker placeholder factory with configurable label-to-provider strategies
- add mask placeholder factory with configurable label-to-function masking strategies
- add mask placeholder factory for partial masking anonymization strategy

### Refactor

- extract _deanonymize helper and clean up middleware
- convert lambda assignments to def functions in tests
- reorganize tests directory to mirror src package structure
- create own module for each step of pipeline

## 0.2.0 (2026-03-28)

### Feat

- add cache-backed deanonymization with CacheMissError fallback and fix middleware await
- **v2**: add fuzzy entity resolution with jaro-winkler and levenshtein similarity
- **v2**: add conversation memory and conversation anonymization pipeline for cross-message deanonymization
- **v2**: add conversation memory and conversation anonymization pipeline for cross-message token consistency
- **v2**: add async anonymization pipeline with aiocache detector and deanonymization cache
- **v2**: add Anonymizer with placeholder factories (counter, hash, redact), make Entity frozen
- **v2**: add merge entity conflict resolver with union-find strategy
- **v2**: add entity model and exact entity linker for detection expansion and grouping
- **v2**: add span conflict resolver with confidence-based strategy
- **v2**: add detector with word-boundary regex matching
- **v2**: rework models of library
- add last work of claude code (full bullshit lmao)
- add RedactPlaceholderFactory with irreversible anonymization guard
- add pre-built PII regex detector examples for US and Europe

### Fix

- **v2**: resolve lint errors, fix tuple return types and default cache serialization

### Refactor

- **v2**: delete old code, set v2 to main package
- complete review of code, delete useless code
- **v2**: remove abstract base classes, keep protocol + implementation only
- extract PlaceholderRegistry from Pipeline, clarify Anonymizer statefulness and public API
- deduplicate pipeline/placeholder cache, fix types and dead code, dispatch AI/tool messages via reanonymize in abefore_model
- replace isinstance checks with polymorphic PlaceholderFactory hierarchy

## [0.1.0] - 2025-03-22

### Features

- **anonymizer**: 4-stage pipeline (Detect → Expand → Map → Replace) with protocol-based dependency injection
- **detector**: `GlinerDetector` using GLiNER2 NER for entity detection
- **occurrence-finder**: `RegexOccurrenceFinder` for word-boundary regex matching of all entity occurrences
- **placeholder-factory**: `CounterPlaceholderFactory` for stable `<<LABEL_N>>` tags
- **span-replacer**: `SpanReplacer` with reverse spans for reliable deanonymization
- **pipeline**: `AnonymizationPipeline` with `PlaceholderStore` protocol for cross-session caching (SHA-256 keyed)
- **middleware**: `PIIAnonymizationMiddleware` for LangChain/LangGraph hooks on `abefore_model`, `aafter_model`, `awrap_tool_call`
- **pipeline**: `deanonymize_value` for per-argument placeholder resolution
- **examples**: LangGraph + FastAPI example with React frontend and Aegra integration
