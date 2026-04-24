---
icon: lucide/shield-alert
---

# Pourquoi anonymiser ?

Cette page a pour but d'expliquer, pour un public large (technique ou non), pourquoi il est préférable d'anonymiser les données personnelles avant de les envoyer à un LLM, **indépendamment de `piighost`**. L'objectif n'est pas de vous vendre cette librairie, mais de poser un constat que vous pourrez opposer à un décideur ou à un interlocuteur sceptique.

!!! abstract "Résumé"
    Quand vous envoyez du texte à un LLM hébergé par un provider tiers, vous ne contrôlez plus qui le lit, combien de temps il est conservé, ni sous quelle juridiction il retombe. Cela peut être utilisé contre les utilisateurs en récupérant ces données et les agrégeant à d'autres pour de la surveillance de masse, du fichage politique, ciblage publicitaire. L'anonymisation **avant envoi** est une protection qui ne dépend ni du provider, d'une promesse, de la sécurité de leur infrastructure et ni d'une décision politique future.

La réflexion se construit en trois temps. D'abord, **comment un LLM cloud fonctionne techniquement** et **pourquoi la promesse contractuelle d'un provider ne suffit pas**. Ensuite, **le cadre juridique** qui s'applique à ces services, et ses zones grises. Enfin, **ce que l'anonymisation change concrètement**, ses usages obligatoires et ses limites.

---

## Fonctionnement d'un LLM cloud

Un LLM comme ChatGPT, Claude ou Mistral Le Chat n'est pas un logiciel qui tourne sur votre ordinateur. C'est un service distant. Votre question quitte votre machine, traverse Internet, arrive sur les serveurs du provider, y est traitée, puis une réponse revient.

!!! warning "L'interface peut être locale, le modèle ne l'est pas"
    Même si vous utilisez une application de bureau, une extension navigateur ou un plugin IDE, le modèle n'est pas exécuté sur votre machine. Seule l'interface l'est. Le calcul a lieu dans le cloud du provider. Le terme "LLM local" désigne uniquement l'inférence sur votre propre matériel via des outils comme `Ollama` ou `llama.cpp`.

Le trajet de votre message a plusieurs conséquences souvent sous-estimées :

- Le message est **reçu en clair** par l'infrastructure du provider. Le chiffrement TLS protège le transit, il ne protège pas la lecture côté serveur.
- Il est généralement **journalisé** pour la facturation, la détection d'abus, le débogage et l'amélioration du modèle.
- Il peut être **conservé pendant des semaines, des mois ou des années**, selon la politique du provider et les obligations légales qui s'imposent à lui.

Parler à un LLM cloud n'est, du point de vue de la confidentialité, pas plus privé qu'envoyer un e-mail via Gmail. Le provider a un accès technique complet au contenu. Tout ce qui empêche cet accès est **contractuel**, pas technique.

---

## Les limites d'une promesse contractuelle

Partons du principe le plus favorable : les grands providers (OpenAI, Anthropic, Google, Mistral et les autres) veulent sincèrement protéger les données de leurs utilisateurs. Leurs politiques de confidentialité contractualisent des engagements ("nous n'entraînons pas sur vos données API", "nous supprimons après 30 jours", "nous refusons les demandes abusives"), et ces engagements sont généralement tenus.

Cela ne suffit pas, parce qu'un engagement contractuel peut tomber pour trois raisons différentes, dont aucune ne relève de la mauvaise foi du provider.

### Un incident technique, un bug ou une attaque

Aucune politique ne protège contre une erreur d'ingénierie ou une intrusion réussie. Deux cas suffisent à l'illustrer.

Le **20 mars 2023**, un bug dans la bibliothèque Redis utilisée par OpenAI a exposé pendant environ neuf heures les titres de conversations ChatGPT à d'autres utilisateurs. Pour environ 1,2 % des abonnés ChatGPT Plus actifs dans la fenêtre concernée, des informations de paiement partielles (nom, e-mail, quatre derniers chiffres de la carte bancaire, date d'expiration) ont également été visibles à des comptes tiers. OpenAI a publié un post-mortem public reconnaissant l'incident.

