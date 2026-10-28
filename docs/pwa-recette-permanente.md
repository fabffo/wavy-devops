# Mobile PWA permanente en RECETTE — configuration et prérequis

> Parcours standard actualisé : [livraison et installation](livraison-standard.md).
> Le mode `technical` RECETTE remplace les attestations fonctionnelles préalables
> par les contrôles techniques automatiques ; le mode historique reste disponible.

## Décision actuelle : NO-GO pour l'activation distante

Le diagnostic fourni confirme un problème de configuration du Shell : manifeste
fermé et absence de montages. Le correctif ci-dessous le résout sans changer les
images ou les fichiers internes des conteneurs. Il n'a pas été appliqué à la VM.

La présence des 13 conteneurs et la connexion ERP HTTPS ne qualifient pas le
parcours PWA complet. Les prérequis distants suivants ne sont pas attestés ici :

1. Volume privé de justificatifs existant, nom exact, montage Factures
   `/app/justificatifs`, UID/GID effectifs, permissions, capacité et sauvegarde /
   restauration éprouvées. Aucun stockage ne sera créé, vidé, déplacé ou chowné
   par ce correctif. Un stockage existant différent nécessite une revue dédiée.
2. Compte ordinaire `NOTE_DE_FRAIS`, association utilisateur/porteur Tiers,
   droits marchands et refus des rôles sans accès. Le correctif Gateway est
   publié dans `0.1.0-3ff5c3b` et référencé par digest dans RECETTE et PREPROD.
   Les nouvelles autorisations sont réservées à RECETTE ; PREPROD/production,
   même en profils mixtes, ne gagnent aucun droit. La publication ne qualifie
   pas les comptes ou les données de la VM cible.
3. Qualification des sessions réelles, changement de société, deux tenants,
   droits sur les notes et les justificatifs, accès ERP intégré et connexion
   autonome smartphone / service worker sur l'origine HTTPS prévue.
4. Pour les écritures : création/modification, téléchargement après reconnexion,
   refus inter-tenant/inter-société et remplacement concurrent de justificatifs.
5. Les accès directs aux API doivent être privés / filtrés. Le Compose RECETTE
   historique publie des ports API : leur filtrage réseau n'est pas confirmé. Le
   paramètre optionnel `WAVY_RECETTE_PRIVATE_BIND_ADDRESS` permet de réserver les
   ports à loopback lorsque le proxy HTTPS est local, sans changer le repli existant.
   Le verrou Notes décrit ci-dessous est un verrou Nginx de l'entrée Shell,
   pas une nouvelle autorisation backend. Il ne protège pas un port API exposé
   qui contourne le Shell. L'authentification métier reste obligatoire partout.

Les réglages IA et l'accès au fournisseur sont des prérequis supplémentaires
pour l'extraction IA. Ils ne sont pas déduits de la visibilité du module ; aucune
création automatique de facture achat ni aucun appel IA n'est activé ici.

## Configuration persistante, même parcours Compose

Les paramètres de `.env.recette` sont lus par le chemin existant
`scripts/release_images.py`, utilisé par `./wavy start recette` et les commandes
historiques qui appellent `compose recette`. PREPROD n'emprunte pas ce chemin.

| Paramètre | Défaut | Effet |
| --- | --- | --- |
| `WAVY_PWA_ENABLED` | `false` | Manifeste Shell et routes `/pwa`, `/pwa/` |
| `WAVY_NOTES_WRITES_ENABLED` | `false` | Mutations Notes à l'entrée Shell, indépendantes du menu PWA |
| `WAVY_PWA_PUBLIC_ORIGIN` | `https://recette.wavyservices.fr` | Origine exacte exigée pour les mutations Notes |
| `WAVY_PWA_QUALIFICATION_FILE` | vide | Compte rendu privé revu et approuvé, lié aux sept images concernées |
| `WAVY_FACTURES_JUSTIFICATIFS_VOLUME` | vide | Volume Docker existant et qualifié ; déclaré external, jamais créé |

`./wavy pwa recette check` affiche les prérequis manquants sans Docker, réseau ou
mutation. Son éventuel GO configuration ne remplace pas les contrôles runtime.
Le modèle `docker/recette-pwa/qualification.example.json` contient des contrôles
à false et n'est jamais une autorisation. Un compte rendu privé 0600, sans cookie
ou mot de passe, doit être produit à partir d'une qualification réelle revue ;
ne pas recopier des true pour contourner un prérequis.

Le booléen `enabled` conserve son sens de disponibilité : les rôles existants du
Shell contrôlent le menu et l'iframe ; l'API contrôle tenant, société, utilisateur,
porteur et documents. Les fichiers statiques de la PWA restent servis sans
session quand le module est ouvert, afin de permettre sa page `/pwa/connexion`
sur smartphone. Ils ne contiennent aucun justificatif. Les guards Angular et
les réponses 401/403 des API continuent de protéger les données métier.

