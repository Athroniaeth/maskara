# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PIIGhost is a PII anonymization library for AI agent conversations. It transparently detects, anonymizes, and deanonymizes sensitive entities (names, locations, etc.) using GLiNER2 NER, with built-in LangChain middleware for seamless integration into LangGraph agents.

## Development Commands

```bash
uv sync                      # Install dependencies
make lint                    # Format (ruff), lint (ruff), type-check (pyrefly)
uv run pytest                # Run all tests
uv run pytest tests/test_anonymizer.py -k "test_name"  # Run a single test
```

## Architecture

### 5-Stage Anonymization Pipeline

`AnonymizationPipeline` (`pipeline.py`) orchestrates: **Detect → Resolve Spans → Link Entities → Resolve Entities → Anonymize**

1. **Detect**: `AnyDetector` protocol `GlinerDetector` runs GLiNER2 NER, `ExactMatchDetector` for tests, `RegexDetector` for patterns, `CompositeDetector` to chain detectors
2. **Resolve Spans**: `AnySpanConflictResolver` protocol `ConfidenceSpanConflictResolver` keeps highest-confidence detection when spans overlap
3. **Link Entities**: `AnyEntityLinker` protocol `ExactEntityLinker` finds all occurrences via word-boundary regex (`_expand`) and groups them (`_group`). Also provides `link_entities()` for cross-message linking
4. **Resolve Entities**: `AnyEntityConflictResolver` protocol `MergeEntityConflictResolver` (union-find) or `FuzzyEntityConflictResolver` (Jaro-Winkler)
5. **Anonymize**: `AnyAnonymizer` protocol `Anonymizer` uses `AnyPlaceholderFactory` (`CounterPlaceholderFactory` for `<<PERSON_1>>` tags) and applies span-based replacement

### Conversation Layer

`ThreadAnonymizationPipeline` (`pipeline/thread.py`) extends the base pipeline with:
- **Thread isolation**: memory and cache are scoped per `thread_id` (passed to each method, defaults to `"default"`)
- `ConversationMemory` accumulates entities across messages per thread, deduplicated by `(text.lower(), label)`, with `_add_variant()` to track case variants (e.g. "France" / "france")
- `link_entities()` on `ExactEntityLinker` links entities across messages so that "patrick" in message 2 shares the same placeholder as "Patrick" in message 1
- `deanonymize_with_ent()` / `anonymize_with_ent()` string-based token replacement for any text
- aiocache for detector result and anonymization mapping caching (SHA-256 keyed, prefixed by thread_id)

### Middleware Integration

`PIIAnonymizationMiddleware` (`middleware.py`) extends LangChain's `AgentMiddleware`:
- Extracts `thread_id` from LangGraph config via `get_config()["configurable"]["thread_id"]`
- `abefore_model` anonymizes all messages before the LLM sees them via `pipeline.anonymize(text, thread_id=...)`
- `aafter_model` deanonymizes for user display (cache-based, with `CacheMissError` fallback to entity-based)
- `awrap_tool_call` deanonymizes tool args, executes tool, re-anonymizes result via `pipeline.anonymize()`

### Design Patterns

All pipeline stages use **protocols** (structural subtyping) for dependency injection, making components swappable and testable. Tests use `ExactMatchDetector` to avoid loading the real GLiNER2 model.

## Conventions

- **Commits**: Conventional Commits via Commitizen (`feat:`, `fix:`, `refactor:`, etc.)
- **Type checking**: PyReFly (not mypy)
- **Formatting/linting**: Ruff
- **Package manager**: uv (not pip)
- **Python**: 3.12+
- **Data models**: Frozen dataclasses for immutability (`Entity`, `Detection`, `Span`)

## Example Application

An example LangGraph agent with PII middleware is available in `examples/graph/`. It includes Aegra deployment, FastAPI HTTP server, PostgreSQL, and Langfuse observability. See `examples/graph/README.md` for details.
