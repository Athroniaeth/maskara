# piighost Sprint 4a — Feature Completeness Design

**Date:** 2026-04-20
**Scope:** Close the three known feature gaps so every documented config option works. Prerequisite for Sprint 4b (PyPI release) and Sprint 4c (MCP standalone + mcpb submission).

---

## Goals

1. `regex_only` detector backend: end `NotImplementedError`; produce a zero-dependency PII detector suitable for GDPR-structured entities.
2. `local` and `mistral` embedder backends: verified and wired in `build_embedder()` so users can opt out of the stub.
3. MCP `reveal` parameter: propagate caller intent through to service methods instead of forcing `False`.

## Non-goals

- NER-style entity types (names, locations, organizations) — those stay GLiNER-only.
- Presidio integration — we keep the regex engine in-house for licensing clarity and label-taxonomy control.
- PyPI release plumbing — that's Sprint 4b.
- MCP bundling / standalone packaging — that's Sprint 4c.

---

## 1. Architecture

```
src/piighost/
├── detector/
│   ├── regex.py                [NEW] RegexDetector + pattern registry
│   └── patterns/               [NEW] One module per entity type
│       ├── __init__.py         [re-exports DEFAULT_PATTERNS]
│       ├── _base.py            [Pattern dataclass]
│       ├── email.py
│       ├── phone.py
│       ├── ip.py
│       ├── credit_card.py      [with Luhn validator]
│       ├── iban.py             [with mod-97 validator]
│       ├── vat.py              [per-country format]
│       ├── date.py             [DOB variants]
│       └── national_id.py      [French NIR + German Personalausweis]
├── indexer/
│   ├── embedder.py             [MODIFY] build_embedder wires all backends
│   └── embedder_local.py       [NEW] LocalEmbedder (sentence-transformers)
├── service/
│   └── core.py                 [MODIFY] _build_default_detector routes "regex"
└── mcp/
    └── server.py               [FIX] reveal param propagated to vault_* calls
```

Each pattern module exports a single `Pattern` object. `RegexDetector` iterates the registered patterns, runs matches, filters via validators, and returns `Detection` objects — the same shape as the existing `Gliner2Detector`.

---

## 2. Regex detector

### 2.1 Pattern interface

```python
# src/piighost/detector/patterns/_base.py
from dataclasses import dataclass
from typing import Callable
import re

@dataclass(frozen=True)
class Pattern:
    label: str
    regex: re.Pattern[str]
    validator: Callable[[str], bool] | None = None
    confidence: float = 0.99
```

### 2.2 Entity coverage

| Label | Pattern source | Validator |
|-------|---------------|-----------|
| `EMAIL_ADDRESS` | RFC 5322 subset (local@domain) | — |
| `PHONE_NUMBER` | EU-leaning: `+\d{1,3}[ .-]?\d{1,4}(?:[ .-]?\d{2,4}){1,4}` | length 7–15 digits |
| `IP_ADDRESS` | IPv4 + IPv6 | octet range check for IPv4 |
| `CREDIT_CARD` | 13–19 digit run (optional spaces/hyphens) | Luhn mod-10 |
| `IBAN_CODE` | 2-letter country + 2 check digits + up to 30 alphanumerics | mod-97 == 1 |
| `EU_VAT` | Country prefix (AT, BE, …, FR, DE) + country-specific body | format-per-country |
| `DATE_TIME` | `DD/MM/YYYY`, `YYYY-MM-DD`, `DD.MM.YYYY`, `DD-MM-YYYY` | valid calendar date |
| `FR_NIR` | `[12]\d{2}(0[1-9]\|1[0-2])(?:\d{2}\|2A\|2B)\d{3}\d{3}\d{2}` | 97 − (NIR mod 97) == key |
| `DE_PERSONALAUSWEIS` | 10 alphanumerics (card number) | DE checksum algorithm |

Label taxonomy aligns with Presidio conventions so downstream tooling using either system sees the same names.

### 2.3 `RegexDetector`

```python
# src/piighost/detector/regex.py
from piighost.detector.patterns import DEFAULT_PATTERNS
from piighost.detector.patterns._base import Pattern
from piighost.models import Detection, Span


class RegexDetector:
    def __init__(self, patterns: list[Pattern] | None = None) -> None:
        self._patterns = patterns or DEFAULT_PATTERNS

    async def detect(self, text: str) -> list[Detection]:
        out: list[Detection] = []
        for pattern in self._patterns:
            for m in pattern.regex.finditer(text):
                matched = m.group(0)
                if pattern.validator and not pattern.validator(matched):
                    continue
                out.append(Detection(
                    text=matched,
                    label=pattern.label,
                    position=Span(start_pos=m.start(), end_pos=m.end()),
                    confidence=pattern.confidence,
                ))
        return _resolve_overlaps(out)


def _resolve_overlaps(detections: list[Detection]) -> list[Detection]:
    """Keep longest span on collision, preferring earlier start as tiebreaker."""
    detections.sort(key=lambda d: (d.position.start_pos, -(d.position.end_pos - d.position.start_pos)))
    accepted: list[Detection] = []
    for d in detections:
        if accepted and d.position.start_pos < accepted[-1].position.end_pos:
            continue
        accepted.append(d)
    return accepted
```

### 2.4 Wiring

In `src/piighost/service/core.py`, `_build_default_detector`:

