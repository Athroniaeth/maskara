# Chunked Detector Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure whether `ChunkedDetector` improves NER quality over a plain NER detector, via grid search over `(chunk_size, overlap, threshold)`, on `ai4privacy/pii-masking-300k` across all 6 supported languages.

**Architecture:** Extend the existing `benchmarks/` suite (branch `benchmark`) with a `benchmarks/chunking/` subpackage: pure-function modules for grid iteration, length bucketing, synthetic long-text generation, and winner selection; a grid runner that loads each detector model once and reuses detections across thresholds via post-hoc filtering; a markdown reporter; and a CLI.

**Tech Stack:** Python 3.12+, `uv`, `pytest`, `pytest-asyncio`, `datasets` (HuggingFace), `gliner2`, `transformers`, existing `piighost` detectors.

**Spec:** `docs/superpowers/specs/2026-04-22-chunked-detector-benchmark-design.md`

---

## File Structure

```
benchmarks/                              # pre-existing (branch `benchmark`)
├── __init__.py
├── __main__.py
├── dataset.py                           # load_samples, BenchmarkSample, GoldAnnotation
├── label_map.py                         # GLINER2_MAP, TRANSFORMERS_MAP, map_label
├── metrics.py                           # compute_detection_metrics, MatchMode
├── runner.py                            # existing run_benchmark (single-config)
├── report.py                            # existing formatters
├── run_all.py                           # existing multi-language driver
│
├── chunking/                            # NEW subpackage
│   ├── __init__.py
│   ├── __main__.py                      # CLI `python -m benchmarks.chunking`
│   ├── grid.py                          # iterate_grid(), GridConfig
│   ├── buckets.py                       # bucket_of(), BUCKET_ORDER
│   ├── synthetic.py                     # concat_samples()
│   ├── selection.py                     # pick_winner()
│   ├── confidence.py                    # filter_by_confidence()
│   ├── grid_runner.py                   # run_grid(), GridResult
│   └── report.py                        # render_grid_report()
│
└── CHUNKING_RESULTS.md                  # generated output

tests/benchmarks/chunking/               # NEW test tree
├── __init__.py
├── test_grid.py
├── test_buckets.py
├── test_synthetic.py
├── test_selection.py
├── test_confidence.py
├── test_grid_runner.py
└── test_report.py
```

---

## Task 0: Setup working branch

**Files:**
- Modify: working tree

Branching: the existing `benchmarks/` suite lives on branch `benchmark` (not merged to master). We branch from `benchmark` to inherit it, and add `benchmarks/chunking/` on top.

- [ ] **Step 1: Create and switch to a new branch from `benchmark`**

```bash
git fetch --all
git checkout benchmark
git pull --ff-only
git checkout -b feat/chunking-benchmark
```

Expected: branch `feat/chunking-benchmark` created from `benchmark`, `benchmarks/` directory is present.

- [ ] **Step 2: Verify existing benchmark still works**

```bash
uv sync
uv run python -c "from benchmarks.dataset import load_samples; from benchmarks.metrics import compute_detection_metrics; print('ok')"
```

Expected: prints `ok` with no traceback.

- [ ] **Step 3: Create the chunking subpackage skeleton**

```bash
mkdir -p benchmarks/chunking tests/benchmarks/chunking
touch benchmarks/chunking/__init__.py tests/benchmarks/chunking/__init__.py tests/benchmarks/__init__.py
```

- [ ] **Step 4: Commit skeleton**

```bash
git add benchmarks/chunking/__init__.py tests/benchmarks/
git commit -m "feat(bench): scaffold chunking subpackage"
```

---

## Task 1: `grid.py` — iterate grid configs

**Files:**
- Create: `benchmarks/chunking/grid.py`
- Test: `tests/benchmarks/chunking/test_grid.py`

- [ ] **Step 1: Write the failing tests**

Write `tests/benchmarks/chunking/test_grid.py`:

```python
from benchmarks.chunking.grid import (
    CHUNK_SIZES,
    GridConfig,
    OVERLAPS,
    THRESHOLDS,
    iterate_grid,
)


def test_grid_config_baseline_has_no_chunk_axes():
    c = GridConfig(chunk_size=None, overlap=None, threshold=0.5)
    assert c.is_baseline()


def test_grid_config_chunked_has_both_axes():
    c = GridConfig(chunk_size=256, overlap=32, threshold=0.5)
    assert not c.is_baseline()


def test_iterate_grid_excludes_invalid_overlap_pairs():
    configs = list(iterate_grid())
    for c in configs:
        if c.chunk_size is not None and c.overlap is not None:
            assert c.overlap < c.chunk_size


def test_iterate_grid_includes_baseline_per_threshold():
    configs = list(iterate_grid())
    baselines = [c for c in configs if c.is_baseline()]
    assert len(baselines) == len(THRESHOLDS)
    assert {c.threshold for c in baselines} == set(THRESHOLDS)


def test_iterate_grid_total_count():
    # 19 valid (chunk, overlap) pairs × 5 thresholds + 5 baseline thresholds = 100
    configs = list(iterate_grid())
    assert len(configs) == 100


def test_iterate_grid_is_deterministic():
    a = list(iterate_grid())
    b = list(iterate_grid())
    assert a == b


def test_iterate_grid_custom_axes():
    from benchmarks.chunking.grid import iterate_grid

    custom = list(
        iterate_grid(chunk_sizes=[128], overlaps=[0, 32], thresholds=[0.5])
    )
    # 2 valid (128,0), (128,32) + 1 baseline = 3
    assert len(custom) == 3


def test_grid_config_hashable():
    # Useful for dict keys during resume/checkpoint
    c1 = GridConfig(chunk_size=256, overlap=32, threshold=0.5)
    c2 = GridConfig(chunk_size=256, overlap=32, threshold=0.5)
    assert c1 == c2
    assert hash(c1) == hash(c2)
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest tests/benchmarks/chunking/test_grid.py -v`
Expected: collection/import error (module does not exist yet).

- [ ] **Step 3: Implement `grid.py`**

Write `benchmarks/chunking/grid.py`:

```python
"""Grid search space over (chunk_size, overlap, threshold)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass


CHUNK_SIZES: tuple[int, ...] = (128, 256, 384, 512, 768)
OVERLAPS: tuple[int, ...] = (0, 32, 64, 128)
THRESHOLDS: tuple[float, ...] = (0.3, 0.5, 0.7, 0.8, 0.9)


@dataclass(frozen=True)
class GridConfig:
    """One point in the grid search.

    ``chunk_size=None`` and ``overlap=None`` together denote the
    no-chunking baseline; in that case only ``threshold`` varies.
    """

    chunk_size: int | None
    overlap: int | None
    threshold: float

    def is_baseline(self) -> bool:
        return self.chunk_size is None and self.overlap is None


def iterate_grid(
    chunk_sizes: list[int] | tuple[int, ...] = CHUNK_SIZES,
    overlaps: list[int] | tuple[int, ...] = OVERLAPS,
    thresholds: list[float] | tuple[float, ...] = THRESHOLDS,
) -> Iterator[GridConfig]:
    """Yield every valid grid point.

    Invalid pairs where ``overlap >= chunk_size`` are skipped.
    Baseline (no chunking) is emitted once per threshold.
    """
    for cs in chunk_sizes:
        for ov in overlaps:
            if ov >= cs:
                continue
            for th in thresholds:
                yield GridConfig(chunk_size=cs, overlap=ov, threshold=th)

    for th in thresholds:
        yield GridConfig(chunk_size=None, overlap=None, threshold=th)
```

- [ ] **Step 4: Run tests, confirm all pass**

Run: `uv run pytest tests/benchmarks/chunking/test_grid.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add benchmarks/chunking/grid.py tests/benchmarks/chunking/test_grid.py
git commit -m "feat(bench): add grid config iteration for chunking benchmark"
```

---

## Task 2: `buckets.py` — length bucketing

