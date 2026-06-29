# 12_PROMPTS_CHAT

## Objectif

Fournir des prompts réutilisables pour l'assistant chat afin d'analyser, comprendre et documenter le projet Wavy.

## Prompts réutilisables

### 1. Analyse de bug

Objectif : identifier la cause d'un bug à partir des logs, du code et des comportements observés.

Prompt :

"Je travaille sur le projet Wavy. Voici le comportement attendu, le comportement observé et les fichiers concernés :
- [description du bug]
- fichiers : [liste ou extraits]

Analyse le problème en te basant uniquement sur ce qui est présenté, identifie la ou les causes possibles, et propose :
1. une explication claire du bug,
2. les zones du code à vérifier en priorité,
3. les tests ou commandes pour reproduire,
4. une première version de correctif si pertinente.

Ne fais pas de modifications automatiques si tu n'es pas sûr. Si l'information manque, indique clairement "À compléter"."

### 2. Création de nouvelle fonctionnalité

Objectif : définir le périmètre fonctionnel, l'architecture nécessaire et les étapes de réalisation.

Prompt :

"Je veux ajouter une fonctionnalité dans le projet Wavy. Voici le besoin métier et le périmètre :
- domaine : [socle/tiers/contrats/factures/pwa/gateway]
- besoin : [description]
- contraintes connues : [profil, auth, API, base de données]

Décris :
1. l'architecture cible,
2. les composants impactés,
3. les entités et endpoints à modifier/créer,
4. les tests à prévoir,
5. les risques et points d'attention.

Ne propose que des éléments basés sur le code et la structure existants. Marque "À compléter" pour les zones non connues."

### 3. Refactorer

Objectif : proposer un plan de refactorisation qui respecte l'architecture actuelle.

Prompt :

"Je veux refactorer du code dans le projet Wavy. Voici le module concerné et le contexte :
- module : [wavy-socle-api/wavy-tiers-api/wavy-contrats-api/wavy-factures-api/wavy-gateway/wavy-socle-front/etc.]
- objectif : [réduire la duplication, clarifier une API, isoler la logique métier, améliorer la lisibilité]
- contraintes : [ne pas changer le comportement, respecter l'architecture Spring/Angular]

Propose :
1. les zones de code à refactorer,
2. un plan par étapes,
3. les tests à exécuter après refactor,
4. les critères de validation.

Si l'information fait défaut, indique "À compléter".
"

### 4. Écrire des tests

Objectif : définir des tests unitaires, d'intégration et e2e en se basant sur l'architecture du projet.

Prompt :

"Je veux écrire des tests pour le projet Wavy. Voici le contexte :
- module : [backend/frontend/PWA]
- type de test : [unitaire/intégration/e2e]
- zone : [endpoint, service, component, workflow]
- état actuel : [pas de tests, tests partiels, tests existants]

Propose :
1. une liste de cas de test prioritaires,
2. les frameworks à utiliser,
3. une structure de fichiers de tests,
4. les commandes pour lancer les tests.

Précise les hypothèses nécessaires et écris "À compléter" si un élément n'est pas clair."

### 5. Mettre à jour la documentation

Objectif : aider à enrichir la documentation du projet sans inventer de contenu.

Prompt :

"Je dois mettre à jour la documentation Wavy. Voici les éléments dont je dispose :
- nouveaux fichiers / modules / options / environnements
- comportement actuel du code
- points de configuration

Propose :
1. les sections à ajouter ou à corriger,
2. le plan du document,
3. les liens aux fichiers sources pertinents,
4. un texte de base pour chaque section.

N'écris rien qui n'est pas appuyé par les sources ou qui n'est pas marqué "À compléter"."

### 6. Préparer un commit Git

Objectif : rédiger un message de commit clair et guider la préparation du diff.

Prompt :

"Je prépare un commit pour le projet Wavy. Voici les changements :
- module : [nom du module]
- type : [bugfix/feature/refactor/docs]
- résume : [description courte]
- fichiers modifiés : [liste]

Propose :
1. un message de commit formaté,
2. une checklist de validation avant git commit,
3. des commandes `git` utiles pour vérifier le diff.

Précise toutes les hypothèses et marque "À compléter" si des éléments manquent."
