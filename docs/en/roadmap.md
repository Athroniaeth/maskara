---
icon: lucide/list-checks
---

# Roadmap

This page tracks the improvements considered for PIIGhost. Items are
grouped by theme; a checked box means the item has shipped.

!!! note "How to read this page"
    This roadmap is not a calendar commitment. It reflects the
    evolution paths we have identified and their current status.

## Mapping security (placeholder ↔ PII)

The `placeholder ↔ PII` mapping is currently kept in cleartext inside
the configured `aiocache` backend. The work below strengthens the
guarantees offered when the backend itself is compromised.

- [ ] **Salt and pepper on placeholder hashing.** Today,
  `LabelHashPlaceholderFactory` and `FakerHashPlaceholderFactory`
  derive a deterministic SHA-256 from the PII. Over a small value
  space (first names, city names), an attacker can rebuild the
  reverse table with rainbow tables. Adding a per-instance salt and a
  global pepper would make the derivation non-replayable outside the
  process.

- [ ] **SQLAlchemy backend (aiosqlite + PostgreSQL).** The default
  cache is in-memory and process-bound. A SQLAlchemy backend would
  bring:
    - simple dev persistence through `aiosqlite`;
    - multi-worker sharing in production through PostgreSQL;
    - strict `thread_id` coherence across workers.

- [ ] **Mapping encryption at rest.** Inspired by LangChain's
  `PostgresStore`, the idea is to encrypt the mapping inside the
  library before handing it to the backend. If the database or the
  cache leaks, an attacker without the key recovers no PII. To
  investigate: feasibility, key-management model (env var, KMS,
  rotation), performance impact.

## Multi-instance deployment safeguards

The default cache (`SimpleMemoryCache`) is in-memory and process-bound.
It is an excellent default for development and single-instance
deployments, but in multi-instance setups behind a load balancer, the
`placeholder ↔ PII` mappings are not shared: the same `thread_id`
routed to two workers will see Patrick assigned to `<<PERSON:1>>` at
turn 1 and `<<PERSON:2>>` at turn 2, breaking placeholder consistency
mid-conversation.

- [ ] **Warning on first instantiation without an explicit backend.**
  Emit a `PIIGhostConfigWarning` (custom category, filterable through
  `warnings.filterwarnings`) once per process when
  `ThreadAnonymizationPipeline` is created without a shared backend.
  The message must speak to **correctness** (cross-worker placeholder
  consistency), not just performance, so the user understands the
  actual risk.

- [ ] **"Multi-instance deployment" page in the docs.** A dedicated
  section that explains the trap, shows the warning, and gives a
  copy-pasteable Redis example. Aligned with LangGraph's wording
  (`MemorySaver` vs `PostgresSaver` / `RedisSaver`) to speak directly
  to the LangChain audience.

## Post-anonymization validation

Once the pipeline runs, nothing currently guarantees that the
anonymized output is free of detectable PII: a misconfigured detector,
an entity missed by the NER, an unmatched placeholder can all let
data leak. The protocols below add an optional safety net at the end
of the pipeline.

- [ ] **`AnyGuardRail` protocol and implementations.** Final binary
  stage that re-runs a detection (strict regex, LLM, or any
  `AnyDetector`) on the anonymized text and raises a
  `PIIRemainingError` if anything is still identified. Minimal API,
  no threshold to tune. Planned implementations: `DetectorGuardRail`
  (reuses any `AnyDetector`), `LLMGuardRail` (small local LLM), and
  `DisabledGuardRail` as the default to stay consistent with the
  other pipeline stages.

- [ ] **`AnyRiskAssessor` protocol and implementations.** Optional
  stage that returns a continuous re-identification risk score
  (`0.0` to `1.0`) without acting on it: the user decides what to do
  with the score (log, block, re-run the pipeline with a stricter
  policy). More complex than `GuardRail` since it requires calibrating
  a threshold. To follow the `GuardRail` for high-stakes use cases
  (medical, legal, financial advice) where binary pass/fail is not
  enough. Usable at runtime or offline, at the user's discretion.

## Detection

PIIGhost orchestrates detectors without imposing any specific one.
The items below strengthen the quality and measurability of the
detection stage.

- [ ] **Public pipeline benchmarks.** Measure the overhead of
  PIIGhost itself (not of the underlying NER) on a reproducible
  corpus: per-stage latency, throughput vs. number of entities, cache
  impact (hit / miss ratio), p50 / p95 / p99 on a reference detector
  setup. The goal is to give users a numeric baseline to calibrate
  their SLAs and to surface performance regressions between releases.

- [ ] **`LLMDetector` improvements.** The current `LLMDetector`
  detects PII via an LLM prompt. Improvement directions: support for
  local LLMs (Ollama, llama.cpp, vLLM) to reduce cost and keep data
  in-house; strict structured output (JSON Schema, Pydantic) to make
  parsing reliable; disambiguator role inside a `CompositeDetector`
  (another detector proposes candidates, the LLM filters false
  positives like "Rose" the name vs. the flower by leveraging
  context). The LLM's global context is exactly what specialized NER
  models lack.