**Files:**
- Create: `benchmarks/chunking/buckets.py`
- Test: `tests/benchmarks/chunking/test_buckets.py`

- [ ] **Step 1: Write failing tests**

Write `tests/benchmarks/chunking/test_buckets.py`:

```python
from benchmarks.chunking.buckets import BUCKET_ORDER, bucket_of


def test_bucket_short():
    assert bucket_of(0) == "<256"
    assert bucket_of(255) == "<256"


def test_bucket_medium():
    assert bucket_of(256) == "256-512"
    assert bucket_of(511) == "256-512"


def test_bucket_long():
    assert bucket_of(512) == "512-1024"
    assert bucket_of(1023) == "512-1024"


def test_bucket_very_long():
    assert bucket_of(1024) == ">1024"
    assert bucket_of(5000) == ">1024"


def test_bucket_order_is_short_to_long():
    assert BUCKET_ORDER == ("<256", "256-512", "512-1024", ">1024")


def test_all_buckets_covered():
    # Every bucket returned by bucket_of must appear in BUCKET_ORDER
    lengths = [0, 100, 255, 256, 500, 511, 512, 1000, 1023, 1024, 5000]
    for n in lengths:
        assert bucket_of(n) in BUCKET_ORDER
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest tests/benchmarks/chunking/test_buckets.py -v`
Expected: import error.

- [ ] **Step 3: Implement `buckets.py`**

Write `benchmarks/chunking/buckets.py`:

```python
"""Length bucketing for per-bucket metric aggregation."""

from __future__ import annotations


BUCKET_ORDER: tuple[str, ...] = ("<256", "256-512", "512-1024", ">1024")


def bucket_of(text_length: int) -> str:
    """Return the bucket label for a text of ``text_length`` characters."""
    if text_length < 256:
        return "<256"
    if text_length < 512:
        return "256-512"
    if text_length < 1024:
        return "512-1024"
    return ">1024"
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/benchmarks/chunking/test_buckets.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add benchmarks/chunking/buckets.py tests/benchmarks/chunking/test_buckets.py
git commit -m "feat(bench): add text-length bucketing"
```

---

## Task 3: `synthetic.py` — concatenate samples into long texts

**Files:**
- Create: `benchmarks/chunking/synthetic.py`
- Test: `tests/benchmarks/chunking/test_synthetic.py`

**Key invariant:** after concatenation, the `GoldAnnotation` offsets in the new `BenchmarkSample` must point at the exact same substring in the concatenated `source_text`.

- [ ] **Step 1: Write failing tests**

Write `tests/benchmarks/chunking/test_synthetic.py`:

```python
from benchmarks.chunking.synthetic import SEPARATOR, concat_samples
from benchmarks.dataset import BenchmarkSample, GoldAnnotation


def _sample(text: str, anns: list[tuple[str, int, int, str]]) -> BenchmarkSample:
    return BenchmarkSample(
        source_text=text,
        target_text=text,
        annotations=tuple(
            GoldAnnotation(text=t, raw_label=lbl, start=s, end=e)
            for (t, s, e, lbl) in anns
        ),
        language="English",
    )


def test_concat_preserves_annotation_text():
    s1 = _sample("Hello Alice.", [("Alice", 6, 11, "GIVENNAME")])
    s2 = _sample("Bob lives in Paris.", [("Paris", 13, 18, "CITY")])

    merged = concat_samples([s1, s2])

    for ann in merged.annotations:
        assert merged.source_text[ann.start : ann.end] == ann.text


def test_concat_shifts_second_sample_offsets():
    s1 = _sample("Hello Alice.", [("Alice", 6, 11, "GIVENNAME")])
    s2 = _sample("Bob lives in Paris.", [("Paris", 13, 18, "CITY")])

    merged = concat_samples([s1, s2])

    expected_offset = len(s1.source_text) + len(SEPARATOR)
    paris = [a for a in merged.annotations if a.text == "Paris"][0]
    assert paris.start == 13 + expected_offset


def test_concat_text_joins_with_separator():
    s1 = _sample("A.", [])
    s2 = _sample("B.", [])
    merged = concat_samples([s1, s2])
    assert merged.source_text == f"A.{SEPARATOR}B."


def test_concat_preserves_language():
    s = _sample("x", [])
    merged = concat_samples([s, s, s])
    assert merged.language == "English"


def test_concat_empty_list_raises():
    import pytest

    with pytest.raises(ValueError):
        concat_samples([])


def test_concat_single_sample_returns_copy_with_same_offsets():
    s1 = _sample("Hello Alice.", [("Alice", 6, 11, "GIVENNAME")])
    merged = concat_samples([s1])
    assert merged.source_text == s1.source_text
    assert merged.annotations == s1.annotations
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest tests/benchmarks/chunking/test_synthetic.py -v`
Expected: import error.

- [ ] **Step 3: Implement `synthetic.py`**

Write `benchmarks/chunking/synthetic.py`:

```python
"""Synthesize long texts by concatenating benchmark samples."""

from __future__ import annotations

from benchmarks.dataset import BenchmarkSample, GoldAnnotation


SEPARATOR: str = "\n\n---\n\n"


def concat_samples(samples: list[BenchmarkSample]) -> BenchmarkSample:
    """Concatenate ``samples`` into a single long ``BenchmarkSample``.

    Source texts are joined with ``SEPARATOR`` and every annotation offset
    is shifted to its new position in the concatenated text. The language
    of the resulting sample is that of the first input sample.

    Args:
        samples: Non-empty list of samples to concatenate.

    Raises:
        ValueError: If ``samples`` is empty.
    """
    if not samples:
        raise ValueError("concat_samples requires at least one sample")

    parts: list[str] = []
    shifted: list[GoldAnnotation] = []
    offset = 0

    for i, s in enumerate(samples):
        if i > 0:
            parts.append(SEPARATOR)
            offset += len(SEPARATOR)

        parts.append(s.source_text)
        for ann in s.annotations:
            shifted.append(
                GoldAnnotation(
                    text=ann.text,
                    raw_label=ann.raw_label,
                    start=ann.start + offset,
                    end=ann.end + offset,
                )
            )
        offset += len(s.source_text)

    merged_text = "".join(parts)

    return BenchmarkSample(
        source_text=merged_text,
        target_text=merged_text,
        annotations=tuple(shifted),
        language=samples[0].language,
    )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/benchmarks/chunking/test_synthetic.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add benchmarks/chunking/synthetic.py tests/benchmarks/chunking/test_synthetic.py
git commit -m "feat(bench): add synthetic long-text generator"
```

---

## Task 4: `confidence.py` — post-hoc threshold filtering

**Files:**
- Create: `benchmarks/chunking/confidence.py`
- Test: `tests/benchmarks/chunking/test_confidence.py`

- [ ] **Step 1: Write failing tests**

Write `tests/benchmarks/chunking/test_confidence.py`:

```python
from benchmarks.chunking.confidence import filter_by_confidence
from piighost.models import Detection, Span


def _det(text: str, start: int, end: int, conf: float) -> Detection:
    return Detection(
        text=text,
        label="PERSON",
        position=Span(start_pos=start, end_pos=end),
        confidence=conf,
    )


def test_filter_keeps_equal_or_above():
    detections = [_det("a", 0, 1, 0.5), _det("b", 1, 2, 0.8)]
    result = filter_by_confidence(detections, threshold=0.5)
    assert len(result) == 2


def test_filter_drops_below():
    detections = [_det("a", 0, 1, 0.3), _det("b", 1, 2, 0.8)]
    result = filter_by_confidence(detections, threshold=0.5)
    assert len(result) == 1
    assert result[0].text == "b"


def test_filter_threshold_zero_keeps_all():
    detections = [_det("a", 0, 1, 0.0), _det("b", 1, 2, 0.1)]
    result = filter_by_confidence(detections, threshold=0.0)
    assert len(result) == 2


def test_filter_preserves_input_unchanged():
    detections = [_det("a", 0, 1, 0.3)]
    _ = filter_by_confidence(detections, threshold=0.5)
    assert len(detections) == 1  # original list untouched


def test_filter_preserves_order():
    detections = [
        _det("a", 0, 1, 0.9),
        _det("b", 1, 2, 0.6),
        _det("c", 2, 3, 0.95),
    ]
    result = filter_by_confidence(detections, threshold=0.5)
    assert [d.text for d in result] == ["a", "b", "c"]
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest tests/benchmarks/chunking/test_confidence.py -v`
Expected: import error.

