# Versionnement et promotion des images Wavy

## Objectif

Wavy applique le principe **build once, deploy many** : une image Docker est
construite une seule fois, publiée dans GitHub Container Registry (GHCR), puis
la même image est déployée successivement en recette et en préproduction.

Les fichiers `versions/recette.env` et `versions/preprod.env` décrivent les
versions attendues dans chaque environnement. Ils sont chargés séparément des dotenv machine par Compose. Les digests
individuels sont dans `versions/<environnement>.digests`. PREPROD les contrôle
avant remplacement et exécute les images par digest.

## Une version par service

Chaque API, interface web et composant transverse possède sa propre variable de
version. Les composants sont répartis dans des dépôts Git indépendants et
n'évoluent pas nécessairement au même rythme. Un tag global imposerait une
version artificiellement commune et ne permettrait pas de savoir précisément
quel code est déployé pour chaque service.

Par exemple, Factures peut recevoir une correction sans reconstruire Socle :

```text
FACTURES_API_VERSION=2.4.1-a8f31c2
SOCLE_API_VERSION=2.3.0-a31cd55
```

## Convention de version

Le tag d'une image applicative suit la convention :

```text
<version>-<sha_git_court>
```

Exemple :

```text
2.4.1-a8f31c2
```

- `2.4.1` est la version applicative ;
- `a8f31c2` est le SHA Git court du commit utilisé pour construire l'image.

Le SHA Git est l'identifiant du commit dans l'historique Git. Son inclusion
permet de retrouver sans ambiguïté les sources qui ont produit l'image. Le SHA
doit provenir du dépôt du composant concerné et le build doit être effectué
depuis un arbre de travail propre.

Le tag `latest` est interdit : il est mutable, ne décrit ni la version ni le
commit et peut désigner une image différente entre deux déploiements.

## Registre cible

Les images ont vocation à être publiées dans GitHub Container Registry :

```text
WAVY_IMAGE_REGISTRY=ghcr.io/fabffo
```

Le namespace `fabffo` est celui du propriétaire GitHub observé dans le remote
du dépôt `wavy-devops`. Aucune image n'est poussée pendant cette étape.

Une référence complète aura, par exemple, la forme suivante :

```text
ghcr.io/fabffo/wavy-factures-api:2.4.1-a8f31c2
```

## Promotion de recette vers préproduction

Le déroulement cible pour un service est le suivant :

1. La CI compile et teste le commit du service.
2. Elle construit une seule image, la tague avec la version et le SHA Git, puis
   la publie dans GHCR.
3. La version est inscrite dans `versions/recette.env` et cette image est
   déployée en recette.
4. Les healthchecks, contrôles Flyway et smoke tests valident la recette.
5. Après validation manuelle, la valeur exacte de la variable du service est
   recopiée de `versions/recette.env` vers `versions/preprod.env`.
6. La préproduction récupère l'image existante dans GHCR sans exécuter de
   `docker build`.

Exemple de promotion :

```text
# versions/recette.env, après validation
FACTURES_API_VERSION=2.4.1-a8f31c2

# versions/preprod.env, après décision de promotion
FACTURES_API_VERSION=2.4.1-a8f31c2
```

Les autres variables ne changent pas si leurs services ne sont pas promus.

## Pourquoi ne jamais reconstruire après la recette

Deux builds exécutés à des moments différents peuvent produire des images
différentes malgré des sources identiques : une image de base ou une dépendance
peut avoir évolué, ou le contexte de build peut différer. Reconstruire pour la
préproduction invaliderait donc la preuve apportée par les tests de recette.

La promotion doit uniquement modifier la référence de version de
l'environnement cible et tirer l'image déjà validée. La comparaison du
digest immuable complète la vérification du tag.

## Règles de gestion

- Une variable vide signifie qu'aucune version n'est encore enregistrée.
- Une version ne doit être renseignée qu'après publication de l'image associée.
- Les fichiers de recette et de préproduction peuvent contenir des versions
  différentes tant qu'une promotion n'a pas été validée.
- Une promotion copie le tag exact ; elle ne crée pas un nouveau tag et ne
  reconstruit pas l'image.
- Aucun secret ne doit être ajouté aux fichiers du répertoire `versions/`.

## Historique PREPROD

Les manifestes expriment une autorisation ; les TSV PREPROD commencent vides
(en-têtes uniquement, même convention RECETTE). Les lignes sont ajoutées après
validation runtime complète, jamais lors de cette préparation. Le journal réel
est séparé (`deployments/preprod*.tsv`) et distingue INITIALIZE/PENDING_SMOKE,
VALIDATE_INITIAL, DEPLOY et ROLLBACK. Voir [PREPROD](../README_PREPROD.md).