Avec visibilité=true et écritures=false, l'application est consultable mais le
Shell bloque POST/PUT/PATCH/DELETE Notes. Ce verrou s'applique aussi aux clients
ERP passant par ces mêmes routes ; il ne distingue pas le menu d'origine.
Inversement, visibilité=false et écritures=true permet de conserver les
mutations Notes qualifiées depuis l'ERP sans afficher Mobile PWA.

## Intégration et persistance

Le Shell reçoit quatre montages bind en lecture seule : son template Nginx, le
fichier existant `/etc/nginx/pwa-route.conf`, le manifeste existant
`/usr/share/nginx/html/pwa-integration.json` et la politique Notes. Tous les
fichiers viennent du dépôt et survivent aux redémarrages et recréations.
Le fragment Compose intermédiaire est temporaire ; aucun montage ne pointe sur
ce fragment ou sur un fichier temporaire. Aucun `docker cp`, `exec sed` ou
rechargement modifiant les fichiers internes n'est nécessaire.

Les routes ouvertes réutilisent la configuration candidate PWA existante,
adaptée au nom RECETTE et à une résolution DNS différée. `/pwa` redirige vers
`/pwa/`, le préfixe est retiré pour le serveur PWA et les query strings sont
conservées. Connexion, assets et service worker utilisent ce même préfixe.
Aucune route statique ne donne accès au volume des justificatifs.
Les chemins API ambigus sont refusés ; les réponses du backend sont conservées.

Les 13 images restent en `version@sha256`. Avant toute recréation demandant une
ouverture, le compte rendu doit correspondre aux sept références PWA/Shell/
Factures/Factures front/Gateway/Socle/Tiers, à l'origine et au volume. Les services
existants doivent être actifs avec ces digests, et le stockage Factures doit
déjà être monté correctement. Aucun service ou stockage n'est provisionné pour
forcer une ouverture. Le contrôle de conservation des montages s'applique aussi
quand l'interface est fermée. La fermeture de PWA ne détache jamais le volume
configuré. Une variable de volume oubliée ne peut pas retirer silencieusement
un montage documentaire déjà actif.

Après validation et publication du correctif, les réglages sont saisis une seule
fois dans la configuration d'environnement. Le démarrage standard `./wavy start
recette` applique la configuration : aucune commande séparée d'activation à
rejouer à chaque release. Les mêmes réglages sont repris au redémarrage.
Le compte rendu n'a pas de bail de session ni de TTL ; les tests ne ferment pas
le module et ne changent pas les paramètres. Une modification des images liées,
de l'origine ou du stockage exige une requalification ; elle est refusée avant
remplacement si le compte rendu est périmé par rapport à la release. Les arrêts
et diagnostics restent disponibles. Aucun déploiement n'a été lancé pour cette
préparation.

## Périmètre PREPROD et MSI

Le cycle HTTPS local permanent MSI et son stockage ne sont pas modifiés.
Aucun fichier Compose, manifeste, orchestrateur, gate ou réservation PREPROD ne
change. `./wavy pwa preprod check` est refusé. L'activation PREPROD reste soumise
à son workflow renforcé et à une validation spécifique.

## Vérifications reproductibles sur MSI

- `python3 scripts/test-recette-pwa.py` : configuration et rendu Compose réel,
  séparation visibilité/écritures, qualification, persistance, refus avant
  mutation, conservation du volume et PREPROD inchangé.
- `python3 scripts/test-recette-pwa-nginx.py` : Nginx réel dans des conteneurs
  jetables sans réseau/ports/volumes métier, entrée standard avec envsubst, trois modes d'ouverture, connexion
  et service worker, query strings, origine des mutations et propagation des
  refus 401/403/404 d'un backend synthétique ; conteneurs supprimés.
- Tests existants PWA et Shell : session restaurée/expirée, changement de société,
  rôle du menu, contexte et iframe. Les sources correspondent aux SHA actifs
  `9bfd217` et `f6ee944`.
- Tests Factures ciblés (source `09fcd98`) : contrôleur Notes, justificatifs,
  concurrence, contexte, stockage privé et réconciliation ; PostgreSQL
  Testcontainers et fichiers de fixtures jetables uniquement.

Les tests de composants ne prouvent pas les prérequis distants. Ils ne justifient
pas de marquer un compte rendu RECETTE approuvé. La publication de cette préparation est autorisée séparément. Aucun test de
composant ne justifie un accès VM, un déploiement ou une activation sans les
contrôles cible ; voir le rapport de publication associé.

## Finalisation et diagnostics complémentaires

Le dossier [de qualification et restauration](pwa-recette-qualification.md)
précise les droits corrigés, la campagne réelle à autoriser, le backup standard
DB + justificatifs et la restauration isolée. Le diagnostic existant accepte
maintenant `--runtime`, `--backup-dir <lot>` et `--plan`, sans exécution de campagne
métier. Aucun accord de publication ou de déploiement n'est supposé.