- [ ] **Step 3: Implement `confidence.py`**

Write `benchmarks/chunking/confidence.py`:

```python
"""Post-hoc confidence filtering used to collapse the threshold axis."""

from __future__ import annotations

from piighost.models import Detection


def filter_by_confidence(
    detections: list[Detection],
    threshold: float,
) -> list[Detection]:
    """Return detections whose confidence is at least ``threshold``.

    The input list is not modified; a new list is returned preserving
    input order. Used by the grid runner to avoid re-running detection
    for each threshold value.
    """
    return [d for d in detections if d.confidence >= threshold]
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/benchmarks/chunking/test_confidence.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add benchmarks/chunking/confidence.py tests/benchmarks/chunking/test_confidence.py
git commit -m "feat(bench): add post-hoc confidence filter"
```

---

## Task 5: `selection.py` — pick grid winner

**Files:**
- Create: `benchmarks/chunking/selection.py`
- Test: `tests/benchmarks/chunking/test_selection.py`

**Rule:** winner = config with maximum **recall** under the constraint **precision ≥ `min_precision`** (default 0.80). Tie-break on F1, then lowest `chunk_size` (smaller chunks are faster), then highest `threshold` (more conservative).

- [ ] **Step 1: Write failing tests**

Write `tests/benchmarks/chunking/test_selection.py`:

```python
import pytest

from benchmarks.chunking.grid import GridConfig
from benchmarks.chunking.selection import (
    ScoredConfig,
    pick_winner,
)


def _scored(cs, ov, th, precision, recall, f1) -> ScoredConfig:
    return ScoredConfig(
        config=GridConfig(chunk_size=cs, overlap=ov, threshold=th),
        precision=precision,
        recall=recall,
        f1=f1,
    )


def test_pick_winner_prefers_highest_recall_above_precision_floor():
    candidates = [
        _scored(256, 32, 0.5, precision=0.9, recall=0.70, f1=0.79),
        _scored(384, 64, 0.7, precision=0.85, recall=0.85, f1=0.85),
        _scored(512, 128, 0.8, precision=0.95, recall=0.60, f1=0.73),
    ]
    winner = pick_winner(candidates, min_precision=0.80)
    assert winner.config.chunk_size == 384
    assert winner.config.threshold == 0.7


def test_pick_winner_excludes_candidates_below_precision_floor():
    candidates = [
        _scored(256, 32, 0.3, precision=0.70, recall=0.99, f1=0.82),
        _scored(256, 32, 0.5, precision=0.85, recall=0.75, f1=0.80),
    ]
    winner = pick_winner(candidates, min_precision=0.80)
    assert winner.config.threshold == 0.5


def test_pick_winner_tie_break_on_f1():
    candidates = [
        _scored(256, 32, 0.5, precision=0.90, recall=0.80, f1=0.85),
        _scored(384, 64, 0.5, precision=0.90, recall=0.80, f1=0.84),
    ]
    winner = pick_winner(candidates, min_precision=0.80)
    assert winner.f1 == 0.85


def test_pick_winner_tie_break_on_chunk_size_when_equal_f1():
    candidates = [
        _scored(384, 64, 0.5, precision=0.90, recall=0.80, f1=0.85),
        _scored(256, 32, 0.5, precision=0.90, recall=0.80, f1=0.85),
    ]
    winner = pick_winner(candidates, min_precision=0.80)
    assert winner.config.chunk_size == 256


def test_pick_winner_raises_when_no_candidate_meets_floor():
    candidates = [
        _scored(256, 32, 0.3, precision=0.60, recall=0.99, f1=0.74),
    ]
    with pytest.raises(ValueError, match="precision"):
        pick_winner(candidates, min_precision=0.80)


def test_pick_winner_accepts_baseline_config():
    candidates = [
        _scored(None, None, 0.5, precision=0.90, recall=0.80, f1=0.85),
    ]
    winner = pick_winner(candidates, min_precision=0.80)
    assert winner.config.is_baseline()
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest tests/benchmarks/chunking/test_selection.py -v`
Expected: import error.

- [ ] **Step 3: Implement `selection.py`**

Write `benchmarks/chunking/selection.py`:

```python
"""Pick the grid winner under a precision floor."""

from __future__ import annotations

from dataclasses import dataclass

from benchmarks.chunking.grid import GridConfig


@dataclass(frozen=True)
class ScoredConfig:
    """A grid config paired with its aggregate metrics."""

    config: GridConfig
    precision: float
    recall: float
    f1: float


def pick_winner(
    candidates: list[ScoredConfig],
    min_precision: float = 0.80,
) -> ScoredConfig:
    """Return the candidate maximizing recall under the precision floor.

    Tie-break order: highest F1, then lowest ``chunk_size`` (baseline treated
    as infinite so chunked configs beat it at equal score), then highest
    ``threshold``.

    Raises:
        ValueError: If no candidate meets ``min_precision``.
    """
    eligible = [c for c in candidates if c.precision >= min_precision]

    if not eligible:
        raise ValueError(
            f"No candidate meets precision floor {min_precision}. "
            f"Max precision observed: {max((c.precision for c in candidates), default=0):.3f}"
        )

    def _sort_key(c: ScoredConfig) -> tuple[float, float, int, float]:
        chunk = c.config.chunk_size if c.config.chunk_size is not None else 10**9
        return (-c.recall, -c.f1, chunk, -c.config.threshold)

    return sorted(eligible, key=_sort_key)[0]
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/benchmarks/chunking/test_selection.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add benchmarks/chunking/selection.py tests/benchmarks/chunking/test_selection.py
git commit -m "feat(bench): add grid winner selection under precision floor"
```

---

## Task 6: `grid_runner.py` — run the grid, reuse detections

**Files:**
- Create: `benchmarks/chunking/grid_runner.py`
- Test: `tests/benchmarks/chunking/test_grid_runner.py`

**Design contract:**

- Input: a factory `make_detector(threshold: float) -> AnyDetector` (callers pass a closure that loads the model once and returns a fresh detector for the given threshold), a list of `BenchmarkSample`s, a `LabelMapping`, and optional custom grid axes.
- For each distinct `(chunk_size, overlap)` in the grid (including baseline `(None, None)`):
  - Build the detector at `threshold=0.0` (via factory), optionally wrap with `ChunkedDetector`.
  - Call `.detect()` on every sample; store per-sample raw detections.
- For each `threshold` in the grid:
  - Filter each sample's detections by confidence.
  - Compute aggregate and per-bucket metrics using existing `compute_detection_metrics`.
  - Emit a `GridResult`.

`per_bucket_metrics` groups samples by `bucket_of(len(sample.source_text))` and computes metrics per bucket.

- [ ] **Step 1: Write failing tests**

Write `tests/benchmarks/chunking/test_grid_runner.py`:

```python
import pytest

from benchmarks.chunking.grid import GridConfig
from benchmarks.chunking.grid_runner import GridResult, run_grid
from benchmarks.dataset import BenchmarkSample, GoldAnnotation
from benchmarks.metrics import MatchMode
from piighost.detector.base import AnyDetector
from piighost.models import Detection, Span


class FakeThresholdDetector:
    """Detector that emits fixed detections; threshold is ignored (kept at 0)."""

    def __init__(self, detections_per_text: dict[str, list[Detection]]) -> None:
        self._map = detections_per_text

    async def detect(self, text: str) -> list[Detection]:
        return list(self._map.get(text, []))


def _sample(text: str, anns: list[tuple[str, int, int, str]]) -> BenchmarkSample:
    return BenchmarkSample(
        source_text=text,
        target_text=text,
        annotations=tuple(
            GoldAnnotation(text=t, raw_label=lbl, start=s, end=e)
            for (t, s, e, lbl) in anns
        ),
        language="English",
    )


def _det(label: str, text: str, start: int, end: int, conf: float) -> Detection:
    return Detection(
        text=text,
        label=label,
        position=Span(start_pos=start, end_pos=end),
        confidence=conf,
    )


@pytest.mark.asyncio
async def test_run_grid_yields_one_result_per_config():
    detector = FakeThresholdDetector({"Hello Alice": [_det("PERSON", "Alice", 6, 11, 0.9)]})
    samples = [_sample("Hello Alice", [("Alice", 6, 11, "GIVENNAME")])]

    def factory(threshold: float) -> AnyDetector:  # noqa: ARG001
        return detector

    label_map = {"GIVENNAME": "PERSON"}
    results = await run_grid(
        factory=factory,
        samples=samples,
        label_map=label_map,
        match_mode=MatchMode.PARTIAL,
        chunk_sizes=[256],
        overlaps=[0],
        thresholds=[0.5, 0.95],
    )

    # 1 (chunk, overlap) + 1 baseline = 2 chunk-level groups, × 2 thresholds = 4 results
    assert len(results) == 4
    assert all(isinstance(r, GridResult) for r in results)


@pytest.mark.asyncio
async def test_run_grid_collapses_threshold_via_posthoc_filter():
    # Detection confidence is 0.6. At threshold 0.5 -> TP. At 0.8 -> FN.
    detector = FakeThresholdDetector({"t": [_det("PERSON", "Alice", 0, 5, 0.6)]})
    samples = [_sample("t", [("Alice", 0, 5, "GIVENNAME")])]  # text "t" for simplicity

    def factory(threshold: float) -> AnyDetector:  # noqa: ARG001
        return detector

    label_map = {"GIVENNAME": "PERSON"}
    results = await run_grid(
        factory=factory,
        samples=samples,
        label_map=label_map,
        match_mode=MatchMode.PARTIAL,
        chunk_sizes=[256],
        overlaps=[0],
        thresholds=[0.5, 0.8],
    )

    by_threshold = {r.config.threshold: r for r in results if not r.config.is_baseline()}
    assert by_threshold[0.5].metrics.true_positives == 1
    assert by_threshold[0.8].metrics.true_positives == 0
    assert by_threshold[0.8].metrics.false_negatives == 1


@pytest.mark.asyncio
async def test_run_grid_populates_per_bucket_metrics():
    short_text = "a" * 100
    long_text = "a" * 600
    detector = FakeThresholdDetector({short_text: [], long_text: []})
    samples = [_sample(short_text, []), _sample(long_text, [])]

    def factory(threshold: float) -> AnyDetector:  # noqa: ARG001
        return detector

    results = await run_grid(
        factory=factory,
        samples=samples,
        label_map={},
        match_mode=MatchMode.PARTIAL,
        chunk_sizes=[256],
        overlaps=[0],
        thresholds=[0.5],
    )

    for r in results:
        assert "<256" in r.per_bucket_metrics
        assert "512-1024" in r.per_bucket_metrics


@pytest.mark.asyncio
async def test_run_grid_baseline_does_not_wrap_chunked():
    # Use a sentinel text longer than chunk_size to confirm baseline
    # does not split it. A FakeThresholdDetector returns the same detections
    # regardless, so we assert the grid emits a baseline result.
    detector = FakeThresholdDetector({})
    samples = [_sample("x" * 1000, [])]

    def factory(threshold: float) -> AnyDetector:  # noqa: ARG001
        return detector

    results = await run_grid(
        factory=factory,
        samples=samples,
        label_map={},
        match_mode=MatchMode.PARTIAL,
        chunk_sizes=[256],
        overlaps=[0],
        thresholds=[0.5],
    )

    baselines = [r for r in results if r.config.is_baseline()]
    assert len(baselines) == 1
```