## Anonymization strategies

The current anonymization is binary (placeholder or cleartext value).
The items below open up intermediate behaviours suited to specific
use cases.

- [ ] **Differentiated deanonymization policies.** Three useful
  variants, selectable per label through an
  `AnyDeanonymizationPolicy` protocol (with `IdentityPolicy` as the
  default):
    - **Persistent pseudonymization**: instead of `<<PERSON:1>>`,
      return a stable Faker name across threads (Patrick → "Alex
      Martin" always). Lets data / analytics teams aggregate
      conversations without handling real PII.
    - **k-anonymity on sensitive values**: for numeric or
      categorical attributes (age, ZIP code, salary), return a bucket
      instead of the exact value: `34` → `30-39`, `75001` → `Paris`,
      `52340 €` → `[50k-60k]`.
    - **Differential privacy**: for numeric values exposed to an LLM
      that could aggregate them, add calibrated noise (Laplace,
      Gaussian). Use case: aggregated reporting where an
      individual's exact value is not needed.

- [ ] **`ToolPIIPolicy`: fine-grained policy per tool call.** Today,
  `awrap_tool_call` deanonymizes all tool arguments before execution,
  then re-anonymizes the result. This is binary and global. A
  declarative per-tool policy would unlock finer zero-trust
  architectures:
    - *Attribute whitelist*: this tool receives `name` and `email`,
      but not `phone`.
    - *Per-tool pseudonymization*: this tool receives a stable Faker
      value rather than the real one (useful for external CRMs where
      a stable trace is wanted without exposing the real customer).
    - *Result policy*: this tool may return cleartext content
      (public summary) without re-running detection.

  The API would look like a middleware argument:
  `PIIAnonymizationMiddleware(tool_policies={"send_email":
  ToolPolicy(reveal=["email"], hide=["phone"])})`.

## Integrations

- [ ] **Adapters beyond LangChain.** The middleware logic
  (anonymize before the LLM, deanonymize for the user, wrap tool
  calls) is isomorphic across frameworks. Targets:
    - **LlamaIndex**: integration via agent hooks.
    - **OpenAI Agents SDK**: `on_message_start` / `on_tool_call`
      hooks.
    - **Native Anthropic SDK**: interceptor on `messages.create`
      with `tool_use` handling.
    - **Pydantic AI**: middleware compatible with their graph
      runtime.
    - **DSPy**: wrapper module for pipelines.
    - **"Transparent HTTP proxy" mode**: generic request / response
      interceptor (httpx middleware, or proxy server) for agents
      that don't use any of these frameworks.

  The core (`AnonymizationPipeline`, `ConversationMemory`) stays
  identical, only the glue layer changes. To be shared in a
  separate package or behind extras (`piighost[llamaindex]`,
  `piighost[openai]`, etc.).

## Observability and progressive rollout

- [ ] **"Shadow" mode.** Read-only middleware that logs what it
  *would* have anonymized without modifying the messages. Lets teams
  integrate PIIGhost into a production agent risk-free during the
  calibration phase (label tuning, confidence threshold, detector
  selection). Phased implementation:
    - *Phase 1: Langfuse integration.* Log each detection as a
      Langfuse trace with score, label, position (without the
      cleartext value), and the placeholder that would have been
      applied. Lets a dashboard surface what the pipeline would do
      without affecting the agent.
    - *Phase 2: alerting system (optional).* Above a configurable
      threshold of PII detected per conversation, trigger an alert
      (webhook, Slack, email) for human review. Useful in regulated
      environments or to verify that a new detector does not
      silently regress.

- [ ] **Structured audit trail for compliance.** Logger without raw
  PII values that traces per message: number of PII detected,
  distribution by label, source detector, confidence score, value
  hash (to correlate without revealing). Different from shadow mode
  because this log runs in **production runtime**, not passively.
    - Structured format (JSON Lines, OpenTelemetry spans) for
      ingestion by any SIEM or observability platform.
    - Deterministic per-PII hash to allow aggregate analyses
      ("term X appears 47 times this month") without storing the
      value.
    - Coupling with the Langfuse traces from shadow mode for an
      end-to-end view.
    - "DPIA snippet" export: automatically generate the data flows
      needed for GDPR Article 35 audits.

## Robustness evaluation

- [ ] **Built-in adversarial evaluation (exploratory, low
  priority).** A "red team" mode that takes an anonymized
  conversation and actively tries to re-identify the person (via
  prompting an adversarial LLM, or via cross-referencing heuristics
  on quasi-identifiers). Returns a measured robustness score rather
  than a theoretical promise.

  Practical usefulness still needs validation: the `RiskAssessor`
  (planned in "Post-anonymization validation" above) covers most of
  the need with a single LLM call, while adversarial evaluation
  requires multiple adversarial passes, so significantly more costly
  for marginal gain. To be considered only for one-off compliance
  audits or public benchmarks, not for runtime use.

## See also

- [Security](security.md): current threat model and guarantees.
- [Deployment](deployment.md): cache configuration in production.
