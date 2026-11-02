# Publication Wavy — 2 novembre 2026

**GO pour installer la release sur RECETTE distante avec `./wavy install recette`, puis réaliser les tests fonctionnels utilisateur.** Aucun déploiement exécuté. PREPROD attend la validation humaine avant installation ; sa VM volontairement arrêtée ne bloque pas la publication.

## Sources publiées

- DevOps automatisation Windows : `f505bd9` (master).
- [factures-api ac6b6da](https://github.com/fabffo/wavy-factures-api/commit/ac6b6daeaba1c6de259c6548f54563d04fc07085) (master).
- [factures-front 3966786](https://github.com/fabffo/wavy-factures-front/commit/39667865315f229bab377340ed60f3ab32756790) (master).
- [tresorerie-front ebe7584](https://github.com/fabffo/wavy-tresorerie-front/commit/ebe75844e081a85a77f401e268ed274a6696d53b) (master).
- [pwa 9507982](https://github.com/fabffo/wavy-pwa/commit/95079827f2e924479ac657c32ad38e460e83e52c) (main).

Le commit DevOps contenant ce bilan porte les manifestes finaux ; son identifiant est fourni dans le compte rendu de livraison. Les cinq arbres Git sont propres à la livraison et les branches sont vérifiées contre GitHub.

## Images publiées et vérifiées

- `ghcr.io/fabffo/wavy-factures-api:0.1.0-ac6b6da`
  - `sha256:16cdd278ea4326e6528f84341de9cc08464def7c7837be329d6a8ba3cb9e96ae`
- `ghcr.io/fabffo/wavy-factures-front:0.2.0-3966786`
  - `sha256:f91f34c14b880f0d4eabb96b094b85b0ca41686bdb127ebf2ec047d68c31da9d`
- `ghcr.io/fabffo/wavy-tresorerie-front:0.2.0-ebe7584`
  - `sha256:f715747e88cbf942a6d61d68a6c68e2adaa35812afefd86a70e654baa64ebb9c`
- `ghcr.io/fabffo/wavy-pwa:0.2.0-9507982`
  - `sha256:eb04852ea2b7cf33e733502e89600cc9858a0ce44503bb4a8fcb928afe1d6c18`

Vérification directe GHCR : réponse par tag puis par digest, SHA256 calculé sur les octets du manifeste et du blob de configuration, concordance avec Docker-Content-Digest et l'identifiant de l'image locale. Plateforme linux/amd64 ; labels OCI source, révision et version conservés dans le [relevé JSON](publication-windows-dates-extraction-2026-11-02.images.json).

RECETTE et PREPROD référencent exactement les mêmes 13 couples version/digest. Seuls les quatre composants ci-dessus changent. Les neuf autres images restent identiques ; les historiques versionnés sont conservés avec ajout des quatre nouvelles références par environnement. Aucune protection PREPROD n'est modifiée.

## Validation

- API Factures : 278 tests, zéro échec/erreur/skip (résumé de l'exécution Maven courante, pas les rapports XML résiduels).
- Factures Front : 173 tests ; Trésorerie Front : 15 ; PWA : 58. Installations npm ci et builds de production réussis ; images construites depuis des commits propres.
- DevOps : 207 contrôles locaux réussis (diagnostic 28, livraison 17, images 6, PWA 25, documents 11, CORS 3, configuration PREPROD 36, gardes 10, build 14, historique 8, commandes locales 25, menu 17, nginx PWA 1, restauration isolée 1, nginx PREPROD 5). Configuration PREPROD, images et livraison revérifiées après modification des manifestes.
- Windows : 17 assertions locales réussies, sans réseau. Copie installée conforme au script revu, aux espaces de fin de ligne près. Tâche Wavy-Connections active, déclencheur utilisateur à l'ouverture de session, MultipleInstances=IgnoreNew. Deux demandes de démarrage successives conservent le seul superviseur PID 33592. Le relais RECETTE 34443 appartient au seul PID SSH 11176 (écoutes IPv4 et IPv6 du même processus). PREPROD 24443 absent comme attendu ; boucle de reprise sans commande distante et sans démarrage de VM.
- git diff --check, cohérence des 13 références et conservation des neuf composants inchangés vérifiés.

## Réserves et limites

Un redémarrage complet de Windows n'a pas été effectué : dernier démarrage Windows le 30 octobre, lancement de la tâche le 1er novembre. La configuration de démarrage, l'activité présente et l'absence de doublon sont vérifiées ; le fonctionnement après le prochain redémarrage et la reconnexion PREPROD lors du retour de son port SSH restent à observer. Ce bilan ne les présente pas comme validés. Une clé chiffrée exige son déverrouillage utilisateur dans l'agent existant.

Les tests fonctionnels Chrome/ERP/PWA sur la nouvelle installation distante restent à réaliser par l'utilisateur. Les builds signalent des dépassements de budgets CSS non bloquants et GitHub signale des vulnérabilités de dépendances existantes, hors modifications de ce lot.

Aucun accès aux VMs, aucune commande distante, aucun déploiement ; aucune base, donnée métier, pièce, secret ni protection PREPROD modifiés. Les tests utilisent exclusivement des fixtures et conteneurs locaux isolés. La PWA conserve sa politique d'activation existante.
