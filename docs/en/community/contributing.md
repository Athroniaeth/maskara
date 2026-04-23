---
icon: lucide/git-pull-request
---

# Contributing

Thanks for your interest in `piighost`. This page summarises the contribution workflow. For the authoritative version, see [`CONTRIBUTING.md`](https://github.com/Athroniaeth/piighost/blob/master/CONTRIBUTING.md) at the repository root.

## Prerequisites

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) as package manager
- A GitHub account

## Getting started

1. **Fork** the repository on GitHub.
2. **Clone** your fork locally:

    ```bash
    git clone https://github.com/YOUR-USERNAME/piighost.git
    cd piighost
    git remote add upstream https://github.com/Athroniaeth/piighost.git
    ```

3. **Install** dependencies:

    ```bash
    uv sync
    ```

## Workflow

### Create a branch

Always from `master`:

```bash
git checkout -b feat/my-feature
```

### Follow the conventions

- **Protocols** at every pipeline stage keep components swappable.
- **Frozen dataclasses** for data models (`Entity`, `Detection`, `Span`).
- **`ExactMatchDetector`** in tests, never a real NER model in CI.
- **Conventional commits** through Commitizen (`feat:`, `fix:`, `refactor:`, etc.).

### Local checks

Before opening a PR:

```bash
make lint       # Format + lint + type-check
uv run pytest   # Test suite
```

### Open the pull request

- Clear title following the Commitizen format.
- Description that explains the *why* rather than the *what*.
- Link the related issue (`Fixes #42`).
- Screenshots or output samples when relevant.

## Extension points

The most common places to contribute without touching the core:

- **New detector**: implement the `AnyDetector` protocol. See [Extending PIIGhost](../extending.md).
- **New regex pack**: add a module under `piighost/detector/patterns/`.
- **New validator**: a `Callable[[str], bool]` function in `piighost/validators.py`.
- **New placeholder factory**: implement `AnyPlaceholderFactory`.
