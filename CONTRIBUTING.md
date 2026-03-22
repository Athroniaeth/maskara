# Contributing to Maskara

Thank you for your interest in contributing to Maskara! We welcome contributions from everyone.

## Prerequisites

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) package manager
- Git and a GitHub account

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/YOUR-USERNAME/maskara.git
   cd maskara
   ```
3. **Add upstream remote** for syncing:
   ```bash
   git remote add upstream https://github.com/Athroniaeth/maskara.git
   ```

## Development Workflow

### 1. Create a Feature Branch

Always branch from `master`:
```bash
git checkout -b feature/your-feature-name
```

### 2. Install Dependencies

```bash
uv sync
```

### 3. Make Your Changes

Follow the existing code style and patterns. Key conventions:
- **Protocols** for every pipeline stage — keep components swappable
- **Frozen dataclasses** for data models (`Entity`, `Placeholder`, `Span`, etc.)
- **`FakeDetector`** in tests — never load the real GLiNER2 model in CI

### 4. Quality Assurance

Run all checks before submitting:

```bash
make lint         # Format (ruff), lint (ruff), type-check (pyrefly)
uv run pytest     # Run tests
```

### 5. Commit Your Changes

Use [Conventional Commits](https://www.conventionalcommits.org/) via Commitizen:
```bash
cz commit
```

Follow the prompts to select commit type (`feat`, `fix`, `docs`, `refactor`, etc.).

## Pull Request Guidelines

1. **Target the `master` branch**
2. **Ensure all checks pass**:
   - `make lint` — no linting or type errors
   - `uv run pytest` — all tests green
3. **Add tests** for any new functionality
4. **Update documentation** if the public API changes
5. **Sync with upstream** if your branch diverged:
   ```bash
   git fetch upstream
   git rebase upstream/master
   git push --force-with-lease
   ```

### PR Checklist

- [ ] Code follows project style guidelines
- [ ] Tests pass locally (`make lint && uv run pytest`)
- [ ] New tests added for new functionality
- [ ] Documentation updated if needed
- [ ] Synced with upstream master

## Adding a New Pipeline Stage

New detector, occurrence finder, or placeholder factory implementations must:
- Implement the corresponding **protocol** (`EntityDetector`, `OccurrenceFinder`, `PlaceholderFactory`, `SpanValidator`)
- Include tests that use the protocol interface (not the concrete class)
- Not load heavy ML models in test code — use `FakeDetector` or equivalents

## Questions?

Open a [GitHub Discussion](https://github.com/Athroniaeth/maskara/discussions) or an issue. We're happy to help!

---

Thank you for contributing to Maskara!
