# Smoke tests Wavy

## Rôle

Le healthcheck répond à « l'application est-elle techniquement démarrée ? » en
appelant `/actuator/health`. Le smoke test vérifie qu'une fonction applicative
de lecture répond et que son contenu possède une forme minimale cohérente.

Le script `scripts/smoke-test.sh` n'utilise que des requêtes GET. Il ne crée, ne
modifie et ne supprime aucune donnée.

## Contrôles

| Service | Requête | Validation |
|---|---|---|
| Socle | `/actuator/health` | statut `UP` |
| Tiers | `/api/tiers/referentiels/natures-personne` | tableau JSON contenant `SALARIE_INTERNE` |
| Contrats | `/api/contrats` | tableau JSON, vide accepté |
| Factures | `/actuator/health` | statut `UP` |
| Trésorerie | `/api/tresorerie/comptes-bancaires` | tableau JSON, vide accepté |
| Gateway | `/api/tiers/health` | module Tiers et statut `OK` |

Le dernier contrôle prouve que le Gateway route une requête vers le backend
Tiers ; il ne teste pas seulement la santé interne du Gateway.

## Exécution

```bash
./scripts/healthcheck.sh recette
./scripts/smoke-test.sh recette
```

Local et recette utilisent les ports déclarés dans `.env.local` et
`.env.recette`. Les identifiants de contexte valent `1` par défaut pour les jeux
de données de ces deux environnements et peuvent être remplacés :

```bash
WAVY_SMOKE_TENANT_ID=1 \
WAVY_SMOKE_USER_ID=1 \
WAVY_SMOKE_COMPANY_ID=1 \
./scripts/smoke-test.sh recette
```

La préproduction ne publie pas les ports des API. Le script y exécute donc les
requêtes depuis les conteneurs. Les identifiants de contexte sont obligatoires.
Contrats et Trésorerie exigent un compte réel : leur filtre délègue la
vérification au Socle en transmettant Authorization. Les appels PREPROD
utilisent curl depuis le conteneur Socle vers les services du réseau interne
(les options Basic de wget BusyBox ne sont pas portables) :

```bash
WAVY_SMOKE_TENANT_ID=... \
WAVY_SMOKE_USER_ID=... \
WAVY_SMOKE_COMPANY_ID=... \
WAVY_SMOKE_USER=... \
WAVY_SMOKE_PASSWORD=... \
./scripts/smoke-test.sh preprod
```

Ces valeurs doivent venir du gestionnaire de secrets ou de l'environnement du
processus. Elles ne doivent jamais être écrites dans Git. Le script ne les
affiche pas.

## Résultats

`OK` signifie que la requête a réussi et que son contenu respecte le contrat
minimal attendu. `KO` signale une erreur HTTP, un contenu inattendu ou une
configuration requise absente. Le script continue les autres contrôles et
retourne un code non nul si au moins un contrôle échoue.

## Limites

- Les listes vides sont acceptées afin de ne pas dépendre d'une donnée métier
  particulière.
- Les IDs de contexte doivent désigner un contexte valide.
- Le contrôle Gateway utilise le endpoint public `/api/tiers/health` : il teste
  le routage, mais pas une opération métier authentifiée.
- Le mode préproduction dépend des clients HTTP présents dans les images et
  nécessite des identifiants fournis au moment de l'exécution.
- Ces tests ne remplacent ni les tests automatisés applicatifs ni des tests
  fonctionnels métier complets.

En RECETTE, Contrats et Trésorerie utilisent `/actuator/health` ; en PREPROD,
les routes métier indiquées dans le tableau restent testées. Le bootstrap et
les migrations ne sont jamais déclenchés par ce script GET. Aucun smoke test
réel PREPROD n’a été exécuté pendant la préparation MSI.
