# Publication du correctif Factures et filtres — 2 novembre 2026

**Publication vérifiée, sans accès VM ni déploiement. GO pour installer le correctif avec `./wavy install recette` et effectuer les tests fonctionnels, après synchronisation du dépôt sur la VM par l'opérateur. L'authentification Anthropic sur RECETTE distante reste non vérifiée.**

## Commits publiés

- [factures-api `49b1f95`](https://github.com/fabffo/wavy-factures-api/commit/49b1f95045f94733d1147debcf7521a8c27bc682) : prévisualisation à montant global, conservation des valeurs inconnues et distinction des erreurs IA.
- [factures-front `4c52d7d`](https://github.com/fabffo/wavy-factures-front/commit/4c52d7d16ca3a7467f995e5766f7ae37c61ed4be) : priorité par filtre URL explicite > session > défaut, sans perte de choix sur une URL partielle.
- [DevOps `63f1d0e`](https://github.com/fabffo/wavy-devops/commit/63f1d0e4c7c9fe2886081f6a66ed592eef542c5e) : diagnostic expurgé, cycle MSI et preuves de validation.
- Le commit DevOps contenant ce bilan publie les références finales RECETTE/PREPROD ; son identifiant est communiqué dans le compte rendu de livraison.

## Images publiées

- `ghcr.io/fabffo/wavy-factures-api:0.1.0-49b1f95`
  - `sha256:73f8cf7d5de61af86efc034864d0bd6e969980b9b77d8ab46f632fb765ed742e`
- `ghcr.io/fabffo/wavy-factures-front:0.2.0-4c52d7d`
  - `sha256:65146af9c4f84d9ee01913060c2991e49a28d774f4db30e5ac9aac19ae312df8`

Les deux images sont linux/amd64. Pour chacune, le manifeste GHCR par tag et par digest a été lu directement : SHA256 des octets recalculé, Docker-Content-Digest comparé, blob de configuration vérifié, identifiant de l'image construite et labels OCI source/révision/version concordants. Les tags étaient absents avant publication et n'ont pas été remplacés.

Les 13 tags et références immuables de la cohorte complète ont également été vérifiés dans GHCR par recalcul SHA256. RECETTE et PREPROD portent exactement les mêmes 13 couples version/digest. Seuls Factures API et Factures Front sont modifiés ; les onze autres références restent identiques à la release précédente. Les quatre historiques Factures sont enrichis par ajout, avec tous leurs octets antérieurs conservés ; les autres historiques sont inchangés.

Preuves : [images et labels OCI](publication-correctif-factures-2026-11-02.images.json), [cohorte complète vérifiée au registre](publication-correctif-factures-2026-11-02.registry.json).

## Validation

- Revue des modifications et des preuves MSI avant commit, contrôle de propreté Git et synchronisation GitHub.
- Tests relancés par le script `scripts/build-image.sh` avant construction : **286 API**, zéro échec/erreur/skip ; **179 Front**, puis build de production réussi.
- Contrôles DevOps : images/transmission 7, diagnostic expurgé 6, cycle MSI 29, menu 17, HTTPS MSI 10, authentification locale 7, livraison 17, gardes PREPROD 10. Après mise à jour des manifestes : configuration PREPROD 36, images/transmission 7 et livraison 17 réussis.
- Preuve fonctionnelle antérieure à la publication : **20 contrôles Chrome réels** sur MSI et extraction réelle du PDF de loyer via Anthropic. Une ligne de quantité 1, PU HT/HT/TTC 3000 €, zéro TVA provisoire à confirmer, case non cochée et création désactivée ; aucune requête de création. Empreintes des 50 tables contrôlées et des documents inchangées. Voir la [validation MSI](validation-msi-factures-dates-ia.md).
- Les tests API de publication utilisent des bases Testcontainers isolées et des fournisseurs simulés. Aucun nouvel appel réel Anthropic pendant la publication.
- `git diff --check`, cohérence des 13 références, conservation des onze composants, des historiques et des fichiers de protection PREPROD vérifiés.

Aucune clé IA affichée, copiée ou remplacée. Aucun secret, base applicative, volume, document ou réglage runtime n'a été modifié par cette publication. Les seuls conteneurs de construction/tests sont locaux et isolés. Aucun service applicatif n'a été recréé à cette étape. Les avertissements préexistants de budgets Front/dépendances restent hors périmètre du correctif.

## Diagnostic expurgé de RECETTE distante

La réussite Anthropic sur MSI ne prouve pas la validité de la configuration distante. Le refus 401/403 précédemment observé sur RECETTE n'est **pas déclaré résolu** par cette publication. Le correctif distingue désormais configuration absente, authentification refusée, accès fournisseur refusé, modèle introuvable et réponse d'extraction invalide.

Après synchronisation du dépôt DevOps sur RECETTE, l'opérateur peut exécuter, sans installer ni appeler le fournisseur :

```sh
python3 scripts/diagnose-recette-factures.py
```

Ce relevé en lecture seule compare fournisseur, modèle, présence de clé et configuration rendue avec le conteneur actif. Il affiche uniquement une comparaison booléenne pour la clé, jamais sa valeur ou son empreinte. Il fournit l'identifiant et les digests de l'image réellement active, ses labels OCI reconnus et l'existence éventuelle d'un montage de JAR/fichiers statiques ; il compare cette identité avec les nouveaux manifestes. Les journaux sont limités aux statuts HTTP fournisseur récents, sans lignes brutes, document ou corps fournisseur.

Le diagnostic refuse un contexte Docker distant et doit être lancé par l'opérateur sur la VM. Il n'effectue aucun pull, démarrage, modification de configuration ou appel IA. Il ne remplace pas le test réel d'extraction après installation. Aucune clé ne doit être recopiée depuis MSI ou remplacée pour contourner un refus.

Le parcours de livraison reste celui existant : synchroniser la release, `./wavy install recette`, vérifier l'image active et faire un test réel d'extraction. PREPROD attend toujours la validation humaine ; ses protections sont inchangées, et son arrêt volontaire ne bloque pas cette publication. Aucun nouveau mécanisme de livraison n'est ajouté.
