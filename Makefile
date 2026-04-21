# piighost — raccourcis d'installation Docker
# =============================================================================
# Cibles principales :
#   make install       Génère les secrets, prépare .env
#   make up            Démarre le profil workstation
#   make up-server     Démarre le profil server
#   make up-sovereign  Démarre server + embedder + LLM (stack souveraine)
#   make down          Arrête la pile
#   make logs          Suit les logs
#   make backup        Force une sauvegarde immédiate
#   make restore       BACKUP=chemin.tar.age — restaure depuis un fichier
#   make update        Met à jour via `piighost self-update`
#   make status        Affiche l'état courant
#   make clean         Supprime les volumes (DESTRUCTIF)

# Load environment variables from .env file if it exists
.PHONY: install up up-server up-sovereign down logs backup restore update status clean lint docs-build docs docs-watch docs-watch-fr

COMPOSE_BASE := docker-compose.yml
COMPOSE_EMBEDDER := docker-compose.embedder.yml
COMPOSE_LLM := docker-compose.llm.yml
COMPOSE_WORKSTATION_PORTS := docker-compose.workstation-ports.yml

install:
	@test -f .env || cp .env.example .env
	@mkdir -p docker/secrets backups
	@piighost docker init

up:
	docker compose -f $(COMPOSE_BASE) -f $(COMPOSE_WORKSTATION_PORTS) --profile workstation up -d

up-server:
	docker compose -f $(COMPOSE_BASE) --profile server up -d

up-sovereign:
	docker compose -f $(COMPOSE_BASE) -f $(COMPOSE_EMBEDDER) -f $(COMPOSE_LLM) --profile server up -d

down:
	docker compose --profile workstation --profile server down

logs:
	docker compose logs -f --tail=100

backup:
	docker compose exec -T piighost-backup bash /docker/scripts/backup.sh

restore:
	@test -n "$(BACKUP)" || (echo "usage: make restore BACKUP=./backups/piighost-YYYY-MM-DD.tar.age" && exit 1)
	docker compose down
	docker compose run --rm piighost-daemon bash /docker/scripts/restore.sh "$(BACKUP)"
	docker compose -f $(COMPOSE_BASE) -f $(COMPOSE_WORKSTATION_PORTS) --profile workstation up -d

update:
	piighost self-update

status:
	piighost docker status

clean:
	@echo "ATTENTION: cela va supprimer tous les volumes et données. Ctrl-C pour annuler."
	@sleep 5
	docker compose down -v

# Documentation and linting targets (legacy)
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
