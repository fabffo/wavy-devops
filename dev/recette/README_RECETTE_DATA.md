# Données de recette Wavy

Ce dossier contient les jeux de données destinés à la pile Docker recette globale.

Fichiers :
- `01_socle_recette.sql` : données de base du référentiel socle (tenants, sociétés internes, rôles, utilisateurs, liens utilisateur/société).
- `02_tiers_recette.sql` : données de tiers pour `tenant_id = 3`, `societe_interne_id = 4` et `societe_interne_id = 5`.
- `03_contrats_recette.sql` : contrats de recette pour les tiers `4` et `5`, et références facturables.
- `04_factures_recette.sql` : factures de recette Alpha et Beta, avec lignes et ventilation TVA.
- `07_salaires_recette.sql` : paramètres de lignes de salaire par défaut pour le tenant recette.

Contraintes :
- les scripts sont idempotents grâce aux clauses `ON CONFLICT` ou `WHERE NOT EXISTS`.
- ils doivent être exécutés uniquement par `./scripts/load-recette-data.sh`.
- en cas de rechargement, il est recommandé de sauvegarder les bases avec `./scripts/backup-recette-data.sh`.