Add `pytest-asyncio` marker config if not present. Check existing `pyproject.toml` under `[tool.pytest.ini_options]`; if `asyncio_mode = "auto"` is set, the `@pytest.mark.asyncio` decorators above are redundant but harmless.

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest tests/benchmarks/chunking/test_grid_runner.py -v`
Expected: import error.

- [ ] **Step 3: Implement `grid_runner.py`**

Write `benchmarks/chunking/grid_runner.py`:

```python
"""Run a grid search, reusing raw detections across thresholds."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from benchmarks.chunking.buckets import BUCKET_ORDER, bucket_of
from benchmarks.chunking.confidence import filter_by_confidence
from benchmarks.chunking.grid import (
    CHUNK_SIZES,
    OVERLAPS,
    THRESHOLDS,
    GridConfig,
    iterate_grid,
)
from benchmarks.dataset import BenchmarkSample
from benchmarks.label_map import LabelMapping
from benchmarks.metrics import MatchMode, MetricsResult, compute_detection_metrics
from piighost.detector.base import AnyDetector
from piighost.detector.chunked import ChunkedDetector
from piighost.models import Detection


@dataclass(frozen=True)
class GridResult:
    """Metrics for one grid configuration."""

    config: GridConfig
    metrics: MetricsResult
    per_bucket_metrics: dict[str, MetricsResult]
    num_samples: int
    elapsed_seconds: float


DetectorFactory = Callable[[float], AnyDetector]


async def run_grid(
    factory: DetectorFactory,
    samples: list[BenchmarkSample],
    label_map: LabelMapping,
    match_mode: MatchMode = MatchMode.PARTIAL,
    chunk_sizes: list[int] | None = None,
    overlaps: list[int] | None = None,
    thresholds: list[float] | None = None,
) -> list[GridResult]:
    """Run the grid search and return one ``GridResult`` per config.

    The ``factory`` callable is used to build detectors at
    ``threshold=0.0`` so that detections can be filtered post-hoc
    for every requested threshold without re-running detection.

    Args:
        factory: Creates a detector at the given confidence threshold.
        samples: Evaluation samples (already loaded).
        label_map: Gold-to-model label mapping.
        match_mode: Metric matching mode (typically ``PARTIAL``).
        chunk_sizes: Override of the default ``chunk_size`` axis.
        overlaps: Override of the default ``overlap`` axis.
        thresholds: Override of the default ``threshold`` axis.

    Returns:
        One ``GridResult`` per valid configuration.
    """
    configs = list(
        iterate_grid(
            chunk_sizes=chunk_sizes if chunk_sizes is not None else CHUNK_SIZES,
            overlaps=overlaps if overlaps is not None else OVERLAPS,
            thresholds=thresholds if thresholds is not None else THRESHOLDS,
        )
    )

    results: list[GridResult] = []

    # Map (chunk_size, overlap) -> list of per-sample detections at threshold=0
    chunk_groups: dict[tuple[int | None, int | None], list[list[Detection]]] = {}

    for c in configs:
        key = (c.chunk_size, c.overlap)
        if key in chunk_groups:
            continue

        base_detector = factory(0.0)
        if c.chunk_size is not None and c.overlap is not None:
            runtime_detector: AnyDetector = ChunkedDetector(
                detector=base_detector,
                chunk_size=c.chunk_size,
                overlap=c.overlap,
            )
        else:
            runtime_detector = base_detector

        per_sample: list[list[Detection]] = []
        for s in samples:
            per_sample.append(await runtime_detector.detect(s.source_text))
        chunk_groups[key] = per_sample

    # Compute metrics for each config
    for c in configs:
        t0 = time.perf_counter()
        raw = chunk_groups[(c.chunk_size, c.overlap)]
        filtered: list[list[Detection]] = [
            filter_by_confidence(dets, c.threshold) for dets in raw
        ]

        flat_golds = [g for s in samples for g in s.annotations]
        flat_preds = [p for ps in filtered for p in ps]
        agg = compute_detection_metrics(
            list(flat_golds), flat_preds, label_map, match_mode
        )

        per_bucket: dict[str, MetricsResult] = {}
        for bucket in BUCKET_ORDER:
            bucket_samples = [
                (s, f)
                for s, f in zip(samples, filtered, strict=True)
                if bucket_of(len(s.source_text)) == bucket
            ]
            if not bucket_samples:
                continue
            b_golds = [g for s, _ in bucket_samples for g in s.annotations]
            b_preds = [p for _, f in bucket_samples for p in f]
            per_bucket[bucket] = compute_detection_metrics(
                list(b_golds), b_preds, label_map, match_mode
            )

        results.append(
            GridResult(
                config=c,
                metrics=agg,
                per_bucket_metrics=per_bucket,
                num_samples=len(samples),
                elapsed_seconds=time.perf_counter() - t0,
            )
        )

    return results
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/benchmarks/chunking/test_grid_runner.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add benchmarks/chunking/grid_runner.py tests/benchmarks/chunking/test_grid_runner.py
git commit -m "feat(bench): add grid runner with post-hoc threshold reuse"
```

---

## Task 7: `report.py` — markdown rendering

**Files:**
- Create: `benchmarks/chunking/report.py`
- Test: `tests/benchmarks/chunking/test_report.py`

- [ ] **Step 1: Write failing tests**

Write `tests/benchmarks/chunking/test_report.py`:

```python
from benchmarks.chunking.grid import GridConfig
from benchmarks.chunking.grid_runner import GridResult
from benchmarks.chunking.report import render_grid_report
from benchmarks.chunking.selection import ScoredConfig
from benchmarks.metrics import MetricsResult


def _metrics(p: float, r: float, f1: float) -> MetricsResult:
    return MetricsResult(
        precision=p,
        recall=r,
        f1=f1,
        true_positives=10,
        false_positives=2,
        false_negatives=3,
        total_gold=13,
        total_predicted=12,
    )


def _result(cs, ov, th, p=0.9, r=0.8, f=0.85) -> GridResult:
    return GridResult(
        config=GridConfig(chunk_size=cs, overlap=ov, threshold=th),
        metrics=_metrics(p, r, f),
        per_bucket_metrics={"<256": _metrics(p, r, f)},
        num_samples=10,
        elapsed_seconds=1.0,
    )


def test_render_grid_report_contains_sections():
    results = {
        ("gliner2", "en"): [
            _result(256, 32, 0.5),
            _result(None, None, 0.5, p=0.85, r=0.75, f=0.80),
        ],
    }
    winners = {
        ("gliner2", "en"): ScoredConfig(
            config=GridConfig(chunk_size=256, overlap=32, threshold=0.5),
            precision=0.9, recall=0.8, f1=0.85,
        ),
    }
    md = render_grid_report(results, winners)

    assert "# Chunked Detector Benchmark Results" in md
    assert "gliner2" in md
    assert "en" in md
    assert "Winner" in md
    assert "256" in md  # chunk_size printed


def test_render_grid_report_per_bucket_table():
    results = {
        ("gliner2", "en"): [_result(256, 32, 0.5)],
    }
    winners = {
        ("gliner2", "en"): ScoredConfig(
            config=GridConfig(chunk_size=256, overlap=32, threshold=0.5),
            precision=0.9, recall=0.8, f1=0.85,
        ),
    }
    md = render_grid_report(results, winners)
    assert "<256" in md  # bucket label appears
```

- [ ] **Step 2: Run and verify failure**

Run: `uv run pytest tests/benchmarks/chunking/test_report.py -v`
Expected: import error.

- [ ] **Step 3: Implement `report.py`**

Write `benchmarks/chunking/report.py`:

```python
"""Render grid-search results to markdown."""

from __future__ import annotations

from benchmarks.chunking.buckets import BUCKET_ORDER
from benchmarks.chunking.grid_runner import GridResult
from benchmarks.chunking.selection import ScoredConfig


Key = tuple[str, str]  # (detector_name, language)


def _fmt_config(cs: int | None, ov: int | None, th: float) -> str:
    if cs is None:
        return f"baseline @ {th}"
    return f"cs={cs}, ov={ov}, th={th}"


def _fmt_metrics_row(precision: float, recall: float, f1: float) -> str:
    return f"{precision:.3f} | {recall:.3f} | {f1:.3f}"


def render_grid_report(
    results: dict[Key, list[GridResult]],
    winners: dict[Key, ScoredConfig],
) -> str:
    """Render the full results report as a markdown string."""
    lines: list[str] = []
    lines.append("# Chunked Detector Benchmark Results\n")

    for (detector, language), winner in sorted(winners.items()):
        lines.append(f"## {detector} / {language}\n")
        lines.append(f"**Winner:** {_fmt_config(winner.config.chunk_size, winner.config.overlap, winner.config.threshold)}\n")
        lines.append(
            f"Aggregate P/R/F1: {winner.precision:.3f} / {winner.recall:.3f} / {winner.f1:.3f}\n"
        )

        key_results = results[(detector, language)]
        winner_result = next(
            r for r in key_results if r.config == winner.config
        )

        lines.append("\n### Per-bucket metrics (winner)\n")
        lines.append("| Bucket | Precision | Recall | F1 |")
        lines.append("|---|---|---|---|")
        for bucket in BUCKET_ORDER:
            if bucket in winner_result.per_bucket_metrics:
                m = winner_result.per_bucket_metrics[bucket]
                lines.append(f"| {bucket} | {_fmt_metrics_row(m.precision, m.recall, m.f1)} |")
        lines.append("")

        lines.append("### Top 5 configs (by recall, precision >= 0.80)\n")
        eligible = [r for r in key_results if r.metrics.precision >= 0.80]
        eligible.sort(key=lambda r: (-r.metrics.recall, -r.metrics.f1))
        lines.append("| Config | Precision | Recall | F1 |")
        lines.append("|---|---|---|---|")
        for r in eligible[:5]:
            cfg = _fmt_config(r.config.chunk_size, r.config.overlap, r.config.threshold)
            lines.append(
                f"| {cfg} | {_fmt_metrics_row(r.metrics.precision, r.metrics.recall, r.metrics.f1)} |"
            )
        lines.append("")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/benchmarks/chunking/test_report.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add benchmarks/chunking/report.py tests/benchmarks/chunking/test_report.py
git commit -m "feat(bench): add markdown report rendering"
```

---

## Task 8: CLI `python -m benchmarks.chunking`

**Files:**
- Create: `benchmarks/chunking/__main__.py`

Two subcommands:

- `eval` — single config sanity run for debugging
- `grid` — full grid search, all detectors and languages

- [ ] **Step 1: Implement CLI**

Write `benchmarks/chunking/__main__.py`:

```python
"""CLI for chunking benchmark.

Usage:
    python -m benchmarks.chunking grid --output CHUNKING_RESULTS.md
    python -m benchmarks.chunking grid --detectors gliner2 --languages en --phase1-limit 20
    python -m benchmarks.chunking eval --detector gliner2 \
        --chunk-size 384 --overlap 64 --threshold 0.7 --language en --limit 200
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from benchmarks.chunking.grid_runner import GridResult, run_grid
from benchmarks.chunking.report import render_grid_report
from benchmarks.chunking.selection import ScoredConfig, pick_winner
from benchmarks.dataset import load_samples
from benchmarks.label_map import GLINER2_MAP, TRANSFORMERS_MAP, LabelMapping
from benchmarks.metrics import MatchMode
from piighost.detector.base import AnyDetector


_LABEL_MAPS: dict[str, LabelMapping] = {
    "gliner2": GLINER2_MAP,
    "transformers": TRANSFORMERS_MAP,
}

