# Hacienda Ghost

> Le fantôme qui protège vos données dans votre hacienda numérique.

**Hacienda Ghost** est un middleware de souveraineté des données pour agents IA. Il détecte automatiquement les informations personnelles (PII) dans vos prompts, les remplace par des jetons opaques avant envoi au LLM, puis les réhydrate dans la réponse. Aucune donnée sensible ne quitte jamais votre poste.

Conçu pour les professionnels européens (avocats, médecins, notaires, DPO, cabinets de conseil) soumis au **RGPD** et au futur **AI Act** (Règlement IA européen).

---

## Table des matières

- [Fonctionnalités](#fonctionnalités)
- [Conformité RGPD & AI Act](#conformité-rgpd--ai-act)
- [Isolation par projet (gestion des dossiers)](#isolation-par-projet-gestion-des-dossiers)
- [Installation dans Claude Desktop](#installation-dans-claude-desktop)
- [Installation Docker](#installation-docker)
- [Installation automatique par Claude](#installation-automatique-par-claude)
- [Utilisation](#utilisation)
- [Architecture](#architecture)
- [Licence](#licence)

---

## Fonctionnalités

### Détection & anonymisation

- **Détection PII multi-moteur** — Combine des détecteurs basés sur des règles (regex), des modèles NER (GLiNER, multilingue) et des heuristiques contextuelles pour identifier noms, adresses, emails, numéros de téléphone, IBAN, numéros de sécurité sociale, dates de naissance, etc.
- **Résolution de spans** — Fusionne automatiquement les détections imbriquées ou chevauchantes pour garantir des entités propres et non redondantes.
- **Liaison d'entités (entity linking)** — Relie les différentes mentions d'une même personne même avec des fautes de frappe ou des variantes (« M. Dupont » = « Jean Dupont » = « Jean D. »).
- **Placeholders déterministes** — Chaque entité détectée est remplacée par un jeton opaque stable (`<PERSON:a3f8...>`) qui survit aux passages multiples dans le LLM.
- **Réhydratation fidèle** — Restaure les valeurs originales dans la réponse du LLM, même si ce dernier cite partiellement le jeton.
- **Coffre-fort chiffré (AES-256-GCM)** — Les valeurs originales sont stockées chiffrées localement, jamais exposées dans les logs ni dans les messages d'erreur.

### Indexation & recherche (RAG)

- **Ingestion documentaire** — PDF, DOCX, XLSX, ODT, TXT, Markdown via Kreuzberg (OCR intégré).
- **Recherche hybride** — Combine BM25 (mots-clés) et recherche vectorielle (embeddings multilingues `multilingual-e5`) pour une précision maximale, même sur des documents anonymisés.
- **Reranking** — Modèle cross-encoder (`BAAI/bge-reranker-base`) pour réordonner les résultats selon la pertinence sémantique.
- **Filtres de requête** — Restreignez la recherche à un préfixe de chemin ou à une liste d'ID de documents (`QueryFilter`).
- **Streaming sûr** — La réhydratation en streaming utilise un buffer à fenêtre glissante qui empêche toute fuite de jetons partiels vers l'utilisateur.
- **Cache de réponses** — Les requêtes identiques retournent instantanément sans ré-invoquer le LLM (backend aiocache, TTL configurable).

### Intégrations

- **LangChain** — Retrievers, middlewares, `PIIGhostRAG` pipeline clé-en-main.
- **Haystack** — Composants pipeline compatibles, `CachedRagPipeline` et `streaming_callback`.
- **MCP (Model Context Protocol)** — Bundle Claude Desktop prêt à l'emploi.
- **CLI** — `piighost` binaire pour ingestion, requête et gestion du coffre-fort.
- **Démon local** — Serveur JSON-RPC pour intégration avec d'autres applications desktop.

---

## Conformité RGPD & AI Act

### RGPD — Règlement Général sur la Protection des Données (UE 2016/679)

Hacienda Ghost est conçu par défaut pour la conformité RGPD. Les principes suivants sont appliqués :

| Principe RGPD | Mise en œuvre |
|---|---|
| **Art. 5(1)(b) — Limitation des finalités** | Les données PII sont traitées uniquement pour l'anonymisation locale. Aucune transmission à des tiers. |
| **Art. 5(1)(c) — Minimisation** | Seuls les jetons opaques sont envoyés au LLM distant. Les valeurs originales restent dans votre coffre-fort local. |
| **Art. 5(1)(f) — Intégrité & confidentialité** | Coffre-fort chiffré AES-256-GCM, clé dérivée par utilisateur, stockée hors du projet. |
| **Art. 17 — Droit à l'effacement** | Commande `piighost vault delete` pour supprimer un jeton et sa valeur originale. Suppression de projet : `piighost project delete`. |
| **Art. 20 — Droit à la portabilité** | Export JSON des documents indexés, placeholders et métadonnées. |
| **Art. 25 — Privacy by design** | Aucune PII n'est jamais loggée. Les erreurs sont expurgées. Invariant critique vérifié à chaque test. |
| **Art. 30 — Registre des traitements** | Journal d'audit local (append-only) de chaque opération d'anonymisation et de révélation. |
| **Art. 32 — Sécurité du traitement** | Chiffrement en transit (HTTPS vers le LLM) et au repos (AES-256-GCM). Clé de coffre jamais loggée. |
| **Art. 33 — Notification de violation** | Détection de tentatives d'accès non autorisé via les logs d'audit. |
| **Art. 44-49 — Transferts hors UE** | Les PII n'étant pas transférées au LLM, les transferts vers des LLM hors UE (OpenAI, Anthropic US, etc.) ne constituent plus un transfert de données personnelles au sens du RGPD. |

### AI Act — Règlement européen sur l'intelligence artificielle (UE 2024/1689)

L'AI Act entre en application progressivement jusqu'en 2026. Hacienda Ghost facilite la conformité pour les systèmes IA à haut risque et les obligations de transparence :

| Article AI Act | Mise en œuvre |
|---|---|
| **Art. 10 — Gouvernance des données** | Les données d'entraînement ou de contexte envoyées aux LLM sont tracées, anonymisées et journalisées. |
| **Art. 12 — Journalisation** | Journal d'audit horodaté de chaque interaction avec un LLM (requête anonymisée + réponse réhydratée). |
| **Art. 13 — Transparence & information des utilisateurs** | Les jetons `<LABEL:hash>` sont explicites — l'utilisateur sait qu'une anonymisation a eu lieu. |
| **Art. 14 — Contrôle humain** | Le coffre-fort permet la révélation contrôlée (`vault show --reveal`) avec journalisation de l'accès. |
| **Art. 15 — Exactitude, robustesse, cybersécurité** | Tests d'invariants (fail-closed : si l'anonymisation échoue, aucun texte partiel n'est renvoyé). |
| **Art. 50 — Obligations de transparence pour deepfakes et contenu IA** | Les réponses LLM peuvent être marquées comme étant d'origine IA via la métadonnée RAG. |

### Souveraineté des données

- **Tout est local par défaut** — Indexation, embeddings, reranking, coffre-fort : tout tourne sur votre machine.
- **Aucune télémétrie** — Aucun appel sortant sauf vers le LLM que vous configurez explicitement.
- **Choix du LLM** — Compatible avec les LLM européens (Mistral, LightOn) ou les LLM locaux (Ollama, vLLM, LM Studio).
- **Audit local** — Le journal d'audit reste sur votre disque, jamais envoyé vers un serveur distant.

---

## Isolation par projet (gestion des dossiers)

Hacienda Ghost isole strictement les données par **projet**. Un projet est une unité logique avec son propre index, son propre coffre-fort et ses propres métadonnées. Aucune fuite possible entre projets.

### Principe

```
~/.hacienda-ghost/
├── vaults/
│   ├── client-dupont/          # Projet 1 — totalement isolé
│   │   ├── vault.db            # Coffre-fort chiffré (clé propre)
│   │   ├── index.lance/        # Index vectoriel
│   │   └── bm25/               # Index BM25
│   ├── dossier-medical-smith/  # Projet 2 — aucune visibilité sur projet 1
│   │   ├── vault.db
│   │   ├── index.lance/
│   │   └── bm25/
│   └── default/                # Projet par défaut
└── audit.log                   # Journal d'audit global (append-only)
```

### Garanties d'isolation

- **Clés de chiffrement séparées** — Chaque projet a sa propre clé AES-256 dérivée. La compromission d'un projet ne met pas en danger les autres.
- **Jetons non portables** — Le hash `<PERSON:a3f8...>` du projet A n'a aucune signification dans le projet B. Impossible de mélanger les contextes.
- **Recherche cloisonnée** — `svc.query(..., project="client-dupont")` ne retournera jamais un chunk d'un autre projet.
- **Cache de RAG cloisonné** — La clé de cache inclut l'ID du projet : `project="a"` et `project="b"` produisent des entrées distinctes même pour la même question.
- **Suppression atomique** — `piighost project delete client-dupont` efface intégralement le projet (index, coffre, cache) en une opération.

### Commandes de gestion

```bash
# Créer un nouveau projet
piighost project create client-dupont --description "Dossier contentieux M. Dupont"

# Lister les projets
piighost project list

# Indexer dans un projet spécifique
piighost index ~/docs/client-dupont --project client-dupont

# Requêter dans un projet
piighost query "Qui est le défendeur ?" --project client-dupont

# Supprimer un projet (refuse par défaut si non-vide)
piighost project delete client-dupont --force
```

---

## Installation dans Claude Desktop

### Méthode 1 — Bundle MCPB (recommandée)

1. Téléchargez le bundle depuis la page [GitHub Releases](https://github.com/jamon8888/hacienda-ghost/releases/latest) :
   - **`hacienda-ghost-core.mcpb`** — anonymisation + coffre-fort seul (~50 Mo, installation rapide).
   - **`hacienda-ghost-full.mcpb`** — inclut l'indexation documentaire et le RAG (~1.5 Go, dépendances lourdes : torch, sentence-transformers).

2. **Double-cliquez sur le fichier `.mcpb`** — Claude Desktop ouvre automatiquement la fenêtre d'installation.

3. Confirmez l'installation et choisissez un **répertoire de coffre-fort** (par exemple `~/Documents/hacienda-vault`).

4. Redémarrez Claude Desktop. Les outils Hacienda Ghost apparaissent dans le menu des outils MCP :
   - `anonymize_text`
   - `rehydrate_text`
   - `index_path`
   - `query`
   - `vault_search` / `vault_show`
   - `list_projects` / `create_project` / `delete_project`

5. Au premier appel, UV installe automatiquement les dépendances Python (quelques minutes la première fois, instantané ensuite).

### Méthode 2 — Configuration manuelle

Éditez votre fichier `claude_desktop_config.json` :

- **macOS** : `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows** : `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux** : `~/.config/Claude/claude_desktop_config.json`

Ajoutez la section MCP suivante :

```json
{
  "mcpServers": {
    "hacienda-ghost": {
      "command": "uvx",
      "args": [
        "--from", "piighost",
        "piighost-mcp",
        "--vault-dir", "/chemin/vers/votre/vault"
      ],
      "env": {
        "PIIGHOST_DETECTOR": "gliner2",
        "PIIGHOST_EMBEDDER": "multilingual-e5"
      }
    }
  }
}
```

Redémarrez Claude Desktop.

---

## Installation Docker

Pour les cabinets et les professionnels qui préfèrent une installation
isolée et reproductible, piighost fournit une pile Docker complète avec
deux profils et des images signées.

### Prérequis

- **Docker Engine** ≥ 24, avec `docker compose` v2 (`docker compose version`)
- **4 Go de RAM** et **10 Go de disque** pour l'image `slim`
- **16 Go de RAM** et **40 Go de disque** pour l'image `full` (NER GLiNER, embeddings locaux)
- Un nom de domaine pointant vers la machine (profil `server` uniquement, pour Let's Encrypt)

### Démarrage « poste de travail »

Pour un professionnel solo utilisant Claude Desktop sur son ordinateur :

```bash
git clone https://github.com/jamon8888/hacienda-ghost
cd hacienda-ghost

# Génère les secrets (clé de coffre, paire age, fichier .env)
make install

# Démarre la pile en profil « poste de travail »
make up
```

Claude Desktop se connecte ensuite à `http://127.0.0.1:8765` (MCP exposé
uniquement sur la boucle locale, aucun port ouvert à l'extérieur).

Pour vérifier l'état :

```bash
make status
```

### Déploiement « serveur de cabinet »

Pour un cabinet avec plusieurs postes clients derrière un pare-feu :

```bash
# Adapter le fichier .env
sed -i 's/COMPOSE_PROFILES=workstation/COMPOSE_PROFILES=server/' .env
sed -i 's/PIIGHOST_PUBLIC_HOSTNAME=.*/PIIGHOST_PUBLIC_HOSTNAME=piighost.cabinet.local/' .env
sed -i 's/CADDY_EMAIL=.*/CADDY_EMAIL=dpo@cabinet.local/' .env

# Créer un premier jeton client
docker compose run --rm piighost-daemon \
    piighost token create --name "poste-durand"
# → copier le jeton affiché dans la configuration Claude Desktop du poste

# Démarrer
make up-server
```

Caddy obtient automatiquement un certificat TLS via Let's Encrypt et
applique l'authentification par jeton bearer. Pour passer en mTLS :

```bash
echo "PIIGHOST_AUTH=mtls" >> .env
make up-server
```

### Overlays optionnels — souveraineté totale

Pour supprimer toute dépendance à des services cloud externes
(embeddings via Mistral, LLM via Anthropic/OpenAI), activez les overlays :

```bash
# Embedder local (sentence-transformers) — l'indexation RAG devient hors-ligne
docker compose --profile server \
    -f docker-compose.yml \
    -f docker-compose.embedder.yml \
    up -d

# Stack souveraine complète : anonymisation + embedder + LLM (Ollama)
make up-sovereign
```

Le réseau `piighost-llm` est marqué `internal: true` : Ollama ne peut
communiquer qu'avec piighost, jamais avec Internet.

### Sauvegardes

Une sauvegarde quotidienne chiffrée avec `age` est activée par défaut
(02:30 locale). Les archives atterrissent dans `./backups/` au format
`piighost-AAAA-MM-JJ.tar.age` avec une rétention de **7 jours + 4 semaines**.

Sauvegarde immédiate :

```bash
make backup
```

Restauration depuis une archive :

```bash
make restore BACKUP=./backups/piighost-2026-04-20.tar.age
```

La clé privée age (`docker/secrets/age.key`) doit être conservée **hors
de la machine** : papier, HSM, ou gestionnaire de mots de passe d'un
associé. Perdre cette clé rend les sauvegardes irrécupérables.

Pour désactiver la sauvegarde automatique (si vous utilisez déjà Restic,
Borg, ou une solution entreprise) :

```bash
COMPOSE_PROFILES=workstation,no-backup make up
```

### Mises à jour

Les images sont épinglées par **digest SHA-256** dans
`docker-compose.yml`, jamais par tag mutable. Pour mettre à jour :

```bash
piighost self-update         # ou : make update
docker compose pull
docker compose up -d
```

Cette commande :

1. Récupère le dernier digest depuis GHCR
2. **Vérifie la signature `cosign`** (OIDC keyless, émise par GitHub Actions)
3. Affiche le diff et demande confirmation
4. Réécrit `docker-compose.yml` avec le nouveau digest

Pour revenir en arrière : `git revert` sur le commit de mise à jour puis
`docker compose up -d`.

Un sidecar `piighost-update-notify` vérifie chaque nuit la présence
d'une nouvelle version et écrit un message sur stderr ainsi qu'un
fichier `/var/lib/piighost/update-available.json`. Il ne touche jamais
à la pile en cours.

### Vérification manuelle de la signature d'image

```bash
cosign verify \
    --certificate-identity-regexp 'https://github\.com/jamon8888/.*' \
    --certificate-oidc-issuer 'https://token.actions.githubusercontent.com' \
    ghcr.io/jamon8888/hacienda-ghost:slim
```

La commande doit afficher une signature valide. En cas d'échec, **ne
déployez pas l'image** — ouvrez un ticket immédiatement.

### Posture de sécurité

Chaque conteneur de la pile applique par défaut :

- **Utilisateur non-root** (UID 10001)
- **Système de fichiers en lecture seule** (`read_only: true`, `tmpfs` pour `/tmp` et `/run`)
- **Toutes les capacités Linux abandonnées** (`cap_drop: [ALL]`)
- **`no-new-privileges: true`** et profil seccomp par défaut
- **Secrets via Docker secrets** — jamais via variables d'environnement (éviterait les fuites via `docker inspect`)
- **Base distroless** (`slim`) ou Chainguard (`full`) — pas de shell, pas de gestionnaire de paquets, surface d'attaque minimale
- **Réseau interne** (`internal: true`) pour le daemon et l'overlay LLM — aucun egress

### Dépannage

| Symptôme | Cause probable | Remède |
|---|---|---|
| `make up` échoue sur `secrets` | `docker/secrets/vault-key.txt` manquant | `make install` |
| MCP inaccessible depuis Claude Desktop | Pare-feu bloque 8765 (workstation) | Vérifier `netstat -an \| grep 8765` |
| Caddy ne récupère pas de certificat TLS | DNS incorrect ou port 80/443 bloqué | `docker compose logs caddy` |
| Image trop grosse au téléchargement | Utilisation de `full` au lieu de `slim` | `PIIGHOST_TAG=slim make up` |
| Sauvegarde échoue avec « recipient file is empty » | `docker/secrets/age-recipient.txt` vide | Régénérer via `age-keygen -y age.key > age-recipient.txt` |

Logs détaillés :

```bash
docker compose logs -f piighost-mcp piighost-daemon
```

Remise à zéro complète (⚠ destructive — supprime toutes les données) :

```bash
make clean
```

---

## Installation automatique par Claude

Vous pouvez laisser Claude installer Hacienda Ghost pour vous. Copiez-collez simplement le prompt suivant dans Claude Desktop :

> **Prompt à donner à Claude :**
>
> ````
> Installe Hacienda Ghost localement sur ma machine et configure-le dans Claude Desktop. Voici les étapes :
>
> 1. Vérifie que `uv` est installé (https://docs.astral.sh/uv/) — sinon installe-le avec la commande officielle de mon système d'exploitation.
> 2. Crée un dossier `~/Documents/hacienda-vault` pour le coffre-fort si il n'existe pas.
> 3. Installe le paquet via `uv tool install piighost[mcp]`.
> 4. Initialise le coffre-fort avec `piighost --init --vault-dir ~/Documents/hacienda-vault`. Note la clé de coffre générée (`CLOAKPIPE_VAULT_KEY`) et conserve-la dans un gestionnaire de mots de passe.
> 5. Ouvre le fichier de configuration Claude Desktop :
>    - macOS : `~/Library/Application Support/Claude/claude_desktop_config.json`
>    - Windows : `%APPDATA%\Claude\claude_desktop_config.json`
>    - Linux : `~/.config/Claude/claude_desktop_config.json`
> 6. Ajoute la section `mcpServers.hacienda-ghost` en préservant les autres serveurs MCP existants. La commande doit pointer vers `uvx`, utiliser `--from piighost piighost-mcp --vault-dir <chemin vault>`, et définir la variable d'environnement `CLOAKPIPE_VAULT_KEY` avec la clé générée à l'étape 4.
> 7. Crée un projet de démarrage : `piighost project create demo --description "Projet de test Hacienda Ghost"`.
> 8. Affiche un récapitulatif : chemin du coffre-fort, nom du projet créé, emplacement du fichier de configuration Claude, et instructions pour redémarrer Claude Desktop.
>
> Ne modifie AUCUN autre fichier système. N'envoie AUCUNE donnée à l'extérieur. Confirme chaque étape avant de passer à la suivante.
> ````

Claude suivra ces étapes pas à pas en utilisant ses outils Bash/FileSystem, en vous demandant confirmation aux moments critiques.

---

## Utilisation

### Exemple minimal — anonymiser une conversation

```python
import asyncio
from piighost.service.core import PIIGhostService
from piighost.service.config import ServiceConfig

async def main():
    cfg = ServiceConfig()
    svc = await PIIGhostService.create(vault_dir="~/hacienda-vault", config=cfg)

    # Anonymise avant envoi au LLM
    anon = await svc.anonymize(
        "M. Jean Dupont habite au 12 rue de Rivoli à Paris.",
        project="demo"
    )
    print(anon.anonymized)
    # → "<PERSON:a3f8...> habite au <ADDRESS:b7e1...> à <LOCATION:c4d2...>."

    # ... envoyez anon.anonymized au LLM distant ...
    reponse_llm = "<PERSON:a3f8...> réside à <LOCATION:c4d2...>."

    # Réhydrate la réponse
    rehydrated = await svc.rehydrate(reponse_llm, project="demo")
    print(rehydrated.text)
    # → "M. Jean Dupont réside à Paris."

asyncio.run(main())
```

### Exemple RAG — interroger un dossier anonymisé

```python
from piighost.integrations.langchain.rag import PIIGhostRAG
from piighost.integrations.langchain.cache import RagCache
from piighost.indexer.filters import QueryFilter
from langchain_openai import ChatOpenAI

rag = PIIGhostRAG(svc, project="client-dupont", cache=RagCache(ttl=300))

# Indexer un dossier
await rag.ingest("~/docs/client-dupont/")

# Requête filtrée + reranking + cache
llm = ChatOpenAI(model="gpt-4")
answer = await rag.query(
    "Quelle est la date du procès-verbal ?",
    llm=llm,
    filter=QueryFilter(file_path_prefix="~/docs/client-dupont/2024/"),
    rerank=True,
    top_n=20,
)
print(answer)
# → Aucune PII n'a été envoyée au LLM ; la réponse est réhydratée localement.
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Utilisateur / Claude Desktop                               │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│  MCP Server (hacienda-ghost)                                │
│    Tools: anonymize_text, query, vault_search, ...          │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│  PIIGhostService (multiplexeur multi-projet)                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ Projet A     │  │ Projet B     │  │ Projet C     │       │
│  │ - Vault AES  │  │ - Vault AES  │  │ - Vault AES  │       │
│  │ - Index      │  │ - Index      │  │ - Index      │       │
│  │ - BM25       │  │ - BM25       │  │ - BM25       │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
└─────────────────────┬───────────────────────────────────────┘
                      │ (jetons opaques uniquement)
┌─────────────────────▼───────────────────────────────────────┐
│  LLM (Claude, Mistral, GPT, Ollama local, ...)              │
│  Ne voit JAMAIS les PII originales.                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Licence

MIT — voir [LICENSE](LICENSE).

## Support

- **Documentation** : [athroniaeth.github.io/piighost](https://athroniaeth.github.io/piighost/)
- **Issues** : [GitHub Issues](https://github.com/jamon8888/hacienda-ghost/issues)
- **Sécurité** : voir [SECURITY.md](SECURITY.md) pour signaler une vulnérabilité de manière responsable.

---

*Hacienda Ghost — le fantôme qui garde vos secrets.*
