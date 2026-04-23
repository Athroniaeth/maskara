---
icon: lucide/download
---

# Installation

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Basic installation

=== "uv"

    ```bash
    uv add piighost
    ```

=== "pip"

    ```bash
    pip install piighost
    ```

## Extras

`piighost` installs minimal by default (regex detectors only). NER detectors and the LangChain middleware are optional extras:

=== "uv"

    ```bash
    uv add piighost[gliner2]       # GLiNER2 NER detector
    uv add piighost[spacy]         # spaCy NER detector
    uv add piighost[transformers]  # transformers NER detector
    uv add piighost[langchain]     # LangChain / LangGraph middleware
    uv add piighost[client]        # HTTP client for piighost-api
    ```

=== "pip"

    ```bash
    pip install piighost[gliner2]
    pip install piighost[spacy]
    pip install piighost[transformers]
    pip install piighost[langchain]
    pip install piighost[client]
    ```

Extras compose: `piighost[gliner2,langchain]` installs both.

## Development installation

```bash
git clone https://github.com/Athroniaeth/piighost.git
cd piighost
uv sync
```

## Development commands

```bash
uv sync                              # Install dependencies
make lint                            # Format (ruff) + lint (ruff) + type-check (pyrefly)
uv run pytest                        # Run the full test suite
uv run pytest tests/ -k "test_name"  # Run a single test
```
