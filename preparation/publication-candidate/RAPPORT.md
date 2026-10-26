# Publication Wavy exécutée — 26 octobre 2026

Les huit lots approuvés ont été commités et poussés, puis les six images de release ont été construites et publiées avec les vrais SHA Git. Les 64 fichiers uniques autorisés constituent le périmètre des commits ; le suivi du manifeste ne touche que neuf fichiers déjà présents dans ces 64 chemins.

## Commits sources publiés

| Dépôt | Branche | Commit vérifié sur GitHub |
|---|---|---|
| wavy-devops | master | `c73a0afb260d6ea87c0d005a65d45676bf3fde7d` |
| wavy-erp-shell | master | `f6ee944b538be66fb60346e3f51fbbe5454cef53` |
| wavy-pwa | main | `9bfd21779135aa04030bb0ab83bf922fd015f506` |
| wavy-tiers-front | master | `05594f9f6df9842aba8c73f63fa2b7c93bb2601c` |
| wavy-contrats-front | master | `e05aabcf81fa408cb4cf9f067b7add1474582b07` |
| wavy-factures-front | master | `0663a9986675a5f83418973e895e2c20dd65406b` |
| wavy-tresorerie-front | master | `9c2bea6b2db19c6ab0c05e0479dc61aeccb1e6a4` |
| wavy-gateway | master | `2ac68294620facf7703a880cf6c3d37a28586c51` |

## Six images publiées et vérifiées

| Composant | Tag | Digest GHCR |
|---|---|---|
| erp-shell | `0.2.0-f6ee944` | `sha256:450328d7bea84b1c9e11616daa03067f6fe6da8dcc2d5bf929a46c909940ae96` |
| pwa | `0.2.0-9bfd217` | `sha256:9f10a7e8716b1fe4a09a91653e7591a00f8f5c64b1b1dc667cae685f5a375938` |
| tiers-front | `0.2.0-05594f9` | `sha256:45cd1ad15e450946e360347ae76738b28f20e69517e82313c5061f15dbc457ef` |
| contrats-front | `0.2.0-e05aabc` | `sha256:5562ba2cf480630aa66cc1ced8484f61b24c1dbf619966464f27a9df0d7484a6` |
| factures-front | `0.2.0-0663a99` | `sha256:e116a8eaf8141684b9ce27e056c8e21eadd30e42c2215c67a0c678ee4dca3726` |
| tresorerie-front | `0.2.0-9c2bea6` | `sha256:061a1b61488313f07c5f57b84b53f20b83f6ccdd4da03f484bacaf69fa76c7b6` |

Chaque digest a été relu dans GHCR ; le descripteur et le digest de configuration concordent avec l’image locale publiée. Labels OCI : version `0.2.0`, révision réelle et dépôt source attendu. Plateforme : `linux/amd64`. Les sept autres digests de la cohorte MSI ont aussi été revérifiés.

## Manifeste définitif

`cohort-candidate.json` est désormais le manifeste définitif publié et vérifié, malgré son nom historique. Il contient les treize références immuables. Cohorte : `56d43b10fa99dfd17edc072fefadaca6d9221984d0aad82ec209df2f552cd646`.

Les fichiers `versions/recette.digests.template` et `versions/preprod.digests.template` sont byte-identiques, avec treize SHA256 réels et aucun champ en attente. Les treize versions sont également identiques entre les deux jeux ; seules les configurations HTTPS/CORS restent propres à chaque environnement. Le plan PWA final est complété dans `release-plan.json.template`.

Conformément au périmètre de 64 fichiers et à la conservation des configurations existantes, les fichiers actifs `versions/recette.*`, `versions/preprod.*` et `preparation/pwa-notes-frais/release-plan.json` ne sont pas modifiés à cette étape. Les jeux livrés devront être matérialisés par la procédure d’installation autorisée. Il ne faut pas utiliser les anciens manifestes actifs pour installer cette release.

## Contrôles et préservation

Les builds de release ont réexécuté `npm ci`, les 392 tests frontaux, les builds Angular et Docker. Avant publication : 42 tests Gateway, 5 tests de justificatifs sur PostgreSQL jetable, 130 tests DevOps, 8 contrôles d’historique, 4 scénarios navigateur sur les images de validation avec API simulées et 6 smoke tests d’images avaient réussi. Les 247 validations d’isolation restent des preuves historiques, non une attestation PREPROD.

La validation GitHub DevOps du commit source est verte : https://github.com/fabffo/wavy-devops/actions/runs/40361231880.

Aucun accès VM, déploiement, nettoyage métier ou changement de base/volume. Les nouveaux HEAD API Socle et Contrats n’ont pas été intégrés : seuls leurs digests réellement testés sont conservés. Les caches, secrets et preuves privées restent exclus. Les treize historiques PREPROD sont préservés.

## GO / NO-GO

**GO pour les artefacts d’installation RECETTE distante** : sources poussées, six images publiées, treize digests vérifiés et cohorte commune RECETTE/PREPROD complète.

**NO-GO pour déclencher une installation avec les anciens manifestes actifs ou sans précontrôles cible**. La matérialisation des jeux livrés, la compatibilité des schémas existants, les volumes/documents et le profil HTTPS distant doivent être validés dans une étape d’installation explicitement autorisée. Aucun GO de déploiement PREPROD n’est donné ici.
