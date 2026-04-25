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

## See also

- [Security](security.md): current threat model and guarantees.
- [Deployment](deployment.md): cache configuration in production.
