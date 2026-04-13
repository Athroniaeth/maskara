# Load environment variables from .env file if it exists
.PHONY: lint docs-build docs docs-watch docs-watch-fr

lint:
	-uv run ruff format .
	-uv run ruff check --fix .
	-uv run pyrefly check .

docs-build:
	uv run python -m zensical build
	uv run python -m zensical build -f zensical.fr.toml

docs:
	uv run python -m zensical build
	uv run python -m zensical build -f zensical.fr.toml
	python3 -m http.server 8000 --directory site

docs-watch:
	uv run python -m zensical serve -a localhost:8000 -o

docs-watch-fr:
	uv run python -m zensical serve -f zensical.fr.toml -a localhost:8001 -o
