---
icon: lucide/shield-check
---

# Security

This page complements [`SECURITY.md`](https://github.com/Athroniaeth/piighost/blob/master/SECURITY.md) at the repo
root with a threat model: what `piighost` protects against, and what it does not.

## What `piighost` protects against

- **Exfiltration toward third-party LLMs**: the LLM only ever sees placeholders (`<<PERSON_1>>`, etc.), not the real
  PII. Even if the provider logs the request, no sensitive data is leaked.
- **Tool-call leakage**: the middleware deanonymizes tool arguments just before execution and re-anonymizes results
  before they go back to the LLM, so the real values never flow through the LLM's visible context.
- **Cross-message drift**: the cache links variants (`Patrick` / `patrick`) so the same entity keeps the same
  placeholder across the whole conversation, preventing the LLM from seeing the same PII under different masks.

## What `piighost` does not protect against

- **Local memory compromise**: the cache holds the mapping `placeholder -> real value` in memory (or in whatever
  backend you configured). An attacker with process memory access recovers the mapping in cleartext.
- **Disk theft of an unencrypted cache backend**: if you point `aiocache` at a Redis instance without disk
  encryption, and someone walks off with the disk, they walk off with the mapping. Encrypt backend storage.
- **LLM hallucinations**: if the LLM invents a PII that was never in the input, `piighost` cannot link it because
  it was never cached. See [Limitations](limitations.md) for mitigation.
- **Side-channel inference**: placeholders preserve the structure of the text. A determined adversary with partial
  knowledge could attempt to re-identify entities from context (rare, but not impossible).
- **Upstream access to logs**: `piighost` does not log raw PII, but your app might. Audit your own logging, tracing,
  and error reporting before claiming compliance.

## Design decisions that back the threat model

- **Anonymization happens locally**: PII is replaced before the HTTP request hits the LLM provider.
- **SHA-256 keyed cache**: placeholders are deterministically derived, not stored in plaintext under the placeholder
  label. Even a cache dump does not reveal which placeholder maps to which PII without the salt.
- **No logging of raw PII by the library**: `piighost` itself never writes PII to any logger. Your own code must
  follow the same discipline.
- **Frozen dataclasses**: `Entity`, `Detection`, `Span` are immutable, preventing accidental mutation after
  anonymization has been applied.

## Reporting a vulnerability

See [`SECURITY.md`](https://github.com/Athroniaeth/piighost/blob/master/SECURITY.md) for the private vulnerability
reporting channel and the supported-version matrix.
