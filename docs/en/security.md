---
icon: lucide/shield-check
---

# Security

This page complements [`SECURITY.md`](https://github.com/Athroniaeth/piighost/blob/master/SECURITY.md) at the repo
root with a threat model: what `piighost` protects against, and what it does not.

## What `piighost` protects against

!!! success "Within the protection scope"
    - **Exfiltration toward third-party LLMs**: the LLM only ever sees placeholders (`<<PERSON:1>>`{ .placeholder },
      etc.), not the real PII. Even if the provider logs the request, no sensitive data is leaked.
    - **Tool-call leakage**: the middleware deanonymizes tool arguments just before execution and re-anonymizes
      results before they go back to the LLM, so the real values never flow through the LLM's visible context.
    - **Cross-message drift**: the cache links variants (`Patrick`{ .pii } / `patrick`{ .pii }) so the same entity
      keeps the same placeholder across the whole conversation, preventing the LLM from seeing the same PII
      under different masks.

## What `piighost` does not protect against

!!! danger "Outside the protection scope"
    - **Local memory compromise**: the cache holds the mapping `placeholder -> real value` in memory (or in
      whatever backend you configured). An attacker with process memory access recovers the mapping in cleartext.
    - **Disk theft of an unencrypted cache backend**: if you point `aiocache` at a Redis instance without disk
      encryption, and someone walks off with the disk, they walk off with the mapping. Encrypt backend storage.
    - **LLM hallucinations**: if the LLM invents a PII that was never in the input, `piighost` cannot link it
      because it was never cached. See [Limitations](limitations.md) for mitigation.
    - **Side-channel inference**: placeholders preserve the structure of the text. A determined adversary with
      partial knowledge could attempt to re-identify entities from context (rare, but not impossible).
    - **Upstream access to logs**: `piighost` does not log raw PII, but your app might. Audit your own logging,
      tracing, and error reporting before claiming compliance.

## Logging discipline for PII-bearing dataclasses

The `Detection` dataclass holds the raw PII surface form in its `text`
field. The dataclass-generated `__repr__` renders that value verbatim,
which keeps the API predictable for inspection, debugging, and tests:

```python
>>> from piighost.models import Detection, Span
>>> d = Detection(text="Patrick", label="PERSON", position=Span(0, 7), confidence=0.9)
>>> repr(d)
"Detection(text='Patrick', label='PERSON', position=Span(start_pos=0, end_pos=7), confidence=0.9)"
```

The library deliberately does not auto-mask the field. If you forward
`Detection` or `Entity` instances to logs, traces, or error reporters,
scrub them yourself. Two simple recipes:

- Filter `to_dict()` before serialization (drop the `text` key).
- Wrap your structured logger with a redactor that recognises
  `Detection` and replaces `text` with a length marker.

`piighost` itself never writes PII to any logger; the discipline above
is needed in your own code.

## Observation payload redaction

When the pipeline is wired to an `AbstractObservationService` (for
example `LangfuseObservationService`), each stage emits a child
observation with its own `input` and `output`. The pipeline runs a
dedicated placeholder factory on every PII span before the payload
reaches the backend. The default is `RedactPlaceholderFactory()`,
which collapses every entity to `<<REDACT>>`:

```text
user text             : "Patrick lives in Paris."
observation payload   : "<<REDACT>> lives in <<REDACT>>."
```

Concretely:

- the root span's `input`, the `detect` stage's `input`, and the
  `placeholder` stage's `input` are filled with the text rendered by
  the factory once detection has run. Until detection produces a
  reliable mapping the root span has no `input` at all, so nothing
  leaks early,
- `Detection` and `Entity` records serialized into `detect.output`
  and `link.input/output` carry the factory's token instead of their
  `text` field. Label, position, and confidence stay visible for
  debugging,
- already-anonymized payloads (`placeholder.output`, `guard.input/output`,
  the root span's `output`) pass through unchanged because they
  contain placeholders only.

This default protects user input even when the pipeline fails before
producing the final anonymized text. A crash at the `link` or
`placeholder` stage cannot leak raw PII to Langfuse, because every
payload pushed so far already carries observation placeholders.

To surface more structure (for example a distinct counter per PII
during local development), pass a different factory to the
constructor:

```python
from piighost.placeholder import RedactCounterPlaceholderFactory

pipeline = ThreadAnonymizationPipeline(
    detector=detector,
    anonymizer=anonymizer,
    observation=LangfuseObservationService(client),
    observation_ph_factory=RedactCounterPlaceholderFactory(),  # <<REDACT:1>>, <<REDACT:2>>, ...
)
```

Any `AnyPlaceholderFactory` implementation is accepted. The
observation factory is independent from the one used for actual
anonymization, so you can display `<<PERSON:1>>` on Langfuse while
keeping a Faker-generated fake name in the prompt sent to the LLM.

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