_DEFAULT_LABELS: dict[str, list[str]] = {
    "gliner2": ["PERSON", "LOCATION", "ORGANIZATION", "DATE", "EMAIL", "PHONE"],
    "transformers": ["PER", "LOC", "ORG"],
}

_TRANSFORMERS_MULTILINGUAL_MODEL = "Davlan/xlm-roberta-base-ner-hrl"
_GLINER2_DEFAULT_MODEL = "fastino/gliner2-multi-v1"


def _make_gliner2_factory(model_name: str, labels: list[str]):
    from gliner2 import GLiNER2
    from piighost.detector.gliner2 import Gliner2Detector

    sys.stderr.write(f"Loading GLiNER2: {model_name}\n")
    model = GLiNER2.from_pretrained(model_name)

    def factory(threshold: float) -> AnyDetector:
        return Gliner2Detector(model=model, labels=labels, threshold=threshold)

    return factory


def _make_transformers_factory(model_name: str, labels: list[str]):
    from transformers import pipeline
    from piighost.detector.transformers import TransformersDetector

    sys.stderr.write(f"Loading Transformers: {model_name}\n")
    ner = pipeline("ner", model=model_name, aggregation_strategy="simple")

    # TransformersDetector has no threshold knob; post-hoc filter handles it
    def factory(_threshold: float) -> AnyDetector:
        return TransformersDetector(pipeline=ner, labels=labels)

    return factory


def _factory_for(detector: str):
    if detector == "gliner2":
        return _make_gliner2_factory(_GLINER2_DEFAULT_MODEL, _DEFAULT_LABELS["gliner2"])
    if detector == "transformers":
        return _make_transformers_factory(
            _TRANSFORMERS_MULTILINGUAL_MODEL, _DEFAULT_LABELS["transformers"]
        )
    raise ValueError(f"Unknown detector: {detector}")


async def _run_grid(args: argparse.Namespace) -> None:
    detectors = args.detectors or ["gliner2", "transformers"]
    languages = args.languages or ["en", "fr", "de", "it", "es", "nl"]

    all_results: dict[tuple[str, str], list[GridResult]] = {}
    winners: dict[tuple[str, str], ScoredConfig] = {}

    for detector in detectors:
        factory = _factory_for(detector)
        label_map = _LABEL_MAPS[detector]

        for lang in languages:
            sys.stderr.write(f"\n=== {detector} / {lang} ===\n")
            samples = load_samples(
                split=args.split,
                language=lang,
                limit=args.phase1_limit,
                seed=args.seed,
            )
            sys.stderr.write(f"Loaded {len(samples)} samples\n")

            results = await run_grid(
                factory=factory,
                samples=samples,
                label_map=label_map,
                match_mode=MatchMode.PARTIAL,
            )
            all_results[(detector, lang)] = results

            scored = [
                ScoredConfig(
                    config=r.config,
                    precision=r.metrics.precision,
                    recall=r.metrics.recall,
                    f1=r.metrics.f1,
                )
                for r in results
            ]
            try:
                winners[(detector, lang)] = pick_winner(scored, min_precision=args.min_precision)
            except ValueError as exc:
                sys.stderr.write(f"No winner for {detector}/{lang}: {exc}\n")

    md = render_grid_report(all_results, winners)
    Path(args.output).write_text(md)
    sys.stderr.write(f"\nReport written to {args.output}\n")

    if args.json:
        payload = {
            f"{d}|{l}": [
                {
                    "config": {
                        "chunk_size": r.config.chunk_size,
                        "overlap": r.config.overlap,
                        "threshold": r.config.threshold,
                    },
                    "precision": r.metrics.precision,
                    "recall": r.metrics.recall,
                    "f1": r.metrics.f1,
                    "elapsed": r.elapsed_seconds,
                }
                for r in rs
            ]
            for (d, l), rs in all_results.items()
        }
        Path(args.json).write_text(json.dumps(payload, indent=2))
        sys.stderr.write(f"JSON raw results written to {args.json}\n")


async def _run_eval(args: argparse.Namespace) -> None:
    factory = _factory_for(args.detector)
    label_map = _LABEL_MAPS[args.detector]

    samples = load_samples(
        split=args.split, language=args.language, limit=args.limit, seed=args.seed
    )

    results = await run_grid(
        factory=factory,
        samples=samples,
        label_map=label_map,
        match_mode=MatchMode.PARTIAL,
        chunk_sizes=[args.chunk_size],
        overlaps=[args.overlap],
        thresholds=[args.threshold],
    )

    for r in results:
        print(
            f"{r.config}: P={r.metrics.precision:.3f} R={r.metrics.recall:.3f} F1={r.metrics.f1:.3f} "
            f"({r.num_samples} samples, {r.elapsed_seconds:.1f}s)"
        )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Chunking benchmark")
    sp = p.add_subparsers(dest="cmd", required=True)

    g = sp.add_parser("grid", help="Run full grid search")
    g.add_argument("--detectors", nargs="+", choices=["gliner2", "transformers"])
    g.add_argument("--languages", nargs="+", choices=["en", "fr", "de", "it", "es", "nl"])
    g.add_argument("--phase1-limit", type=int, default=200)
    g.add_argument("--split", default="validation")
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--min-precision", type=float, default=0.80)
    g.add_argument("--output", default="benchmarks/CHUNKING_RESULTS.md")
    g.add_argument("--json", default=None, help="Optional JSON dump of raw results")

    e = sp.add_parser("eval", help="Single config sanity run")
    e.add_argument("--detector", required=True, choices=["gliner2", "transformers"])
    e.add_argument("--chunk-size", type=int, required=True)
    e.add_argument("--overlap", type=int, required=True)
    e.add_argument("--threshold", type=float, required=True)
    e.add_argument("--language", default="en")
    e.add_argument("--limit", type=int, default=200)
    e.add_argument("--split", default="validation")
    e.add_argument("--seed", type=int, default=42)

    return p


def main() -> None:
    args = _build_parser().parse_args()
    if args.cmd == "grid":
        asyncio.run(_run_grid(args))
    elif args.cmd == "eval":
        asyncio.run(_run_eval(args))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke test the CLI (no real model)**

Run: `uv run python -m benchmarks.chunking --help`
Expected: usage string printed.

Run: `uv run python -m benchmarks.chunking grid --help`
Expected: subcommand help printed.

- [ ] **Step 3: Commit**

```bash
git add benchmarks/chunking/__main__.py
git commit -m "feat(bench): add chunking CLI with grid and eval subcommands"
```

---

## Task 9: Post-hoc threshold smoke test (real detector)

**Files:**
- Create: `tests/benchmarks/chunking/test_posthoc_assumption.py`

**Purpose:** Validate the core optimization assumption: detections at `threshold=0.5` from `Gliner2Detector` equal (or are a subset of) detections at `threshold=0.0` filtered client-side to `confidence >= 0.5`. If this holds, we save 5× compute.

**Marked as `@pytest.mark.slow` so it runs on demand, not in CI by default.**

- [ ] **Step 1: Write the smoke test**

Write `tests/benchmarks/chunking/test_posthoc_assumption.py`:

```python
"""Verify threshold filtering can be moved post-hoc.

Marked slow because it loads a real GLiNER2 model; run with:
    uv run pytest tests/benchmarks/chunking/test_posthoc_assumption.py -m slow -v
"""

import pytest

from benchmarks.chunking.confidence import filter_by_confidence


pytestmark = pytest.mark.slow


@pytest.mark.asyncio
async def test_gliner2_threshold_is_posthoc_equivalent():
    try:
        from gliner2 import GLiNER2
        from piighost.detector.gliner2 import Gliner2Detector
    except ImportError:
        pytest.skip("gliner2 not installed")

    model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")
    labels = ["PERSON", "LOCATION"]
    text = (
        "Patrick lives in Paris. Alice visited Lyon. "
        "Bob works at the embassy in Madrid."
    )

    server_thr = 0.5
    server = Gliner2Detector(model=model, labels=labels, threshold=server_thr)
    server_dets = await server.detect(text)

    client = Gliner2Detector(model=model, labels=labels, threshold=0.0)
    client_raw = await client.detect(text)
    client_filtered = filter_by_confidence(client_raw, server_thr)

    def _key(d):
        return (d.position.start_pos, d.position.end_pos, d.label, round(d.confidence, 4))

    assert sorted(_key(d) for d in server_dets) == sorted(
        _key(d) for d in client_filtered
    ), "threshold=0 + post-hoc filter must match server-side threshold"
```

