# Correctif RECETTE — dates et diagnostic IA

État initial : préparé localement le 2 novembre 2026, sans commit, push, image construite/publiée ou déploiement. Cette analyse a ensuite été complétée par la [validation réelle sur MSI](validation-msi-factures-dates-ia.md), qui identifie et corrige aussi le parcours de prévisualisation achats. Dans cette phase initiale : aucun accès VM, secret remplacé, appel IA réel ni donnée métier modifiée. Les manifestes et protections PREPROD restent identiques à HEAD.

## Causes établies et limites

### Dates

Dans Factures Front publié (3966786), le premier affichage sans état ni paramètres de filtre utilise déjà le 1er janvier de l'année locale, sans date de fin. Réinitialiser réécrit ces dates dans l'URL et le stockage de session, puis lance une recherche sans borne supérieure.

L'URL signalée contient deux dates explicites : `dateDebut=2026-10-31&dateFin=2026-11-29`. Elles remplacent les valeurs par défaut. C'est une explication suffisante de cet affichage avec la nouvelle image aussi. Leur présence ne prouve pas qu'une ancienne image est active. L'ancien calcul de mois via conversion UTC peut expliquer leur forme, mais leur origine exacte (ancien défaut, favori ou choix manuel) n'est pas démontrable à partir de l'URL seule.

Il serait incorrect de supprimer automatiquement cette période sans pouvoir la distinguer d'un choix utilisateur. L'action Réinitialiser constitue le choix explicite de revenir aux nouveaux défauts.

Un défaut supplémentaire est reproduit dans le service de mémorisation : tout paramètre URL, même `returnUrl`, supprimait les choix mémorisés ; une URL partielle supprimait les autres filtres mémorisés. Le correctif applique désormais la priorité par filtre : URL explicite > session > défauts. Les paramètres de navigation ne sont plus assimilés à des filtres.

### Extraction IA

Dans l'image API publiée (ac6b6da), le message « Clé IA invalide ou non autorisée » est produit par le client Anthropic pour HTTP 401 ou 403. Une configuration absente/incomplète produit un client désactivé et un autre message. L'échec signalé correspond donc au chemin de refus fournisseur, avant l'extraction métier. Il ne permet pas de décider entre clé refusée et autorisation d'accès refusée.

Le code retourné était néanmoins toujours `IA_INDISPONIBLE`, y compris pour absence de configuration. Une absence de modèle pouvait même être présentée comme une absence de clé. Le correctif distingue `IA_NON_CONFIGUREE`, `IA_AUTHENTIFICATION_REFUSEE` (401), `IA_ACCES_REFUSE` (403), `IA_MODELE_INDISPONIBLE` (404), `IA_LIMITE_ATTEINTE` (429), `JSON_IA_INVALIDE` et les erreurs métier existantes. Les deux parcours achats et les ventes propagent ces codes. Aucun corps d'erreur HTTP fournisseur n'est recopié dans les nouveaux messages.

Le chemin `./wavy install recette` utilise `release_images.recette_compose`, qui transmet provider, modèle, clé, timeout et taille maximale depuis `.env.recette`. Le test de rendu Compose réel confirme cette transmission et la priorité sur le shell ; une clé vide reste vide. Aucun correctif du câblage de l'installateur n'est justifié par ce contrôle.

Sur MSI uniquement, les fichiers `.env.local` et `.env.recette` déclarent Anthropic / `claude-sonnet-4-5-20250929`, avec une clé présente et identique entre ces deux fichiers. La clé n'a été ni affichée, ni modifiée, ni testée chez le fournisseur. Cela ne démontre pas la validité actuelle du compte, ni la configuration de la VM RECETTE.

## Vérification distante restant nécessaire

Après synchronisation du dépôt DevOps publié, le script `scripts/diagnose-recette-factures.py` est à exécuter **par l'opérateur sur la VM**, sans lancer l'installateur :

```sh
python3 scripts/diagnose-recette-factures.py
```

Il utilise uniquement `docker context inspect`, `docker inspect`, `docker image inspect`, le rendu `compose config` et les 400 dernières lignes de journaux sur 24 h. Aucune commande de démarrage/recréation, téléchargement d'image ou appel fournisseur. Un contexte Docker distant est refusé. Les sorties brutes Docker, valeurs de clé et lignes complètes des journaux ne sont jamais affichées.

Le relevé contient :

- référence attendue et identité de l'image active de Factures Front/API ; présence du digest attendu et correspondance du label de révision ; état démarré ;
- fournisseur et modèle reconnus, présence/absence des variables IA ; comparaison booléenne entre configuration rendue et conteneur actif, y compris pour la clé sans l'afficher ;
- présence de certaines surcharges Spring/JVM, sans en afficher le contenu ;
- seuls les statuts HTTP des erreurs fournisseur récentes, sans nom de fichier ni corps fournisseur. Ce relevé n'établit pas à lui seul le lien entre une erreur ancienne et le document signalé.

Factures Front attendu : `ghcr.io/fabffo/wavy-factures-front:0.2.0-3966786@sha256:f91f34c14b880f0d4eabb96b094b85b0ca41686bdb127ebf2ec047d68c31da9d`.

Sans ce relevé, l'image réellement active sur RECETTE, la présence des variables dans son conteneur et le statut exact 401/403 restent **non vérifiés**. Aucun changement de clé ou de modèle n'est proposé sans preuve. Si le conteneur diffère du rendu, la cause est une configuration active désynchronisée ; s'ils concordent et le fournisseur refuse, il faudra examiner les droits de la configuration existante avec l'opérateur, sans générer/remplacer de clé.

## Périmètre et validation

Trois dépôts seulement : Factures Front (priorité et tests), Factures API (codes/messages IA et tests), DevOps (diagnostic expurgé et tests de transmission). Aucun changement PWA, Trésorerie, autres applications, bases ou documents métier. Le client IA partagé conserve son protocole Anthropic, le modèle configuré et le format PDF/image ; aucun modèle de remplacement n'est imposé.

- Front : 179 tests réussis ; six nouveaux cas sur première ouverture, dates URL, mémorisation, URL partielle et réinitialisation. Build production réussi, avertissements de budgets existants.
- API : 283 tests réussis, zéro échec/erreur/skip ; cinq nouveaux cas, assertions enrichies sur absence de configuration, 401/403, réponse illisible et protocole MSI. Services et PostgreSQL de test isolés, fournisseur simulé.
- DevOps : 7 tests images/transmission, 5 tests diagnostic expurgé, 17 tests livraison, 28 tests diagnostic existant, 10 gardes PREPROD réussis.
- `git diff --check` réussi dans les trois dépôts. Aucune modification des versions/digests ou des fichiers PREPROD.

Le correctif reste à examiner avant toute autorisation de commit/publication. Il ne constitue pas une réparation attestée de l'authentification IA distante : son diagnostic exact reste en attente du relevé RECETTE.