En **janvier 2025**, les chercheurs de `Wiz Research` ont découvert qu'une base ClickHouse de DeepSeek était accessible sur Internet, sans authentification. Plus d'un million de lignes de logs y étaient exposées, incluant des historiques de conversations, des clés d'API et des métadonnées internes de l'infrastructure.

Dans les deux cas, les données ont fuité sans procès, sans injonction et sans intention malveillante de l'entreprise. Un bug, une configuration manquante, et le périmètre contractuel perd son sens.

### L'exploitation de vos données pour l'entraînement

"Si c'est gratuit, c'est vous le produit." Le principe, vieux comme le Web commercial, s'applique aussi aux LLM.

L'inférence d'un grand modèle coûte cher : chaque réponse mobilise des GPU en temps réel et le provider paie cette facture à chaque requête. Pourtant, OpenAI, Google et d'autres proposent des offres gratuites très généreuses. Les raisons commerciales classiques (acquisition d'utilisateurs, effet de standard de facto) n'expliquent qu'une partie du modèle économique. Ces offres alimentent aussi la **collecte de données d'entraînement**.

Sur les offres grand public gratuites, vos conversations peuvent être exploitées pour améliorer le modèle de plusieurs façons : le feedback explicite (👍/👎, reformulation, régénération d'une réponse) sert de signal d'apprentissage par renforcement, les échanges peuvent être relus par des annotateurs humains pour identifier les cas d'échec, et l'ensemble des conversations peut servir de matière première pour construire les jeux de données des itérations suivantes.

Les offres payantes (API, ChatGPT Enterprise, Claude Team, etc.) excluent généralement vos données de l'entraînement par défaut. Sur les offres gratuites en revanche, l'opt-out est souvent enfoui dans les paramètres, parfois désactivé par défaut, et la politique peut évoluer avec le temps.

### Une injonction judiciaire

Même quand le provider *veut* supprimer vos données, un tribunal peut l'en empêcher.

Le **13 mai 2025**, dans le cadre de son procès contre OpenAI, le `New York Times` a obtenu de la *Magistrate Judge* Ona T. Wang une **ordonnance de préservation** : OpenAI devait conserver toutes les conversations ChatGPT et les appels API de ses clients, y compris celles que l'entreprise aurait normalement supprimées selon sa propre politique. OpenAI s'y est opposée publiquement en déposant une motion de reconsidération, refusée dans un premier temps, puis en appelant devant le *District Judge* Sidney Stein, qui a rejeté l'appel en juin 2025. L'ordonnance a finalement été levée le **26 septembre 2025** (terminaison formelle le 9 octobre), les utilisateurs de l'EEE, de Suisse et du Royaume-Uni ayant par ailleurs été exemptés de la mesure.

L'affaire ne s'arrête pas là. Le **7 novembre 2025**, la même *Magistrate Judge* a ordonné à OpenAI de livrer au `New York Times` **20 millions de logs ChatGPT désidentifiés** à des fins de preuve. OpenAI a demandé une reconsidération, refusée, puis a fait appel. Le **5 janvier 2026**, le *District Judge* Stein a affirmé la décision, scellant l'obligation de livraison.

Cet épisode a deux conséquences pratiques. D'abord, la politique de confidentialité d'un provider n'est **jamais définitive** : une décision de justice à laquelle vous n'êtes pas partie peut la réécrire, imposer la conservation ou forcer la livraison massive de conversations à un tiers. Ensuite, le temps d'exposition de vos données à une future fuite ou attaque augmente mécaniquement, et la probabilité qu'une autorité publique (américaine ou, via une commission rogatoire internationale, étrangère) y accède grandit avec lui.

---

## Juridique : le droit ne suffit pas non plus

La réponse instinctive à ce constat technique est de se tourner vers le droit : choisir un provider "conforme RGPD", vérifier les certifications, exiger des clauses contractuelles. Cette approche est utile mais incomplète, pour deux raisons : le droit américain donne des voies d'accès légales aux données, et le droit européen n'a pas encore produit de garde-fou appliqué sur les LLM.

### Le cadre américain : CLOUD Act, FISA 702, Executive Order 12333

Trois textes structurent l'accès américain aux données des providers, aucun n'étant le Patriot Act.

!!! info "Pourquoi pas le Patriot Act ?"
    Le Patriot Act (2001) revient souvent dans ce débat, mais il n'est plus le bon texte à citer. Sa disposition la plus connue pour la surveillance, la `Section 215` (collecte massive de métadonnées téléphoniques révélée par Snowden), a été restreinte par le `USA FREEDOM Act` en 2015, puis laissée **expirer par le Congrès en mars 2020**. Elle n'est plus en vigueur. Par ailleurs, le Patriot Act visait les enquêtes antiterroristes, pas la question qui nous intéresse ici ("un provider américain peut-il être contraint de livrer des données stockées en Europe ?"). Les arrêts de la CJUE qui structurent le débat actuel ne citent pas le Patriot Act : ils citent FISA 702 et l'Executive Order 12333.

- **Le CLOUD Act (2018)** oblige tout fournisseur sous juridiction américaine à livrer les données qu'il contrôle, **peu importe où ces données sont physiquement stockées**. Un datacenter en Irlande ou en France ne met pas les données hors de portée dès que l'entreprise est américaine.
- **FISA Section 702** est la base légale des programmes de surveillance de masse comme `PRISM`, révélés en 2013 par Edward Snowden. Il permet la collecte de communications via les grands fournisseurs américains de services de communication électronique.
- **Executive Order 12333** est le cadre plus large de la surveillance par l'exécutif américain, sans supervision judiciaire directe.

Ces trois textes se cumulent et offrent des voies d'accès légales, discrètes (sans notification préalable aux personnes concernées), et applicables aux données des citoyens non américains.

### Schrems II : la CJUE tranche

En **juillet 2020**, la Cour de justice de l'Union européenne a invalidé le `Privacy Shield`, l'accord qui encadrait les transferts de données entre l'UE et les États-Unis. Sa motivation, résumée simplement : FISA 702 et l'Executive Order 12333 sont trop permissifs pour respecter le RGPD et n'offrent aucun recours judiciaire effectif aux citoyens européens.

Plus de 5 300 entreprises s'appuyaient sur le `Privacy Shield` pour leurs transferts transatlantiques. Un second accord, le `Data Privacy Framework` (2023), a remplacé le précédent, mais il repose sur les mêmes fondations juridiques américaines et sa durabilité est contestée. Plusieurs plaintes (notamment celles portées par l'association noyb de Max Schrems) visent explicitement une troisième invalidation.

