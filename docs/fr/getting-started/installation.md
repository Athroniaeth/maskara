---
icon: lucide/download
---

# Installation

## Prérequis

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (recommandé) ou pip

## Installation basique

=== "uv"

    ```bash
    uv add piighost
    ```

=== "pip"

    ```bash
    pip install piighost
    ```

## Extras

`piighost` s'installe minimal par défaut (détecteurs regex seulement). Les détecteurs NER et le middleware LangChain sont des extras optionnels :

=== "uv"

    ```bash
    uv add piighost[gliner2]       # détecteur GLiNER2
    uv add piighost[spacy]         # détecteur spaCy
    uv add piighost[transformers]  # détecteur transformers
    uv add piighost[langchain]     # middleware LangChain/LangGraph
    uv add piighost[client]        # client HTTP pour piighost-api
    ```

=== "pip"

    ```bash
    pip install piighost[gliner2]
    pip install piighost[spacy]
    pip install piighost[transformers]
    pip install piighost[langchain]
    pip install piighost[client]
    ```

Les extras se combinent : `piighost[gliner2,langchain]` installe les deux.

## Installation pour le développement

```bash
git clone https://github.com/Athroniaeth/piighost.git
cd piighost
uv sync
```

## Commandes de développement

```bash
uv sync                              # Installer les dépendances
make lint                            # Format (ruff) + lint (ruff) + type-check (pyrefly)
uv run pytest                        # Lancer tous les tests
uv run pytest tests/ -k "test_name"  # Lancer un test spécifique
```
