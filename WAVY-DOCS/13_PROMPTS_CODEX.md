# 13_PROMPTS_CODEX

## Objectif

Fournir des prompts réutilisables pour Codex afin de générer du code, proposer des correctifs et documenter le projet Wavy.

## Prompts réutilisables

### 1. Générer une nouvelle API ou endpoint

Objectif : créer ou compléter un endpoint REST dans un module backend.

Prompt :

"Dans le module Wavy `[nom du module]`, je veux ajouter un endpoint `[GET|POST|PUT|DELETE] /api/[...]`.
- Contexte : [qui utilise le endpoint, quels headers sont requis]
- Données d'entrée : [DTO attendu]
- Données de sortie : [DTO attendu]
- Validation métier : [règles]

Propose :
1. le controller Spring Boot complet,
2. le service et repository nécessaires,
3. le DTO/Entity si besoin,
4. les tests unitaires ou d'intégration associés.

Ne modifie pas le comportement des endpoints existants. Si tu dois inventer un contrat, marque "À compléter"."

### 2. Générer un composant Angular

Objectif : créer un composant, une page ou un service Angular dans un front Wavy.

Prompt :

"Je dois ajouter un composant Angular au projet `[wavy-socle-front/wavy-tiers-front/wavy-contrats-front/wavy-factures-front/wavy-pwa]`.
- Objectif : [page, formulaire, liste, service API]
- Route : [chemin de navigation]
- API cible : [endpoint gateway]
- données affichées : [structure attendue]

Propose :
1. le composant TypeScript,
2. le template HTML,
3. le style CSS/SCSS minimal,
4. le service Angular d'accès API.

Conserve la structure existante et n'ajoute pas de dépendances non présentes."

### 3. Corriger une configuration Docker

Objectif : identifier et corriger une configuration Docker Compose ou `.env`.

Prompt :

"Je veux corriger une configuration Docker pour Wavy. Voici les fichiers :
- `docker-compose.local.yml`
- `docker-compose.recette.yml`
- `.env.local` ou `.env.recette`

Explique :
1. les variables à mettre à jour,
2. les ports hôtes et internes corrects,
3. les relations `depends_on` et réseaux à vérifier,
4. les changements à apporter sans toucher au code applicatif.

Indique clairement "À compléter" si une variable manque."

### 4. Générer les tests pour un module

Objectif : écrire une suite de tests backend ou frontend.

Prompt :

"Je veux créer des tests pour le projet Wavy. Voici le module, le type de test et l'objectif :
- module : [backend/frontend]
- type : [unitaire/intégration/e2e]
- objectif : [couverture de l'endpoint / workflow / composant]

Propose :
1. une structure de fichiers de test,
2. des exemples de cas de test,
3. les assertions clés,
4. les commandes pour exécuter les tests.

Si certains détails manquent, marque "À compléter"."

### 5. Documenter une nouvelle fonctionnalité

Objectif : ajouter un paragraphe de documentation cohérent.

Prompt :

"Je veux documenter une nouvelle fonctionnalité dans Wavy. Voici le contexte et le composant :
- module : [backend/frontend]
- fonctionnalité : [description]
- points clés : [API, UI, données, sécurité]

Propose :
1. un titre de section,
2. un résumé en 3 phrases,
3. une liste de prérequis,
4. un plan de documentation.

Ne publie pas d'information non confirmée ; marque "À compléter" si nécessaire."

### 6. Préparer un commit technique

Objectif : rédiger un message de commit précis pour du code généré par Codex.

Prompt :

"Je prépare un commit technique dans Wavy. Voici les modifications :
- fichiers modifiés : [liste]
- module : [nom]
- type : [feature/fix/refactor/docs]
- objectifs : [résumé court]

Propose :
1. un message de commit structuré,
2. une liste de vérification avant commit,
3. des commandes pour inspecter le diff.

Si tu ne connais pas l'impact exact, marque "À compléter"."