### Microsoft Ireland : la juridiction prime la géographie

Entre 2013 et 2018, les autorités américaines ont exigé de Microsoft, via un mandat émis sous le `Stored Communications Act`, qu'elle livre des données d'un client stockées sur ses serveurs en Irlande. Microsoft a résisté jusqu'à la Cour Suprême. La procédure n'a jamais été tranchée sur le fond, parce que le Congrès a voté le `CLOUD Act` en mars 2018 pour clarifier la réponse : oui, les entreprises américaines doivent livrer les données, où qu'elles soient stockées. L'affaire a été déclarée sans objet.

Conséquence directe : **l'hébergement européen par un provider américain n'offre pas d'étanchéité juridique face aux États-Unis**. Le marketing "vos données restent en Europe" masque cette asymétrie.

!!! note "Une nuance honnête sur le champ d'application"
    Le CLOUD Act ne s'applique pas à n'importe quelle entreprise ayant un simple lien avec les États-Unis. Il faut que l'entité soit **sous juridiction américaine** (incorporée aux US ou contrôlée par une entité américaine) **et** qu'elle ait la "possession, la garde ou le contrôle" des données. Un fournisseur européen avec une simple filiale commerciale américaine n'est pas automatiquement captif : une analyse au cas par cas est nécessaire.

### Le cadre européen : un RGPD qui n'a pas encore tenu sur les LLM

Le RGPD reste un outil solide sur le papier, mais sa mise en œuvre sur les LLM est balbutiante. L'affaire la plus emblématique le montre.

