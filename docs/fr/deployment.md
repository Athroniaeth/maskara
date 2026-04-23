---
icon: lucide/container
---

# Déployer `piighost-api`

[`piighost-api`](https://github.com/Athroniaeth/piighost-api) est distribué comme image Docker sur `ghcr.io/athroniaeth/piighost-api`. L'image de base (~218 Mo) ne contient que les détecteurs regex. Pour utiliser les détecteurs NER (GLiNER2, spaCy, transformers) ou des extras d'intégration (Faker, etc.), vous installez les extras via l'un des deux canaux disponibles :

- **`EXTRA_PACKAGES`** (runtime) : lu au démarrage du conteneur, `uv` installe les extras listés avant le boot du serveur.
- **`PIIGHOST_EXTRAS`** (build) : cuit dans une image custom via `docker build --build-arg PIIGHOST_EXTRAS="gliner2"`.

Le canal runtime est pratique pour prototyper mais télécharge plusieurs centaines de Mo de wheels (`torch`, `nvidia-*`, `triton`, `transformers`, …) à chaque démarrage du conteneur. Les stratégies ci-dessous permettent d'amortir ce coût.

---

## Cacher les packages optionnels

### Stratégie 1 — Cacher le dossier de téléchargement de `uv` (recommandé, gain rapide)

Ajoutez un volume nommé sur `/root/.cache/uv`. `uv` y conserve tous les wheels qu'il a déjà téléchargés ; au démarrage suivant, il évite le réseau et se contente de relier les fichiers dans le venv du conteneur. Le démarrage à froid passe typiquement de plusieurs minutes à quelques secondes, sans toucher à l'image.

```yaml
services:
  api:
    image: ghcr.io/athroniaeth/piighost-api:latest
    environment:
      - EXTRA_PACKAGES=piighost[gliner2]
    volumes:
      - ./pipeline.py:/app/pipeline.py
      - huggingface-cache:/root/.cache/huggingface  # poids des modèles
      - uv-cache:/root/.cache/uv                    # wheels Python

volumes:
  huggingface-cache:
  uv-cache:
```

!!! note
    Le volume `huggingface-cache` cache les poids de modèles téléchargés (GLiNER2, modèles transformers). Il est indépendant du cache des wheels et doit être conservé.

### Stratégie 2 — Cuire les extras dans une image custom (zéro install au runtime)

Pour les environnements où le temps de démarrage compte (CI, production, serverless), construisez votre propre image par-dessus `piighost-api`. Le `uv sync` tourne une seule fois au `docker build`, les extras sont cuits dans un layer d'image, et chaque démarrage suivant est instantané.

```dockerfile
# Dockerfile
FROM ghcr.io/athroniaeth/piighost-api:latest
RUN uv pip install --system "piighost[gliner2]"
```

```yaml
# compose.yml
services:
  api:
    build: ./piighost-api
    volumes:
      - ./pipeline.py:/app/pipeline.py
      - huggingface-cache:/root/.cache/huggingface
    # EXTRA_PACKAGES n'est plus necessaire
```

C'est l'option la plus reproductible : l'image est auto-suffisante, le cache de layers Docker gère les rebuilds, et aucune dépendance runtime sur la disponibilité de PyPI.

### Stratégie 3 — Monter le venv complet (démarrage le plus rapide, plus fragile)

Montez un volume nommé sur le chemin du venv de l'image, pour que les fichiers installés eux-mêmes persistent entre les runs. Le démarrage est quasi-instantané après le premier boot, au prix d'un cache qui peut silencieusement dériver si l'image upstream change de version Python ou de layout de venv.

```yaml
services:
  api:
    image: ghcr.io/athroniaeth/piighost-api:latest
    environment:
      - EXTRA_PACKAGES=piighost[gliner2]
    volumes:
      - piighost-venv:/app/.venv

volumes:
  piighost-venv:
```

!!! warning
    Si vous mettez à jour `ghcr.io/athroniaeth/piighost-api:latest`, purgez le volume du venv (`docker compose down -v`) avant le démarrage suivant — sinon l'ancien venv masque le nouveau et vous débugguez des mismatches de versions mystérieux.

---

## Laquelle choisir ?

| Scénario                                   | Stratégie recommandée              |
| ------------------------------------------ | ---------------------------------- |
| Développement local, redémarrages ponctuels | Stratégie 1 (cache `uv`)           |
| CI / production / versions figées          | Stratégie 2 (image custom)         |
| Boucle de dev rapide sur image de base figée | Stratégie 3 (volume venv)        |

Les stratégies 1 et 2 se composent très bien : gardez le cache `uv` sur votre machine de dev pour accélérer le `docker build`, et cuisez les extras dans l'image pour le déploiement.
