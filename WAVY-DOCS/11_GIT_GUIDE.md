# 11_GIT_GUIDE

## Objectif

Documenter les pratiques Git observées et fournir des recommandations pour les commits, les branches et les revues.

## Informations trouvées dans le code

- Le projet possède un dépôt Git racine `wavy-devops`.
- Il existe un `.gitignore` à la racine.
- Les fichiers `.env.local` et `.env.recette` ne sont pas versionnés.

## Conventions observées

- Pas de conventions Git explicites trouvées dans le code.
- Le dépôt utilise des fichiers de documentation et des scripts d'infrastructure.
- Les branches et la stratégie de commit ne sont pas documentées.

## Recommandations générales

- Créer une branche par fonctionnalité ou correctif : `feature/<nom>` ou `fix/<nom>`.
- Faire des commits atomiques et lisibles.
- Ajouter un message de commit expliquant le pourquoi, pas seulement le quoi.
- Valider les modifications avec `git status`, `git diff` et `git log --oneline`.
- Exécuter les tests pertinents avant de pousser.

## Points à compléter

- Convention de nommage de branches exacte.
- Politique de merge (merge commit, rebase, squash).
- Structure des PR et checklists de revue.
- Règles de gestion des versions et tags.
- Existence d'un workflow GitLab/GitHub spécifique.

## Commandes recommandées

```bash
git status
git add <fichiers>
git commit -m "[MODULE] Description courte"
git branch
git checkout -b feature/<nom>
git push origin feature/<nom>
git pull --rebase
git log --oneline --graph --decorate
```