Update `pyproject.toml` to register the `slow` marker if not present. Check for an existing `[tool.pytest.ini_options]` section and add:

```toml
markers = [
    "slow: tests that require real model weights",
]
```

- [ ] **Step 2: Run the smoke test manually (not in CI)**

Run: `uv run pytest tests/benchmarks/chunking/test_posthoc_assumption.py -m slow -v`
Expected: passes. If it fails, file an issue referencing this plan and proceed to Task 10 with a **fallback**: in `grid_runner.run_grid`, move the threshold axis outside the chunk-group loop (re-run inference per threshold). Update the plan and mark this optimization as "rejected".

- [ ] **Step 3: Commit**

```bash
git add tests/benchmarks/chunking/test_posthoc_assumption.py pyproject.toml
git commit -m "test(bench): validate post-hoc threshold filter vs server-side"
```

---

## Task 10: Mini end-to-end grid run

**Files:**
- No new files; execute the CLI with tiny parameters.

**Purpose:** confirm the pipeline produces a valid markdown report on real data before launching the full multi-hour run.

- [ ] **Step 1: Run a tiny grid on EN only, 20 samples, Gliner2 only**

Run:
```bash
uv run python -m benchmarks.chunking grid \
    --detectors gliner2 \
    --languages en \
    --phase1-limit 20 \
    --output benchmarks/CHUNKING_RESULTS_smoke.md \
    --json benchmarks/chunking_smoke.json
```

Expected: report file created, no exceptions, report contains `# Chunked Detector Benchmark Results` and `gliner2`.

- [ ] **Step 2: Inspect the report**

Run: `head -30 benchmarks/CHUNKING_RESULTS_smoke.md`
Expected: see winner config, per-bucket table, top-5 configs.

- [ ] **Step 3: Commit**

```bash
git add benchmarks/CHUNKING_RESULTS_smoke.md benchmarks/chunking_smoke.json
git commit -m "chore(bench): capture smoke run output for chunking grid"
```

---

## Task 11: Full grid run

**Files:**
- Generated: `benchmarks/CHUNKING_RESULTS.md`, `benchmarks/chunking_full.json`

**Warning:** this can take several hours depending on hardware. Run on a machine with GPU if possible.

- [ ] **Step 1: Launch full run**

Run:
```bash
uv run python -m benchmarks.chunking grid \
    --phase1-limit 200 \
    --output benchmarks/CHUNKING_RESULTS.md \
    --json benchmarks/chunking_full.json \
    2>&1 | tee benchmarks/chunking_run.log
```

Expected: report and JSON produced, log file records per-config timing.

- [ ] **Step 2: Review results**

Inspect `benchmarks/CHUNKING_RESULTS.md` for:
- winners per `(detector, language)`
- whether chunking wins over baseline on the `>1024` bucket
- any configs where precision dropped below 0.80

- [ ] **Step 3: Commit results**

```bash
git add benchmarks/CHUNKING_RESULTS.md benchmarks/chunking_full.json benchmarks/chunking_run.log
git commit -m "chore(bench): record full chunking benchmark run"
```

---

## Task 12: Phase 2 — long-text evaluation

**Files:**
- Modify: `benchmarks/chunking/__main__.py` (add `phase2` subcommand)
- Create: `benchmarks/chunking/phase2.py`

**Purpose:** take the per-`(detector, language)` winners from phase 1, re-run on 1000 real samples + synthetic long texts, produce a comparison report chunked vs baseline.

- [ ] **Step 1: Write `phase2.py`**

Write `benchmarks/chunking/phase2.py`:

```python
"""Phase 2: re-evaluate winner vs baseline on larger sample + synthetic long texts."""

from __future__ import annotations

import json
from pathlib import Path

from benchmarks.chunking.buckets import BUCKET_ORDER, bucket_of
from benchmarks.chunking.confidence import filter_by_confidence
from benchmarks.chunking.grid import GridConfig
from benchmarks.chunking.synthetic import concat_samples
from benchmarks.dataset import BenchmarkSample, load_samples
from benchmarks.label_map import LabelMapping
from benchmarks.metrics import MatchMode, MetricsResult, compute_detection_metrics
from piighost.detector.base import AnyDetector
from piighost.detector.chunked import ChunkedDetector


def load_winners(path: str) -> dict[tuple[str, str], GridConfig]:
    """Parse phase 1 JSON output into per-key winning configs."""
    data = json.loads(Path(path).read_text())
    winners: dict[tuple[str, str], GridConfig] = {}
    for key, rows in data.items():
        detector, lang = key.split("|", 1)
        # Pick recall-winner under precision >= 0.80
        eligible = [r for r in rows if r["precision"] >= 0.80]
        if not eligible:
            continue
        best = max(eligible, key=lambda r: (r["recall"], r["f1"]))
        cfg = best["config"]
        winners[(detector, lang)] = GridConfig(
            chunk_size=cfg["chunk_size"],
            overlap=cfg["overlap"],
            threshold=cfg["threshold"],
        )
    return winners


def _synthesize_long_samples(
    samples: list[BenchmarkSample], count: int, per_bundle: int = 5
) -> list[BenchmarkSample]:
    """Build ``count`` synthetic long samples by concatenating ``per_bundle`` short ones."""
    short = [s for s in samples if len(s.source_text) < 256]
    synth: list[BenchmarkSample] = []
    for i in range(count):
        bundle = short[i * per_bundle : (i + 1) * per_bundle]
        if len(bundle) < per_bundle:
            break
        synth.append(concat_samples(bundle))
    return synth


async def evaluate(
    detector_factory,
    samples: list[BenchmarkSample],
    config: GridConfig,
    label_map: LabelMapping,
) -> tuple[MetricsResult, dict[str, MetricsResult]]:
    """Run a single config on ``samples`` and return aggregate + per-bucket metrics."""
    base = detector_factory(0.0)
    detector: AnyDetector = (
        ChunkedDetector(detector=base, chunk_size=config.chunk_size, overlap=config.overlap)
        if config.chunk_size is not None and config.overlap is not None
        else base
    )

    per_sample_dets = []
    for s in samples:
        raw = await detector.detect(s.source_text)
        per_sample_dets.append(filter_by_confidence(raw, config.threshold))

    golds = [g for s in samples for g in s.annotations]
    preds = [p for ps in per_sample_dets for p in ps]
    agg = compute_detection_metrics(list(golds), preds, label_map, MatchMode.PARTIAL)

    per_bucket: dict[str, MetricsResult] = {}
    for bucket in BUCKET_ORDER:
        bs = [
            (s, dets) for s, dets in zip(samples, per_sample_dets, strict=True)
            if bucket_of(len(s.source_text)) == bucket
        ]
        if not bs:
            continue
        bg = [g for s, _ in bs for g in s.annotations]
        bp = [p for _, f in bs for p in f]
        per_bucket[bucket] = compute_detection_metrics(list(bg), bp, label_map, MatchMode.PARTIAL)

    return agg, per_bucket


async def run_phase2(
    winners: dict[tuple[str, str], GridConfig],
    factory_for,  # Callable[[str], factory]
    label_map_for,  # Callable[[str], LabelMapping]
    real_limit: int = 1000,
    synth_count: int = 100,
) -> str:
    """Run phase 2 for every (detector, language) winner and return markdown."""
    lines: list[str] = ["# Chunked Detector Benchmark — Phase 2\n"]

    for (detector, lang), winner in sorted(winners.items()):
        factory = factory_for(detector)
        label_map = label_map_for(detector)

        real_samples = load_samples(split="validation", language=lang, limit=real_limit)
        synth_samples = _synthesize_long_samples(real_samples, count=synth_count)

        # Chunked config
        w_agg, w_buckets = await evaluate(factory, real_samples, winner, label_map)
        w_synth_agg, _ = await evaluate(factory, synth_samples, winner, label_map)

        # Baseline (same threshold, no chunking)
        baseline_cfg = GridConfig(
            chunk_size=None, overlap=None, threshold=winner.threshold
        )
        b_agg, b_buckets = await evaluate(factory, real_samples, baseline_cfg, label_map)
        b_synth_agg, _ = await evaluate(factory, synth_samples, baseline_cfg, label_map)

        lines.append(f"## {detector} / {lang}\n")
        lines.append(
            f"Winner: cs={winner.chunk_size}, ov={winner.overlap}, th={winner.threshold}\n"
        )
        lines.append("### Real-data comparison\n")
        lines.append("| Variant | P | R | F1 |")
        lines.append("|---|---|---|---|")
        lines.append(f"| Winner | {w_agg.precision:.3f} | {w_agg.recall:.3f} | {w_agg.f1:.3f} |")
        lines.append(f"| Baseline (same th) | {b_agg.precision:.3f} | {b_agg.recall:.3f} | {b_agg.f1:.3f} |")

        lines.append("\n### Per-bucket comparison\n")
        lines.append("| Bucket | Winner F1 | Baseline F1 | Delta |")
        lines.append("|---|---|---|---|")
        for bucket in BUCKET_ORDER:
            wf = w_buckets.get(bucket)
            bf = b_buckets.get(bucket)
            if wf is None or bf is None:
                continue
            lines.append(
                f"| {bucket} | {wf.f1:.3f} | {bf.f1:.3f} | {wf.f1 - bf.f1:+.3f} |"
            )

        lines.append("\n### Synthetic long texts (concat of 5 short samples)\n")
        lines.append("| Variant | P | R | F1 |")
        lines.append("|---|---|---|---|")
        lines.append(f"| Winner | {w_synth_agg.precision:.3f} | {w_synth_agg.recall:.3f} | {w_synth_agg.f1:.3f} |")
        lines.append(f"| Baseline | {b_synth_agg.precision:.3f} | {b_synth_agg.recall:.3f} | {b_synth_agg.f1:.3f} |")
        lines.append("")

    return "\n".join(lines)
```

