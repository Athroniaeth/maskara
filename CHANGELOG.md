# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 0.8.0 (2026-04-20)

### Feat

- add PIIGhostService stateful core with anonymize, rehydrate, detect, vault ops
- add CLI commands: init, anonymize, rehydrate, detect, index, query, vault, serve, daemon
- add JSON Lines CLI output with exit-code taxonomy and Rich renderer
- add daemon with Starlette JSON-RPC, bearer-token auth, auto-spawn lifecycle
- add document ingestion (Kreuzberg), sliding-window chunker, embedder hierarchy
- add ChunkStore over LanceDB with meta-mode fallback and BM25Index with RRF fusion
- add vault_search with LIKE query over encrypted originals
- add FastMCP server with 10 tools and 3 resources
- add piighost rm and piighost index-status commands
- add --force flag on piighost index
- add schema v2: indexed_files table with content-hash doc_id and mtime tracking
- add incremental index_path — skip unchanged files, reindex on mtime change
- add PIIGhostService.remove_doc and index_status methods
- add regex_only detector backend with 10 EU-focused PII patterns
- add EMAIL_ADDRESS, PHONE_NUMBER, IP_ADDRESS (v4/v6) regex patterns
- add CREDIT_CARD (Luhn), IBAN_CODE (mod-97), EU_VAT patterns
- add DATE_TIME (calendar-validated), FR_NIR (key-validated), DE_PERSONALAUSWEIS patterns

### Fix

- propagate reveal parameter in MCP vault_list instead of hardcoded False
- MistralEmbedder fails fast when MISTRAL_API_KEY is missing
- BM25 rebuild on deletion-only index_path runs
- resolve paths in index_path so API and CLI agree on stored file_path
- safe removal order in remove_doc (vault before LanceDB)
- delete_doc_entities on content change prevents orphaned entity rows
- validate doc_id format before LanceDB string interpolation
- redact exception message in index_path errors (PII safety)

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
