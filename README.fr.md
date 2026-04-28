# PIIGhost

[![CI](https://github.com/Athroniaeth/piighost/actions/workflows/ci.yml/badge.svg)](https://github.com/Athroniaeth/piighost/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/piighost.svg)](https://pypi.org/project/piighost/)
[![PyPI downloads](https://img.shields.io/pypi/dm/piighost.svg)](https://pypi.org/project/piighost/)
[![Python versions](https://img.shields.io/pypi/pyversions/piighost.svg)](https://pypi.org/project/piighost/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-online-blue.svg)](https://athroniaeth.github.io/piighost/)
[![Tested with pytest](https://img.shields.io/badge/tests-pytest-informational.svg)](https://pytest.org/)
[![Code style: Ruff](https://img.shields.io/badge/code%20style-ruff-4B32C3.svg)](https://docs.astral.sh/ruff/)
[![Security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://github.com/PyCQA/bandit)

[README EN](README.md) - [README FR](README.fr.md)

`piighost` est un **pipeline d'anonymisation de PII composable** pour les agents LLM. Chaque étape (détection, liaison, résolution, anonymisation) est un `Protocol` Python que vous pouvez remplacer, vous gardez la main sur vos détecteurs (NER, regex, LLM, votre propre API) pendant que `piighost` s'occupe du reste : liaison d'entités inter-messages, cohérence des placeholders, et un middleware LangChain qui anonymise avant le LLM et désanonymise pour les outils et l'utilisateur final.

```mermaid
sequenceDiagram
    autonumber
    actor U as Vous
    participant M as piighost
    participant L as LLM
    participant T as Outil

    U->>M: "Email Patrick à patrick@acme.com"
    M->>L: "Email <<PERSON:1>> à <<EMAIL:1>>"
    L->>M: tool_call(send_email, to=<<EMAIL:1>>)
    M->>T: send_email(to="patrick@acme.com")
    T-->>M: "Envoyé."
    M-->>U: "Envoyé."
```

> Le LLM ne voit que `<<PERSON:1>>` et `<<EMAIL:1>>`. Votre outil `send_email` reçoit bien la vraie adresse. L'utilisateur final reçoit une réponse désanonymisée. Aucune modification de votre code agent.

## Table des matières

- [Pourquoi piighost ?](#pourquoi-piighost-)
- [Démarrage rapide](#démarrage-rapide)
- [Apportez votre propre détecteur](#apportez-votre-propre-détecteur)
- [Cas d'usage](#cas-dusage)
- [Fonctionnement](#fonctionnement)
  - [Pipeline](#pipeline)
  - [Middleware](#intégration-du-middleware)
- [Installation](#installation)
- [Composants du pipeline](#composants-du-pipeline)
- [FAQ](#faq)
- [Limites](#limites)
- [Développement et contribution](#développement)
- [Écosystème](#écosystème)
- [Soutenez-nous](#soutenez-nous)

## Pourquoi piighost ?

|                                                  | **piighost**                                | LangChain `PIIMiddleware` (intégré)  | Microsoft Presidio | Regex maison        |
|--------------------------------------------------|---------------------------------------------|--------------------------------------|--------------------|---------------------|
| Détecteurs interchangeables (NER, regex, LLM…)   | ✅ via le protocole `AnyDetector`           | ⚠️ regex / Presidio uniquement        | ⚠️ lié à spaCy / recognizers | ❌                  |
| Composer plusieurs détecteurs                    | ✅ `CompositeDetector` + résolveur de spans | ❌ une stratégie par instance         | ⚠️ partiel         | ❌                  |
| Liaison d'entités inter-messages                 | ✅ `ThreadAnonymizationPipeline` + mémoire  | ❌                                    | ❌                 | ❌                  |
| Tolérance casse / fautes de frappe               | ✅ `ExactEntityLinker` + `FuzzyEntityResolver` | ❌                                 | ❌                 | ❌                  |
| Anonymisation réversible (deanonymize)           | ✅ avec cache                               | ❌ block / mask uniquement            | ⚠️ API séparée     | ❌                  |
| Middleware LangChain / LangGraph                 | ✅ `PIIAnonymizationMiddleware`             | ✅ `PIIMiddleware`                    | ❌                 | ❌                  |
| Désanonymise / réanonymise à l'appel d'outil     | ✅ `awrap_tool_call`                        | ❌                                    | ❌                 | ❌                  |
| API async-first                                  | ✅                                          | ⚠️                                    | ⚠️                 | ❌                  |
| Format de placeholder personnalisable            | ✅ `AnyPlaceholderFactory`                  | ⚠️ template seulement                 | ⚠️ template seulement | dépend           |

Le voisin le plus proche, c'est le [`PIIMiddleware`](https://docs.langchain.com/oss/python/langchain/middleware#pii-middleware) intégré à LangChain : il branche l'anonymisation dans la boucle d'agent, mais il fonctionne en sens unique (block / redact / mask / hash) et ne sait ni désanonymiser pour l'utilisateur final, ni passer les vraies valeurs aux outils. `piighost` reprend le même point d'accroche et y ajoute le voyage retour, la mémoire inter-messages et la pile de détection interchangeable, le LLM voit des placeholders pendant que le reste du système continue à travailler avec les vraies données.

## Démarrage rapide

Installez l'extra `cache` (utilisé par le pipeline) :

```bash
uv add 'piighost[cache]'
```

Anonymisez et désanonymisez sans télécharger de modèle. `ExactMatchDetector` matche un dictionnaire fixe via une regex aux frontières de mots, idéal pour essayer `piighost` en moins d'une minute.

```python
import asyncio

from piighost import Anonymizer, ExactMatchDetector
from piighost.pipeline import AnonymizationPipeline

detector = ExactMatchDetector([("Patrick", "PERSON"), ("Paris", "LOCATION")])
pipeline = AnonymizationPipeline(detector=detector, anonymizer=Anonymizer())


async def main() -> None:
    anonymized, entities = await pipeline.anonymize("Patrick lives in Paris.")
    print(anonymized)
    # <<PERSON:1>> lives in <<LOCATION:1>>.

    print([entity.detections[0].position for entity in entities])
    # [Span(start_pos=0, end_pos=7), Span(start_pos=17, end_pos=22)]

    original, _ = await pipeline.deanonymize(anonymized)
    print(original)
    # Patrick lives in Paris.


asyncio.run(main())
```

> **Comment `deanonymize` retrouve-t-il le texte original ?** Il ne relance pas le détecteur. Le pipeline garde un cache en mémoire (`aiocache.SimpleMemoryCache` par défaut) qui mappe `sha256(texte_anonymisé) → (texte_original, entités)`. Appeler `deanonymize` est juste un lookup. Pour les déploiements multi-instances, branchez un backend Redis ou Memcached, voir [docs/fr/deployment.md](docs/fr/deployment.md).

Pour la production, branchez un modèle NER ou votre propre détecteur ci-dessous.

<details>
<summary><strong>Configuration avancée</strong> (vrai NER, résolveurs personnalisés, pipeline complet)</summary>

```python
import asyncio
from gliner2 import GLiNER2

from piighost.anonymizer import Anonymizer
from piighost.detector.gliner2 import Gliner2Detector
from piighost.pipeline import AnonymizationPipeline

model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")
detector = Gliner2Detector(model=model, labels=["PERSON", "LOCATION"])
pipeline = AnonymizationPipeline(detector=detector, anonymizer=Anonymizer())


async def main() -> None:
    text = "Patrick lives in Paris. Patrick loves Paris."
    anonymized, entities = await pipeline.anonymize(text)
    print(anonymized)
    # <<PERSON:1>> lives in <<LOCATION:1>>. <<PERSON:1>> loves <<LOCATION:1>>.

    for entity in entities:
        print(f"  {entity.label}: {entity.detections[0].text}")
    # PERSON: Patrick
    # LOCATION: Paris

    original, _ = await pipeline.deanonymize(anonymized)
    print(original)
    # Patrick lives in Paris. Patrick loves Paris.


asyncio.run(main())
```

Remplacez `Gliner2Detector` par n'importe quelle implémentation de `AnyDetector` (spaCy, regex, API distante, votre propre détecteur, voir [Apportez votre propre détecteur](#apportez-votre-propre-détecteur)). Idem pour chaque autre étape du pipeline.

</details>

### Avec un middleware d'agent LangChain

Un middleware LangChain est un point d'extension qui s'exécute avant et après chaque appel au LLM et chaque appel d'outil. `piighost` s'y branche pour intercepter et transformer les messages, ce qui applique l'anonymisation des PII sans modifier le code de votre agent.

```python
from langchain.agents import create_agent
from langchain_core.tools import tool

from piighost.anonymizer import Anonymizer
from piighost.detector.gliner2 import Gliner2Detector
from piighost.pipeline import ThreadAnonymizationPipeline
from piighost.middleware import PIIAnonymizationMiddleware

from gliner2 import GLiNER2


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email to a given address."""
    return f"Email successfully sent to {to}."


model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1")
detector = Gliner2Detector(model=model, labels=["PERSON", "LOCATION"])
pipeline = ThreadAnonymizationPipeline(detector=detector, anonymizer=Anonymizer())
middleware = PIIAnonymizationMiddleware(pipeline=pipeline)

graph = create_agent(
    model="openai:gpt-5.4",
    system_prompt="You are a helpful assistant.",
    tools=[send_email],
    middleware=[middleware],
)
```

Le middleware intercepte chaque tour de l'agent. Le LLM ne voit que le texte anonymisé, les outils reçoivent les vraies valeurs, et les messages destinés à l'utilisateur sont désanonymisés automatiquement.

## Apportez votre propre détecteur

L'étape de détection est juste un `Protocol`. Tout objet async exposant une méthode `detect(text) -> list[Detection]` fonctionne. Le pipeline ne fait pas de différence entre un modèle, une regex, ou un appel HTTP.

```python
import httpx

from piighost.detector.base import AnyDetector  # protocole, sous-typage structurel
from piighost.models import Detection, Span


class RemoteNERDetector:
    """Calls a hosted NER service and maps its response to Detection objects."""

    def __init__(self, url: str, api_key: str) -> None:
        self._url, self._key = url, api_key

    async def detect(self, text: str) -> list[Detection]:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                self._url,
                json={"text": text},
                headers={"Authorization": f"Bearer {self._key}"},
            )
        return [
            Detection(
                text=hit["text"],
                label=hit["label"],
                position=Span(start_pos=hit["start"], end_pos=hit["end"]),
                confidence=hit["score"],
            )
            for hit in r.json()["entities"]
        ]


# Satisfait AnyDetector par sous-typage structurel, à brancher directement.
detector: AnyDetector = RemoteNERDetector(url="...", api_key="...")
```

Combinez plusieurs détecteurs avec `CompositeDetector` et laissez `ConfidenceSpanConflictResolver` choisir un gagnant si leurs spans se chevauchent. Voir [docs/fr/extending.md](docs/fr/extending.md) pour le catalogue complet (spaCy, transformers, LLM-as-detector, regex avec validators pour IBAN / NIR / Luhn).

## Cas d'usage

`piighost` trouve sa place partout où un LLM tiers ne devrait pas voir de noms réels, d'identifiants, ou de PII en texte libre :

- **Chatbot de support client.** Un SaaS envoie chaque ticket à GPT pour générer une réponse. Avec `piighost`, le LLM voit `<<CUSTOMER:1>> signale une coupure sur la commande <<ORDER_ID:3>>`, la réponse revient désanonymisée, et l'email du client n'apparaît jamais côté fournisseur.
- **Assistant médical / clinique.** Une infirmière colle des notes de patient dans un assistant de tri. `piighost` retire nom, numéro de sécurité sociale et adresse avant l'appel LLM, le contenu médical (symptômes, constantes, traitements) atteint le modèle intact, ce qui préserve la qualité du raisonnement tout en évitant un incident HIPAA / RGPD.
- **Agent RH sur documents internes.** Un agent RAG répond sur des évaluations annuelles et des grilles salariales. Les noms et montants sont anonymisés dans les chunks récupérés, le LLM ne voit jamais qui touche quoi, la réponse finale est reconstruite uniquement pour l'utilisateur RH autorisé.
- **Assistant juridique.** Contrats traités avec noms de clients et de contreparties masqués avant le modèle.
- **Agents outillés.** Anonymise les entrées en texte libre sans casser les appels d'outils. Le `send_email` / CRM / Jira reçoit la vraie adresse, le LLM n'aura vu que `<<PERSON:1>>`.

## Fonctionnement

### Pipeline

`AnonymizationPipeline` exécute cinq étapes, chacune étant un protocole interchangeable :

```mermaid
---
title: "AnonymizationPipeline.anonymize() flow"
---
flowchart LR
    classDef stage fill:#90CAF9,stroke:#1565C0,color:#000
    classDef protocol fill:#FFF9C4,stroke:#F9A825,color:#000
    classDef data fill:#A5D6A7,stroke:#2E7D32,color:#000

    INPUT(["`**Texte d'entrée**
    _'Patrick lives in Paris.
    Patrick loves Paris.'_`"]):::data

    DETECT["`**1. Detect**
    _AnyDetector_`"]:::stage
    RESOLVE_SPANS["`**2. Resolve Spans**
    _AnySpanConflictResolver_`"]:::stage
    LINK["`**3. Link Entities**
    _AnyEntityLinker_`"]:::stage
    RESOLVE_ENTITIES["`**4. Resolve Entities**
    _AnyEntityConflictResolver_`"]:::stage
    ANONYMIZE["`**5. Anonymize**
    _AnyAnonymizer_`"]:::stage

    OUTPUT(["`**Sortie**
    _'<<PERSON:1>> lives in <<LOCATION:1>>.
    <<PERSON:1>> loves <<LOCATION:1>>.'_`"]):::data

    INPUT --> DETECT
    DETECT -- "list[Detection]" --> RESOLVE_SPANS
    RESOLVE_SPANS -- "détections dédupliquées" --> LINK
    LINK -- "list[Entity]" --> RESOLVE_ENTITIES
    RESOLVE_ENTITIES -- "entités fusionnées" --> ANONYMIZE
    ANONYMIZE --> OUTPUT

    P_DETECT["`GlinerDetector
    _(ou RegexDetector, ExactMatchDetector, CompositeDetector…)_`"]:::protocol
    P_RESOLVE_SPANS["`ConfidenceSpanConflictResolver
    _(plus haute confiance gagne)_`"]:::protocol
    P_LINK["`ExactEntityLinker
    _(regex word-boundary)_`"]:::protocol
    P_RESOLVE_ENTITIES["`MergeEntityConflictResolver
    _(fusion union-find)_`"]:::protocol
    P_ANONYMIZE["`Anonymizer + LabelCounterPlaceholderFactory
    _(tags <<LABEL:N>>)_`"]:::protocol

    P_DETECT -. "implémente" .-> DETECT
    P_RESOLVE_SPANS -. "implémente" .-> RESOLVE_SPANS
    P_LINK -. "implémente" .-> LINK
    P_RESOLVE_ENTITIES -. "implémente" .-> RESOLVE_ENTITIES
    P_ANONYMIZE -. "implémente" .-> ANONYMIZE
```

> Trois termes structurent le pipeline. Un **span** est un offset `(début, fin)`, une **detection** est un span + un label + une confiance émis par un détecteur, une **entity** est un groupe de détections qui désignent la même PII (et reçoivent donc le même placeholder). Définitions complètes dans le [glossaire](docs/fr/glossary.md).

### Intégration du middleware

Le middleware se branche sur `abefore_model`, `awrap_tool_call` et `aafter_model` de LangChain pour anonymiser, désanonymiser pour les outils, puis réanonymiser les résultats d'outil. Voir [docs/fr/architecture.md](docs/fr/architecture.md) pour la séquence complète.

## Installation

`piighost` est livré comme un wheel standard sur PyPI. Le paquet principal n'a aucune dépendance obligatoire, n'installez que les extras nécessaires.

### Dans un projet uv (recommandé)

```bash
uv add piighost                 # noyau seul (léger, sans modèle)
uv add 'piighost[cache]'        # AnonymizationPipeline (aiocache)
uv add 'piighost[gliner2]'      # Gliner2Detector
uv add 'piighost[middleware]'   # PIIAnonymizationMiddleware (langchain + aiocache)
uv add 'piighost[all]'          # tout
```

### Standalone (pip ou `uv pip`)

Pour un venv isolé, un notebook, ou un script en dehors d'un projet uv :

```bash
pip install piighost                          # ou:  uv pip install piighost
pip install 'piighost[middleware]'
```

### Compatibilité

| Python  | LangChain (extra `middleware`) | aiocache (extra `cache`) | GLiNER2 (extra `gliner2`) |
|---------|-------------------------------|--------------------------|---------------------------|
| >=3.10  | >=1.2                         | >=0.12                   | >=1.2                     |

`piighost` est testé sur Python 3.10 à 3.14. Les versions sont déclarées dans [`pyproject.toml`](pyproject.toml).

### Depuis les sources (développement)

```bash
git clone https://github.com/Athroniaeth/piighost.git
cd piighost
uv sync
make lint        # ruff format + check, pyrefly type-check, bandit
uv run pytest
```

## Composants du pipeline

Seuls `detector` et `anonymizer` sont obligatoires, les trois étapes intermédiaires (résolveur de spans, linker d'entités, résolveur d'entités) ont des valeurs par défaut que vous pouvez remplacer. Tableau complet des défauts, rôles et risques dans [docs/fr/architecture.md](docs/fr/architecture.md).

## FAQ

**Q : Quelles langues sont supportées ?**
Cela dépend entièrement du détecteur que vous branchez. Le pipeline lui-même est agnostique. Avec `Gliner2Detector` et un modèle GLiNER2 multilingue, vous obtenez environ 100 langues d'office. Avec `SpacyDetector`, tout ce que spaCy supporte. Avec `RegexDetector`, la langue n'a pas d'importance.

**Q : Quelles entités sont détectées d'origine ?**
Aucune. `piighost` ne livre pas son propre modèle NER, c'est volontaire. Vous apportez le détecteur. Utilisez `ExactMatchDetector` pour des dictionnaires fixes, `RegexDetector` avec `piighost.detector.patterns` (FR_IBAN, FR_NIR, EU_VAT, etc.), `Gliner2Detector` pour du NER ouvert (`PERSON`, `LOCATION`, `ORGANIZATION`, `EMAIL`, n'importe quel label que vous lui demandez), ou composez-les.

**Q : Quelle latence ajoutée ?**
Le pipeline lui-même est à l'ordre de la milliseconde (regex et lookups). Le vrai coût vient du détecteur. GLiNER2 sur CPU pour un message de 200 tokens, c'est typiquement 50 à 200 ms. Un LLM-comme-détecteur, plusieurs centaines de ms. Le pipeline cache les détections par hash de texte via `aiocache`, le contenu répété est gratuit. Une mesure sur votre charge réelle reste recommandée avant de dimensionner la production.

**Q : Fonctionne 100 % offline ? (RGPD)**
Oui. Avec un détecteur local (`Gliner2Detector`, `SpacyDetector`, `RegexDetector`, `ExactMatchDetector`), aucune donnée ne quitte votre processus. Le middleware ne transmet au LLM que du texte déjà anonymisé. C'est la raison principale de l'adoption de `piighost`, garder un LLM hébergé sous contraintes UE sans exfiltrer de PII brutes.

**Q : Que se passe-t-il quand le NER rate une entité ?**
Deux lignes de défense.
1. Le **linker d'entités** balaye tout le texte (et toute la conversation, dans `ThreadAnonymizationPipeline`) à la recherche de correspondances de mots pour chaque entité détectée. Si `Patrick` est détecté une fois, chaque autre `Patrick` reçoit le même placeholder, même si le NER les avait ratés.
2. Pour les PII déterministes (emails, numéros, IBANs), combinez le détecteur NER avec un `RegexDetector` via `CompositeDetector`. Les faux négatifs NER deviennent des vrais positifs regex.

Pour les PII **générées par le LLM** dans sa réponse (entités jamais vues en entrée), utilisez un `DetectorGuardRail` sur la sortie, voir [docs/fr/extending.md](docs/fr/extending.md).

**Q : Utilisable sans LangChain ?**
Oui. `AnonymizationPipeline` et `ThreadAnonymizationPipeline` sont indépendants de tout framework d'agent. Le middleware LangChain est une intégration parmi d'autres, le pipeline s'appelle depuis n'importe où (handler FastAPI, script batch, boucle d'agent maison).

**Q : Comment fonctionne la réversibilité (deanonymize) ?**
Un cache à clé SHA-256 stocke `texte_anonymisé → (texte_original, entités)`. `pipeline.deanonymize(texte_anonymisé)` consulte la table et restitue l'original. Le cache est en mémoire par défaut (`SimpleMemoryCache`), passez n'importe quel backend `aiocache` (Redis, Memcached) pour les déploiements multi-instances.

## Limites

`piighost` n'est pas une solution miracle. Compromis à garder en tête avant de déployer :

- **La liaison d'entités amplifie les erreurs du NER.** Si `Rose` est détecté à tort comme une personne, chaque `rose` (la fleur) est anonymisé aussi. Atténuation : détecteur plus strict (`ExactMatchDetector`, `RegexDetector`) ou thread frais par message.
- **La résolution floue peut sur-fusionner.** Jaro-Winkler sur des noms courts (`Marin` vs `Martin`) peut fusionner deux personnes distinctes. Atténuation : relever le seuil ou rester sur `MergeEntityConflictResolver`.
- **Les PII générées par le LLM dans ses réponses** (jamais vues en entrée) échappent à la liaison d'entités. Ajoutez un `DetectorGuardRail` sur la sortie.
- **Le cache est local** par défaut. Les déploiements multi-instances nécessitent un backend partagé (Redis, Memcached) à configurer explicitement.
- **La latence dépend du détecteur.** Mesurez sur votre charge avant de dimensionner.

Voir [docs/fr/architecture.md](docs/fr/architecture.md), [docs/fr/extending.md](docs/fr/extending.md) et [docs/fr/limitations.md](docs/fr/limitations.md) pour les stratégies d'atténuation.

## Développement

```bash
uv sync                              # installer les dépendances de dev
make lint                            # ruff format + check, pyrefly, bandit
uv run pytest                        # lancer tous les tests
uv run pytest tests/ -k "test_name"  # un test précis
```

### Contribuer

- **Commits** : Conventional Commits via Commitizen (`feat:`, `fix:`, `refactor:`, etc.)
- **Vérification de types** : PyReFly (pas mypy)
- **Formatage / lint** : Ruff
- **Gestionnaire de paquets** : uv (pas pip)
- **Python** : 3.10+

Voir [CONTRIBUTING.md](CONTRIBUTING.md) et [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Écosystème

- **[piighost-api](https://github.com/Athroniaeth/piighost-api)** : Serveur API REST pour l'inférence d'anonymisation PII. Charge un pipeline piighost une seule fois côté serveur et expose les opérations `anonymize` / `deanonymize` via HTTP, les clients n'ont besoin que d'un client HTTP léger au lieu d'embarquer le modèle NER.
- **[piighost-chat](https://github.com/Athroniaeth/piighost-chat)** : Application de chat de démonstration pour des conversations IA respectueuses de la vie privée. Utilise `PIIAnonymizationMiddleware` avec LangChain pour anonymiser les messages avant le LLM et désanonymiser les réponses de manière transparente. Construit avec SvelteKit, Litestar et Docker Compose.

## Notes complémentaires

- Tous les modèles de données sont des dataclasses gelées, sûres à partager entre threads.
- Les tests utilisent `ExactMatchDetector` pour éviter de charger un modèle NER lourd en CI.
- Pour le modèle de menaces, ce que `piighost` protège et ce qu'il ne protège pas, ainsi que le stockage du cache, voir [SECURITY.md](SECURITY.md).

## Roadmap

Une roadmap publique (logo, benchmarks latence / précision sur un corpus de référence, GIF de `piighost-chat`, démo live hébergée) est dans [docs/fr/roadmap.md](docs/fr/roadmap.md). Issues et discussions bienvenues.

## Soutenez-nous

Si `piighost` vous fait gagner quelques heures, une ⭐ sur [GitHub](https://github.com/Athroniaeth/piighost) aide d'autres à le découvrir. Bug reports et PR encore mieux, voir [CONTRIBUTING.md](CONTRIBUTING.md).
