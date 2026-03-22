# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PIIGhost is a PII anonymization system for AI agent conversations. It transparently intercepts LLM interactions to detect, anonymize, and deanonymize sensitive entities (names, locations, etc.) using GLiNER2 NER, integrated via LangChain middleware into a LangGraph agent. Built on Aegra (self-hosted LangSmith alternative).

## Development Commands

```bash
uv sync                      # Install dependencies
uv run aegra dev             # Start dev server (graph + FastAPI on port 8000)
make lint                    # Format (ruff), lint (ruff), type-check (pyrefly)
uv run pytest                # Run all tests
uv run pytest tests/test_anonymizer.py -k "test_name"  # Run a single test
docker compose up postgres -d                           # PostgreSQL only
docker compose up --build                               # Full stack (Postgres + API)
```

## Architecture

### 4-Stage Anonymization Pipeline

`Anonymizer` (`anonymizer/anonymizer.py`) orchestrates: **Detect → Expand → Map → Replace**

1. **Detect**: `EntityDetector` protocol — `GlinerDetector` runs GLiNER2 NER to find entities
2. **Expand**: `OccurrenceFinder` protocol — `RegexOccurrenceFinder` locates all occurrences via word-boundary regex
3. **Map**: `PlaceholderFactory` protocol — `CounterPlaceholderFactory` assigns stable tags (`<<PERSON_1>>`)
4. **Replace**: `SpanReplacer` applies character-position substitutions with reverse spans for deanonymization

### Session Layer

`AnonymizationPipeline` (`pipeline.py`) wraps the stateless `Anonymizer` with:
- `PlaceholderStore` protocol — async persistent cache (SHA-256 keyed) for cross-session placeholder reuse
- In-memory registry for fast bidirectional lookup within a session

### Middleware Integration

`PIIAnonymizationMiddleware` (`middleware.py`) extends LangChain's `AgentMiddleware`:
- `abefore_model` — anonymizes all messages before the LLM sees them (NER on human messages, string-replace on AI/tool)
- `aafter_model` — deanonymizes for user display
- `awrap_tool_call` — deanonymizes tool args, executes tool, re-anonymizes result

### Entry Points

- **LangGraph agent**: `graph.py:graph` — agent with tools (`send_email`, `get_weather`) and PII middleware
- **FastAPI app**: `app.py:app` — HTTP server with Keyshield API key auth and TTL sweeper background task
- **Config**: `aegra.json` binds both together for `aegra dev`

### Design Patterns

All pipeline stages use **protocols** (structural subtyping) for dependency injection, making components swappable and testable. Tests use `FakeDetector` to avoid loading the real GLiNER2 model.

## Conventions

- **Commits**: Conventional Commits via Commitizen (`feat:`, `fix:`, `refactor:`, etc.)
- **Type checking**: PyReFly (not mypy)
- **Formatting/linting**: Ruff
- **Package manager**: uv (not pip)
- **Python**: 3.12+
- **Data models**: Frozen dataclasses for immutability (`Entity`, `Placeholder`, `Span`, etc.)

## Environment Setup

Copy `.env.example` to `.env`. Key variables:
- `OPENAI_API_KEY` (or `ANTHROPIC_API_KEY`) — required for LLM
- `AEGRA_CONFIG=aegra.json` — mandatory
- Database: PostgreSQL connection fields or `DATABASE_URL`
- Observability: `OTEL_TARGETS` for Langfuse/Phoenix/OTLP tracing