- [ ] **Step 2: Add `phase2` subcommand to CLI**

Edit `benchmarks/chunking/__main__.py`; in `_build_parser()` add below the existing `eval` subparser:

```python
    p2 = sp.add_parser("phase2", help="Re-evaluate winners on 1000 samples + synthetic long texts")
    p2.add_argument("--winners-json", required=True, help="Path to phase 1 JSON output")
    p2.add_argument("--real-limit", type=int, default=1000)
    p2.add_argument("--synth-count", type=int, default=100)
    p2.add_argument("--output", default="benchmarks/CHUNKING_RESULTS_PHASE2.md")
```

And add dispatch in `main()`:

```python
    elif args.cmd == "phase2":
        asyncio.run(_run_phase2(args))
```

Add the handler:

```python
async def _run_phase2(args: argparse.Namespace) -> None:
    from benchmarks.chunking.phase2 import load_winners, run_phase2

    winners = load_winners(args.winners_json)

    def factory_for(detector: str):
        return _factory_for(detector)

    def label_map_for(detector: str):
        return _LABEL_MAPS[detector]

    md = await run_phase2(
        winners=winners,
        factory_for=factory_for,
        label_map_for=label_map_for,
        real_limit=args.real_limit,
        synth_count=args.synth_count,
    )
    from pathlib import Path as _P
    _P(args.output).write_text(md)
    sys.stderr.write(f"Phase 2 report written to {args.output}\n")
```

- [ ] **Step 3: Smoke-test phase 2 on the smoke JSON**

Run:
```bash
uv run python -m benchmarks.chunking phase2 \
    --winners-json benchmarks/chunking_smoke.json \
    --real-limit 20 \
    --synth-count 5 \
    --output benchmarks/CHUNKING_RESULTS_PHASE2_smoke.md
```

Expected: report produced, no exceptions, contains at least one `##` section.

- [ ] **Step 4: Commit phase 2 code and smoke output**

```bash
git add benchmarks/chunking/phase2.py benchmarks/chunking/__main__.py benchmarks/CHUNKING_RESULTS_PHASE2_smoke.md
git commit -m "feat(bench): add phase 2 evaluation with synthetic long texts"
```

- [ ] **Step 5: Run full phase 2**

Run:
```bash
uv run python -m benchmarks.chunking phase2 \
    --winners-json benchmarks/chunking_full.json \
    --output benchmarks/CHUNKING_RESULTS_PHASE2.md
```

Expected: final report produced.

- [ ] **Step 6: Commit final phase 2 report**

```bash
git add benchmarks/CHUNKING_RESULTS_PHASE2.md
git commit -m "chore(bench): record full phase 2 chunking benchmark"
```

---

## Task 13: Open pull request

**Files:**
- None; GitHub operation.

- [ ] **Step 1: Push branch and open PR**

Run:
```bash
git push -u origin feat/chunking-benchmark
gh pr create --title "feat(bench): chunking grid search benchmark" --body "$(cat <<'EOF'
## Summary
- Add `benchmarks/chunking/` subpackage with grid search, length bucketing, synthetic long-text generation, winner selection, markdown report
- Phase 1 CLI: `python -m benchmarks.chunking grid`
- Phase 2 CLI: `python -m benchmarks.chunking phase2 --winners-json ...`
- Benchmarks the effect of `ChunkedDetector` on `Gliner2Detector` and `TransformersDetector` across all 6 dataset languages

## Test plan
- [ ] `uv run pytest tests/benchmarks/chunking/ -v` — unit tests pass
- [ ] `uv run pytest tests/benchmarks/chunking/test_posthoc_assumption.py -m slow` — post-hoc threshold assumption holds for GLiNER2
- [ ] Smoke run `python -m benchmarks.chunking grid --detectors gliner2 --languages en --phase1-limit 20` produces report
- [ ] Review `benchmarks/CHUNKING_RESULTS.md` and `benchmarks/CHUNKING_RESULTS_PHASE2.md` for sanity
EOF
)"
```

---

## Self-Review (done before handoff)

**Spec coverage:**
- Detectors (Gliner2 + Transformers multilingual): Task 8 `_factory_for` ✓
- Languages × all 6: Task 8 CLI default ✓
- Grid axes: Task 1 ✓
- Baseline in grid: Task 1 (`is_baseline`) ✓
- Phase 1 200 samples / Phase 2 1000 samples: Task 8 (`--phase1-limit`) and Task 12 (`--real-limit`) ✓
- Post-hoc threshold optimization + validation: Task 6 grid_runner + Task 9 smoke ✓
- Bucketization: Task 2 + Task 6 per-bucket aggregation ✓
- Synthetic long texts: Task 3 + Task 12 (_synthesize_long_samples) ✓
- Recall @ precision ≥ 0.80 winner selection: Task 5 + Task 8 ✓
- Markdown report: Task 7 + Task 12 ✓

**Placeholder scan:** no TBD / TODO / "implement later". Error handling is concrete (skip invalid, log, ValueError). All code blocks complete.

**Type consistency:** `GridConfig`, `GridResult`, `ScoredConfig`, `BenchmarkSample`, `GoldAnnotation`, `MetricsResult`, `LabelMapping`, `MatchMode`, `Detection` used consistently across tasks; method names (`iterate_grid`, `bucket_of`, `concat_samples`, `filter_by_confidence`, `pick_winner`, `run_grid`, `render_grid_report`) match between tasks and their call sites.

