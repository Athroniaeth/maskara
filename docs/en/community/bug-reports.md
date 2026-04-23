---
icon: lucide/bug
---

# Bug reports

A good bug report saves time for everyone. Before opening an issue, a few quick checks.

## Before opening an issue

1. **Check the version**: reproduce on the latest release (`pip install -U piighost` or `uv lock --upgrade-package piighost`).
2. **Search existing issues**: [open and closed issues](https://github.com/Athroniaeth/piighost/issues?q=is%3Aissue).
3. **Isolate the problem**: does the bug happen with `ExactMatchDetector` (which loads no NER model) or only with the NER detector? The difference helps locate the cause.

## What a good report contains

!!! example "Minimal template"
    - **`piighost` version** (`uv run python -c "import piighost; print(piighost.__version__)"`)
    - **Python version**
    - **Detector used** (GLiNER2, spaCy, regex, composite…)
    - **Minimal input** that reproduces the bug (a few lines, not a whole dataset)
    - **Observed output**
    - **Expected output**
    - **Full traceback** if an exception fires, inside a code block
    - **Environment**: OS, GPU/CPU, other detectors loaded

## What to avoid

- High-level reports like "anonymization doesn't work" without a reproducible example.
- Screenshots of code instead of a text block (cannot be copy-pasted to reproduce).
- Sharing real PII in the issue. Use fake values (`Alice Smith`, `Paris`, `alice@example.com`).

## Security vulnerabilities

**Do not** open a public issue for a vulnerability. Use the [private GitHub advisory reporting channel](https://github.com/Athroniaeth/piighost/security/advisories/new). See [Security](../security.md) for the threat model and what `piighost` does or does not protect against.

## Where to file

[github.com/Athroniaeth/piighost/issues/new](https://github.com/Athroniaeth/piighost/issues/new)