La `Garante`, autorité italienne de protection des données (équivalent de la `CNIL`), ouvre une enquête contre OpenAI dès **mars 2023**. En **décembre 2024**, elle inflige une amende de **15 millions d'euros** à OpenAI pour traitement sans base légale, manquements à la transparence et absence de mécanisme de vérification d'âge. Mais en **mars 2026**, le tribunal de Rome annule cette décision dans son intégralité ; les motifs détaillés n'ont pas encore été rendus publics au moment de la rédaction de cette page. À ce jour, aucune autorité européenne n'a fait confirmer en dernier ressort une sanction contre un grand LLM pour violation du RGPD sur la phase de collecte d'entraînement.

Le RGPD reste puissant, mais compter uniquement sur lui pour protéger des données sensibles envoyées à un LLM, c'est parier sur un rempart qui n'a pas encore démontré sa capacité à tenir en appel.

---

## Usages secondaires : ce que les données collectées permettent

Les sections précédentes expliquent comment les données sortent de votre périmètre. Reste à préciser ce qu'elles rendent possible une fois collectées. Trois usages, inégalement documentés, méritent d'être distingués pour ne pas amalgamer un risque structurel et une pratique avérée.

### Surveillance de masse

Une conversation LLM ressemble techniquement à un e-mail ou un chat : du texte daté, rattaché à un compte identifiable. Elle tombe dans le même périmètre de collecte que les autres communications électroniques couvertes par `FISA 702`, renouvelé pour deux ans en avril 2024 par le `RISAA`, et dont le renouvellement est à nouveau en débat au Congrès en avril 2026. Les rapports déclassifiés du `PCLOB` documentent plusieurs centaines de milliers de **sélecteurs** (identifiants de cibles) actifs chaque année, et la collecte "à propos" des cibles (suspendue en 2017, réautorisée ensuite) élargit mécaniquement le périmètre à des communications qui ne sont ni envoyées à la cible ni par la cible, mais qui la mentionnent.

Que cette capacité soit aujourd'hui appliquée aux conversations LLM ou non, le cadre juridique et l'architecture technique sont en place.

### Fichage et ciblage politique

L'inquiétude n'est pas spéculative, elle s'appuie sur des cas documentés de surveillance ciblée dans d'autres couches de l'Internet.

- **Angela Merkel, octobre 2013** : les révélations Snowden documentent la surveillance par la NSA du téléphone portable de la chancelière allemande, inscrit comme cible depuis 2002. Les sources allemandes (Süddeutsche Zeitung, NDR) indiquent que Gerhard Schröder, prédécesseur de Merkel, avait lui aussi été surveillé à partir de 2002, en raison de son opposition à l'intervention en Irak. Obama a confirmé implicitement en promettant par téléphone que la surveillance était terminée ; le gouvernement allemand a publiquement protesté.
- **Associated Press, 2012-2013** : le `Department of Justice` saisit secrètement en avril-mai 2012 les relevés de plus de vingt lignes téléphoniques AP, dans le cadre d'une enquête sur une fuite. L'agence ne l'apprend qu'en mai 2013, par notification *après coup*.
- **Pegasus / NSO, 2021** : la coalition `Forbidden Stories` documente l'usage du spyware Pegasus contre environ 180 journalistes ciblés, ainsi que des activistes, avocats, diplomates et chefs d'État dans plus de 20 pays, dont la France, par l'intermédiaire de plusieurs États clients de NSO.

Aucun de ces cas ne concerne spécifiquement un LLM. Mais ils établissent trois faits : les États surveillent régulièrement les communications de journalistes, d'avocats et de personnalités politiques ; les outils juridiques et techniques pour le faire existent déjà ; un LLM qui voit passer les conversations d'un cabinet d'avocats, d'une rédaction d'investigation ou d'un mouvement militant devient, par construction, un point de concentration d'informations à haute valeur.

### Ciblage commercial et data brokers

Le risque est différent des deux précédents : il ne nécessite ni juge, ni mandat. Il repose sur l'écosystème commercial qui entoure les providers.