```python
if config.detector.backend == "regex_only":
    from piighost.detector.regex import RegexDetector
    return RegexDetector()
```

The existing `regex_only` config value (already declared in `DetectorSection`) is the canonical name. No rename, no alias — just make the existing option work.

---

## 3. Embedder backend wiring

### 3.1 `LocalEmbedder`

```python
# src/piighost/indexer/embedder_local.py
from __future__ import annotations

class LocalEmbedder:
    """sentence-transformers wrapper. Requires `pip install piighost[index]`."""

    def __init__(self, model_name: str = "intfloat/multilingual-e5-base") -> None:
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(model_name)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import asyncio
        vectors = await asyncio.to_thread(self._model.encode, texts, convert_to_numpy=True)
        return [v.tolist() for v in vectors]
```

Model name defaults to `intfloat/multilingual-e5-base` to match the sister project (hacienda). Overridable via `ServiceConfig.embedder.local_model`.

### 3.2 `build_embedder` update

```python
# src/piighost/indexer/embedder.py
def build_embedder(section: EmbedderSection) -> Embedder:
    if os.environ.get("PIIGHOST_EMBEDDER") == "stub":
        return StubEmbedder()
    if section.backend == "local":
        from piighost.indexer.embedder_local import LocalEmbedder
        return LocalEmbedder(model_name=section.local_model)
    if section.backend == "mistral":
        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            raise RuntimeError("MISTRAL_API_KEY not set for mistral embedder")
        return MistralEmbedder(api_key=api_key, model=section.mistral_model)
    if section.backend == "stub":
        return StubEmbedder()
    raise NotImplementedError(f"embedder backend {section.backend!r}")
```

### 3.3 `EmbedderSection` fields

Add (if not already present):

```python
local_model: str = "intfloat/multilingual-e5-base"
mistral_model: str = "mistral-embed"
```

---

## 4. MCP `reveal` fix

In `src/piighost/mcp/server.py`, three call sites:

```python
# vault_list
return await svc.vault_list(limit=limit, offset=offset, reveal=reveal)

# vault_get
return await svc.vault_show(token=token, reveal=reveal)

# vault_search
return await svc.vault_search(query=query, reveal=reveal, limit=limit)
```

Each tool signature already accepts a `reveal: bool = False` argument; the fix is threading that value through to the service instead of hardcoding `False`.

---

## 5. Error handling

- `LocalEmbedder` raises at construction time if `sentence-transformers` is missing — clear `ImportError` with a hint to `pip install piighost[index]`.
- `MistralEmbedder` raises `RuntimeError` at `build_embedder` if `MISTRAL_API_KEY` is unset.
- `RegexDetector` never raises from `detect`; validators that crash on malformed input are caught and treated as validation failure (drop the match).
- Overlap resolution is deterministic; ties are broken by start position then length.

## 6. PII safety invariants (preserved)

- `RegexDetector` output flows through the same `Anonymizer`, so no raw PII in indexed chunks.
- `RegexDetector.detect` never logs raw matches. Only `type(exc).__name__` if a validator crashes.
- MCP `reveal=True` path writes an audit log entry (already implemented in `vault_show`); extend to `vault_search` and `vault_list` if missing.

---

## 7. Testing

| Layer | File | Coverage |
|-------|------|----------|
| Pattern unit tests | `tests/unit/detector/patterns/test_email.py` etc. | Positive match, negative, validator edge cases per pattern |
| `RegexDetector` | `tests/unit/detector/test_regex_detector.py` | Multi-pattern detect, overlap resolution |
| Detector wiring | `tests/unit/test_detector_wiring.py` | `_build_default_detector` routes `backend="regex_only"` correctly |
| `LocalEmbedder` | `tests/unit/indexer/test_local_embedder.py` | Smoke test (slow-marked), correct vector dim |
| `MistralEmbedder` | `tests/unit/indexer/test_mistral_embedder.py` | httpx-mocked request/response, API key validation, retry on 429/5xx |
| MCP reveal | `tests/unit/test_mcp_reveal.py` | `reveal=True` surfaces `original`, `reveal=False` leaves it `None`, audit log entry written |
| PII-zero-leak (extended) | existing `test_index_query_roundtrip.py::test_pii_zero_leak_to_mistral` | Already covers regex detector path when both are wired |

---

## 8. Acceptance criteria

- `ServiceConfig(detector=DetectorSection(backend="regex_only"))` produces a working detector that anonymizes email, phone, IP, credit card, IBAN, VAT, date, French NIR, German Personalausweis.
- `ServiceConfig(embedder=EmbedderSection(backend="local"))` loads `sentence-transformers` and returns 768-dim vectors.
- `ServiceConfig(embedder=EmbedderSection(backend="mistral"))` calls the Mistral API and returns 1024-dim vectors.
- MCP `vault_list`, `vault_get`, `vault_search` called with `reveal=True` return populated `original` fields.
- Full test suite (unit + e2e) passes with zero regressions from the current 86-test baseline.
- No `NotImplementedError` raised for any documented config option.

## 9. Out of scope for Sprint 4a

- CI/CD PyPI publishing (Sprint 4b)
- Standalone MCP server packaging (Sprint 4c)
- Rate limiting, circuit breaker, or caching for `MistralEmbedder` beyond basic retry
- Additional EU national ID formats (Spanish DNI, Italian Codice Fiscale, etc.) — add in Sprint 5 if demand emerges
- Postal address detection — stays GLiNER territory