Plusieurs grands acteurs du LLM ont des intérêts adjacents à la publicité ciblée : Google en fait son cœur de métier, Microsoft (actionnaire majeur d'OpenAI) opère `Bing Ads`, Meta pousse son propre écosystème d'IA générative dans un groupe dont la quasi-totalité des revenus provient du ciblage publicitaire. Rien ne prouve aujourd'hui qu'un provider ait revendu des conversations LLM à des data brokers. Mais la structure de revenus crée une **incitation** que les politiques de confidentialité, seules, ne neutralisent pas.

Par ailleurs, un rapport de l'`Office of the Director of National Intelligence` daté de **janvier 2022 et déclassifié en juin 2023** reconnaît que les agences de renseignement américaines **achètent régulièrement des données commerciales auprès de data brokers**, notamment des données de localisation et de navigation. La frontière entre écosystème publicitaire et surveillance étatique est, en pratique, poreuse : ce qui est collecté pour vendre de la publicité peut être racheté pour surveiller.

### Pourquoi l'anonymisation casse ce graphe

Une PII envoyée en clair devient un nœud dans un graphe potentiel : elle peut être croisée avec des réseaux sociaux, des brèches antérieures, des registres publics ou des bases commerciales, pour ré-identifier, enrichir ou cibler. Un placeholder `<<PERSON_1>>` n'a, lui, aucune valeur d'agrégation. L'anonymisation avant envoi coupe la racine commune à toutes les chaînes d'usage secondaire décrites plus haut.

---

## Où se placer dans le spectre des providers ?

Le choix n'est pas binaire entre "cloud américain" et "rien". Il existe un continuum, du plus exposé au plus isolé, et chaque palier modifie à la fois le risque juridique et la responsabilité qui vous incombe.

| Option                        | CLOUD Act / FISA 702            | RGPD                                       | Accès technique du provider     | Exemples                                        |
|-------------------------------|---------------------------------|--------------------------------------------|---------------------------------|-------------------------------------------------|
| Provider US, serveurs US      | Oui, directement                | Indirect (via DPF, fragile)                | Oui                             | OpenAI, Anthropic, Google                       |
| Provider US, serveurs UE      | Oui (cf. Microsoft Ireland)     | S'applique, mais primé par l'injonction US | Oui                             | Azure OpenAI EU, AWS Bedrock EU                 |
| Provider UE                   | Non (sauf filiale US contrôlée) | S'applique pleinement                      | Oui                             | Mistral, OVHcloud AI, Scaleway                  |
| Modèle en local (self-hosted) | Non                             | Vous êtes responsable du traitement        | **Non : vous êtes le provider** | `llama.cpp`, `Ollama`, `vLLM` sur infra privée  |

Au départ du spectre, le **provider américain hébergé aux États-Unis** cumule les trois risques vus plus haut : CLOUD Act, FISA 702 et Executive Order 12333 s'appliquent sans filtre, les transferts de données depuis l'UE reposent sur le `Data Privacy Framework` contesté, et une injonction d'un juge américain peut forcer la conservation indéfinie des conversations. C'est le scénario le plus exposé.

Déplacer physiquement les serveurs en Europe ne change presque rien sur le plan juridique. Dès que l'entité opératrice est sous juridiction américaine, le CLOUD Act s'applique peu importe où se trouvent les disques durs. Cette option apporte des bénéfices réels sur d'autres axes (latence plus faible, garanties opérationnelles, parfois certifications `SecNumCloud` partielles via joint-venture), mais pas d'étanchéité face aux États-Unis.

Changer de juridiction en passant à un **provider européen** (Mistral, OVHcloud AI, Scaleway, Aleph Alpha, etc.) fait tomber le risque CLOUD Act par défaut, sauf si le provider a une filiale américaine sous contrôle. Le RGPD s'applique pleinement et les autorités européennes peuvent sanctionner. Cela ne rend pas le provider aveugle au contenu pour autant : il conserve un accès technique complet, la protection reste contractuelle et étatique, et une commission rogatoire française ou allemande reste possible. Un provider européen peut aussi, pour des raisons pratiques, héberger son infrastructure sur AWS ou Azure, ce qui réintroduit un lien avec une juridiction tierce. Vérifier au cas par cas.

!!! note "Le cas du `on-premise`"
    Certains providers européens, comme Mistral, proposent du `on-premise` : leurs clients font héberger le modèle dans leur propre datacenter. C'est une option intéressante pour bénéficier de l'expertise d'un acteur européen tout en gardant la maîtrise de l'infrastructure, mais elle reste peu répandue et coûteuse.

Enfin, **exécuter le modèle localement** sur votre propre infrastructure (`Ollama`, `vLLM`, `llama.cpp` ou équivalent) supprime entièrement le tiers : aucun provider n'a d'accès technique au contenu, par construction. C'est la protection maximale sur le plan de la confidentialité. La contrepartie est que toute la responsabilité bascule chez vous : sécurité physique et logique, chiffrement au repos, gestion des accès, mises à jour, journalisation. Les modèles ouverts exécutables localement (Llama, Mistral, Qwen, DeepSeek, etc.) peuvent rester en retrait des meilleurs modèles propriétaires sur certaines tâches complexes, bien que l'écart se réduise rapidement.

Le choix du provider continue de compter pour beaucoup de choses : latence, coût, qualité du modèle, conformité RGPD d'ensemble, écosystème d'intégration. Mais **pour le risque spécifique de fuite de PII, l'anonymisation neutralise ce choix**. Si seuls des placeholders comme `<<PERSON_1>>` quittent votre infrastructure, un provider américain ne reçoit rien d'exploitable sur vos données sensibles. Il se retrouve, de ce seul point de vue, équivalent à un modèle exécuté en local.

---

## Les obligations sectorielles et les choix déjà faits

### Quand c'est une obligation légale

Dans plusieurs professions, l'envoi de données personnelles à un LLM non souverain n'est pas un choix d'opportunité, c'est une impossibilité réglementaire.

- **Finance** : MiFID II, secret bancaire, obligations de confidentialité client.
- **Avocats** : secret professionnel absolu (article 66-5 de la loi du 31 décembre 1971). Une consultation client envoyée brute et nominative à un LLM américain peut constituer une faute déontologique ; les guides récents du `CNB` exigent au minimum anonymisation, consentement client et choix d'un provider adéquat.
- **Médecine** : secret médical (article L.1110-4 du Code de la santé publique en France), HIPAA aux États-Unis. Un dossier patient ne peut pas transiter par un service tiers sans garanties techniques lourdes (hébergeur certifié `HDS`, `DPO`, etc.).
- **Défense et secteurs stratégiques** : régimes spécifiques (classification, `CUI` (*Controlled Unclassified Information*) aux US, `Diffusion Restreinte` en France). Le croisement potentiel entre l'accès légal du gouvernement américain et des intérêts stratégiques (énergie, défense, technologie) rend ce risque non-théorique.

Dans ces secteurs, l'anonymisation avant envoi n'est pas une bonne pratique, c'est un prérequis de conformité.

### Ce que les grandes entreprises ont déjà décidé

À défaut de protection technique disponible en 2023, plusieurs grands groupes ont tranché en interdisant purement l'usage des LLM cloud à leurs employés.

- **Samsung, avril 2023** : plusieurs incidents internes où des ingénieurs collent du code source et des notes de réunion dans ChatGPT. Samsung rappelle publiquement que les données ainsi partagées sont impossibles à récupérer, puisqu'elles sont désormais sur les serveurs d'OpenAI. En mai 2023, l'entreprise interdit l'usage des LLM génératifs sur les appareils professionnels.
- **Secteur bancaire américain, printemps 2023** : JPMorgan Chase, Bank of America, Citigroup, Goldman Sachs, Deutsche Bank et Wells Fargo bloquent ou restreignent l'usage de ChatGPT par leurs employés. Verizon, Amazon et Walmart émettent des avertissements internes.

Ces décisions proviennent de directions juridiques et de RSSI qui ont fait le calcul : **le risque structurel dépasse le gain de productivité**, tant qu'aucune barrière technique ne garantit que les PII ne quittent pas l'entreprise. L'anonymisation ouvre précisément cette troisième voie, entre l'interdiction pure et l'envoi en clair.

---

## Protection juridique vs protection technique

Toutes les protections mobilisées jusqu'ici reposent sur des instruments **juridiques** : politiques de confidentialité, clauses contractuelles types, accords internationaux, amendes administratives. Elles partagent un défaut commun : elles sont **révocables**, par une décision politique ou judiciaire sur laquelle vous n'avez aucune prise.

| Type de protection           | Exemple                                    | Pourquoi c'est fragile                                   |
|------------------------------|--------------------------------------------|----------------------------------------------------------|
| Promesse contractuelle       | "Nous ne lisons pas vos données"           | Écrasable par une injonction (cas NYT vs OpenAI)         |
| Clauses contractuelles types | Transferts UE vers US                      | Déjà fragilisées par `Schrems II`                        |
| Accord international         | `Privacy Shield`, `Data Privacy Framework` | Le premier a été invalidé, le second est contesté        |
| Régulation régionale         | RGPD                                       | Lent à produire des sanctions appliquées sur les LLM     |
| Hébergement régional         | "Datacenters en Europe"                    | Neutralisé par le CLOUD Act si le provider est américain |

La protection technique fonctionne différemment. Si la donnée personnelle ne quitte jamais votre infrastructure, et que seul un placeholder (par exemple `<<PERSON_1>>`) est envoyé au LLM :

- aucune injonction ne peut obliger un tiers à divulguer ce qu'il n'a pas,
- aucun changement d'accord international ne vous affecte,
- aucune politique de conservation du provider n'est en cause,
- le provider peut être piraté, racheté, ou disparaître : vos données n'y étaient pas.

C'est la différence entre **"on vous promet de ne pas regarder"** et **"on est techniquement incapable de regarder"**. La seconde est toujours plus robuste que la première.

---

## Ce que l'anonymisation ne résout pas

L'anonymisation est une couche dans une défense en profondeur, pas une solution miracle.

- Elle ne rend pas un LLM conforme à tous les régimes réglementaires. Certaines données (santé nominativement reliable, secret-défense) ne doivent pas sortir de l'infrastructure, même sous forme anonymisée.
- Elle ne protège pas contre un LLM qui **hallucinerait** une PII dans sa réponse. Il faut alors une seconde passe de détection sur la sortie.
- Elle dépend de la qualité des détecteurs. Une PII non détectée passe en clair. C'est un enjeu d'ingénierie, pas un défaut conceptuel.
- Elle ne remplace pas les autres bonnes pratiques : chiffrement au repos, journalisation auditée, gestion des accès, formation des équipes.

---

## Pour aller plus loin

Sources citées et lectures utiles :

- **CJUE, arrêt `Schrems II`** (C-311/18, 16 juillet 2020) : [curia.europa.eu](https://curia.europa.eu/)
- **CLOUD Act** (H.R. 4943, 2018) : texte officiel sur [congress.gov](https://www.congress.gov/)
- **Rapports PCLOB sur FISA 702** (Privacy and Civil Liberties Oversight Board) : [pclob.gov](https://www.pclob.gov/)
- **Garante italienne, décision contre OpenAI** (décembre 2024, annulée par le tribunal de Rome en mars 2026) : [garanteprivacy.it](https://www.garanteprivacy.it/)
- **NYT vs OpenAI, ordonnance de préservation et livraison de logs** (US District Court SDNY, mai à novembre 2025)
- **OpenAI, post-mortem de l'incident Redis** (20 mars 2023) : [openai.com/blog](https://openai.com/)
- **Wiz Research, exposition DeepSeek** (janvier 2025) : [wiz.io](https://www.wiz.io/)
- **Samsung, politique interne sur les LLM** (mai 2023, couverture `Bloomberg`)
- **Surveillance du téléphone d'Angela Merkel par la NSA** (révélations Snowden, octobre 2013, couverture `Der Spiegel`, `Süddeutsche Zeitung`, `NDR`)
- **Saisie des relevés AP par le DOJ** (mai 2013, communiqué public d'Associated Press)
- **Pegasus Project / Forbidden Stories** (juillet 2021) : [forbiddenstories.org](https://forbiddenstories.org/)
- **ODNI, `Report on Commercially Available Information`** (janvier 2022, déclassifié juin 2023) : [dni.gov](https://www.dni.gov/)
- **SecNumCloud** (ANSSI) : [cyber.gouv.fr](https://cyber.gouv.fr/)

Pour un regard critique et équilibré, voir aussi les publications de la `CNIL` sur l'IA générative, du `CEPD` (`EDPB`) sur les transferts internationaux, et de l'`ENISA` sur la souveraineté numérique.
