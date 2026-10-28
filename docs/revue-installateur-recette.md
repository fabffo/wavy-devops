# Revue ciblée de l’installateur RECETTE — 28 octobre 2026

## Décision et périmètre

**Installations suspendues. Publication du correctif autorisée le 28 octobre 2026.**
Les 126 tests ciblés et les contrôles Git/Bash ont été rejoués avec succès avant
publication. Aucun accès VM ni installation n’a été effectué pendant cette revue. Les sources ont été
comparées aux versions applicatives épinglées et aux configurations DevOps
publiées `52eaf39`, `6294480` et `d61c465`.

Le refus `Profil incohérent : recette/socle-api` provient d’une exigence trop
uniforme : l’installateur confondait l’environnement Docker RECETTE et le nom du
profil Spring. Le Compose antérieur à l’installateur avait **Socle `local` par
défaut**. Les autres API et Gateway avaient `recette`. La valeur exacte du dotenv
et des conteneurs de la VM n’a pas été lue ; ce rapport ne prétend pas la connaître.

La correction ne remplace aucun dotenv existant et ne change aucun profil de
conteneur. Elle rétablit le défaut Socle historique, accepte ce contrat dans la
validation et **compare avant installation le profil candidat au profil actif**.
Une divergence dans l’un ou l’autre sens est remontée sans réécriture automatique.

## Diagnostic consolidé intégré au parcours existant

```bash
./wavy install recette --check
```

Cette option ne déploie rien. Elle est également appelée automatiquement au début
d’une installation future autorisée, avant création de verrou, pull, provisionnement
et sauvegarde. Le diagnostic poursuit les contrôles indépendants après une erreur,
avec des statuts `error`, `warning`, `planned` et `pending`. Code de sortie 1 si
au moins une erreur est observée ; les contrôles impossibles ou futurs restent
explicitement signalés, jamais marqués réussis.

Le JSON n’imprime ni secrets, ni environnement complet, ni contenu documentaire.
Les lectures Docker sont limitées à `context inspect`, `info`, `compose config` /
`version` / aide de `up`, `inspect`, `volume ls` / `inspect`, `manifest inspect` et des `exec`
explicitement en lecture : métadonnées documentaires, versions des outils et
`SELECT 1`. Les requêtes HTTPS sont GET/OPTIONS sans session. Aucune exécution de `up` (son aide seule est lue), `run`,
`pull`, stop/start, mkdir/chown/chmod de volume, dump, restauration ou migration
n’est exécuté par `--check`. Aucun verrou absent n’est créé ; Git est lu avec les
verrous optionnels désactivés. Seul le rendu Compose utilise son fichier de
travail temporaire existant, hors fichiers métier.

Si le daemon local système ne peut pas être établi, ou si l’hôte n’est pas celui
désigné par le dotenv, les inspections correspondantes sont déclarées impossibles.
Le diagnostic ne contacte pas un daemon distant fourni par DOCKER_HOST/CONTEXT.

## Contrat des 13 composants

| Composant | Profil candidat publié / conservé | Point de disponibilité | Données / observation |
| --- | --- | --- | --- |
| socle-api | `local` historique ; `recette` si déjà explicitement sélectionné et actif | 8080 `/actuator/health`, curl | DB Socle ; transition de sécurité/DDL non implicite |
| tiers-api | `recette` (groupe `secure`) | 8081 `/actuator/health`, wget | DB Tiers et compte interservices |
| contrats-api | `recette` (groupe `secure`) | 8082 `/actuator/health`, wget | DB et volume pièces jointes Contrats conservés |
| factures-api | `recette` (groupe `secure`) | 8083 `/actuator/health`, wget | DB et justificatifs externes privés ; grâce 120 s / 18 essais |
| tresorerie-api | `recette` (groupe `secure`) | 8086 `/actuator/health`, wget | DB Trésorerie ; grâce 120 s / 18 essais |
| gateway | `recette` | 8088 `/actuator/health`, wget | CORS HTTPS commun et règles PWA publiées |
| socle-front | Sans profil Spring (Nginx) | 80 `/`, route `/modules/socle/` | Image épinglée, aucun build |
| tiers-front | Sans profil Spring (Nginx) | 80 `/`, route `/modules/tiers/` | Image épinglée, aucun build |
| contrats-front | Sans profil Spring (Nginx) | 80 `/`, route `/modules/contrats/` | Image épinglée, aucun build |
| factures-front | Sans profil Spring (Nginx) | 80 `/`, route `/modules/factures/` | Image épinglée, aucun build |
| tresorerie-front | Sans profil Spring (Nginx) | 80 `/`, route `/modules/tresorerie/` | Image épinglée, aucun build |
| pwa | Sans profil Spring (Nginx) | 80 `/`, `/pwa/connexion`, service worker | Droits métier inchangés |
| erp-shell | Sans profil Spring (Nginx) | 80 `/`, manifeste et routes modules/PWA | Montages de configuration en lecture seule |

Socle `8b7a3f0` : `application-local.properties` fixe `ddl-auto=update` ;
`application-recette.properties` fixe `ddl-auto=validate`, et
`application.properties` déclare `spring.profiles.group.recette=secure`.
`SecuriteConfiguration` sélectionne une autre chaîne sous `secure`.
**Passer `local` à `recette` n’est donc pas une correction cosmétique.** Aucun test
fonctionnel de cette transition n’est revendiqué ; elle n’est pas imposée par le
correctif. Une configuration Socle `recette` déjà active reste conservée.

Les autres contrats ont été lus aux commits épinglés : Tiers `7642a09`, Contrats
`527874b`, Factures `09fcd98`, Trésorerie `45fd268`, Gateway `3ff5c3b`. Leurs profils
`recette` publiés et leurs groupes de sécurité restent inchangés. Les mélanges
`dev`, `test` ou les profils non couverts ne sont pas déclarés compatibles par
simple changement du validateur. L’état cible sera donné par le diagnostic VM.

## Tableau consolidé des refus et prérequis

Les preuves ci-dessous sont des tests locaux ou des lectures de code publié.
Aucune ligne ne constitue une attestation d’état VM.

| Contrôle / blocage | Cause ou prérequis | Correction / traitement | Preuve de validation |
| --- | --- | --- | --- |
| Arguments CLI | Environnement ou option invalide | `recette --check` ajouté ; PREPROD conserve son parcours | Tests de syntaxe Bash et CLI ciblés |
| Git sale avec historique légitime | `versions/` incluait les historiques runtime | Exclusions exactes des 13 TSV RECETTE conservées, aucun reset/stash/effacement | Tests vrai Git, historique modifié/indexé conservé octet pour octet |
| Script, Compose ou manifeste non publié | État de livraison non reproductible | Contrôle strict conservé, y compris non-suivis, index et erreurs Git | Tests scripts, deux Compose, quatre manifestes, fichiers inconnus |
| Versions, digests, historique incompatibles | Release manquante, mauvaise forme, conflit d’une version | Contrôle des 13 composants indépendamment ; historique malformé remonté proprement | Tests multi-digests absents, conflits et non-régression images |
| Profil Socle `local` refusé | Exigence uniforme `recette` injustifiée | Défaut historique rétabli ; `local` accepté pour Socle ; warning explicite sur son DDL historique | Rendu Compose réel + reproduction du refus signalé |
| Transition implicite de profil | Changement possible des chaînes de sécurité, du DDL, bootstrap/cookies | Comparaison candidat/actif, sans modifier la configuration | Tests local→recette, recette→local refusés ; recette déjà actif accepté |
| Autre profil inattendu | Contrat publié différent de la configuration locale | Rapporter chaque API/Gateway concerné ; ne pas transformer en `recette` automatiquement | Plusieurs mauvais profils signalés simultanément |
| Hôte ou socket incorrect | Risque de cibler MSI ou un autre daemon | Gardes existantes conservées, runtime différé si destination non prouvée | Test DOCKER_HOST distant : aucune lecture du daemon demandé |
| Réservation MSI / opération concurrente | Cycle local permanent ou backup déjà en cours | Détection en lecture des réservations et verrous existants | Inspection code ; tests de verrou RECETTE existants |
| Docker Compose / tar incomplets | `--wait-timeout` ou tar peut manquer malgré la présence de Docker | Vérifier l’aide de Compose et le binaire tar dans Factures avant tout backup | Test des deux capacités manquantes signalées ensemble |
| Python / outils manquants | `file_digest` exige Python ≥3.11 ; docker, Git, flock nécessaires | Inventaire préliminaire, refus précis avant backup | Version locale vérifiée ; diagnostic ne lance pas le backup |
| Dotenv absent / public / malformé | Configuration machine privée requise | Erreurs ligne/clé sans afficher les valeurs ; propriétaire/permissions contrôlés | Tests de défauts simultanés, pas de secret dans le rapport |
| Doublons / variables de version dans le dotenv | Priorité ambiguë ou contournement des manifestes | Gardes conservées ; doublons listés sans arrêter les autres vérifications | Tests overrides/duplications et rendu Compose existants |
| Quotes dans hostname / noms DB / secrets | Le shell conservait les quotes ; le parseur PWA rejetait les quotes internes des secrets | Quotes externes retirées dans le lecteur commun ; secrets séparés du parseur restrictif PWA | Test hostname quoté, secret avec apostrophe, rendu Compose |
| Mode historique / PWA / écritures fermées | Nouveaux paramètres initiaux non définis sur une ancienne installation | Tous les paramètres manquants remontés ensemble ; aucune activation silencieuse | Test erreurs multiples ; mode technique ne lit pas de preuve fonctionnelle |
| Qualification historique | En mode qualification : approbation, origine, 7 images, volume, hash backup/restauration et checks lus | Contrat historique conservé ; aucun de ces comptes rendus n’est fabriqué en mode technique | 25 tests PWA historiques + nouveaux tests de diagnostic |
| Origine HTTPS / CORS | Origine invalide, absente, wildcard ou contradictions | Une origine PWA typée et une variable API/Gateway commune ; vérifier rendu + OPTIONS réel | Tests CORS, mauvais paramètres simultanés et HTTPS simulé |
| En-têtes proxy | Spring ne reçoit pas forcément le schéma HTTPS | Stratégie `framework` existante contrôlée ; fichiers Nginx inchangés | Rendu réel et contrôles CORS/proxy existants |
| Projet ou conteneurs incorrects | Les noms fixes seuls ne prouvent pas le projet | Contrôle des 18 conteneurs, projet et état, indépendamment | Deux conteneurs absents et un arrêté : les trois signalés |
| Configuration DB divergente | Changer les variables ne renomme pas une DB existante et ne change pas son mot de passe | Comparaison des métadonnées DB/candidat, aucun ALTER/rename automatique | Test divergence DB ; valeur secrète absente du JSON |
| Secret absent / exemple / compte Tiers incomplet | Anciens exemples insuffisants pour une VM durable | Noms des clés en défaut listés ; ne pas remplacer les secrets existants | Tests secrets multiples et compte incomplet |
| Montage DB/Contrats/Factures différent | Recréation susceptible de masquer un volume, bind ou sous-chemin | Comparaison des destinations et noms réels, lecture seule, pas de détachement | Tests volume DB différent, volume documentaire RO et sauvegarde existante |
| Stockage Factures non standard | Racine différente ou contenu déjà présent au futur point de montage | Refus conservatoire ; aucune migration documentaire implicite | Tests de conservation PWA ; diagnostic initial avant provisionnement |
| Premier rattachement à racine vide | Ancienne image sans variable de stockage, volume absent ou non monté | Distinguer absent autorisé (`planned`), absent non autorisé (`error`), non-vérifiable (`pending`) | Test premier rattachement : aucune création de conteneur/volume |
| Volume existant non vide avant premier rattachement | Le backup initial exige un volume vide pour ce cas | Contrôle par métadonnées host si accessibles ; sinon déclaration non vérifié | Code en lecture seule ; ne pas annoncer un GO sur une donnée inaccessible |
| Droits, propriétaire, liens, capacité documentaire | Le probe s’arrêtait au premier défaut ; une erreur de parcours pouvait être masquée | Probe agrégé, codes sans noms de documents ; erreurs find explicites | Deux défauts de modes remontés, mêmes octets et permissions après test |
| Hiérarchie / identifiants / tailles des justificatifs | Le scellement pouvait refuser un lot seulement après arrêt des writers | Validation des mêmes règles de chemins/tailles par métadonnées avant backup, sans lire les contenus | Probe shell réel sur fixture, deux erreurs de structure remontées ensemble |
| Lien cassé à l’ancienne racine | `test ! -e` seul pouvait accepter un lien symbolique cassé | Tester aussi `-L` ; aucun masquage du lien | Probe partagé testé sur lien cassé et dossier non vide, tous deux préservés |
| Ports directs exposés | Repli historique 0.0.0.0 ; futur rendu loopback | Rendu privé contrôlé, exposition actuelle classée changement prévu | Tests ports rendus et inspection simulée |
| Placement du proxy HTTPS | Un port Shell déplacé vers loopback n’est joignable que par un proxy local approprié | Signaler la topologie non prouvée si le Shell actuel est externe ; ne pas déduire du HTTPS actuel le succès futur | Test publication Shell 0.0.0.0 : `pending network.proxy` |
| Délai de disponibilité | Factures/Trésorerie peuvent dépasser l’ancien budget | Délais déjà publiés conservés : grâce 120 s, 18 essais, attente 600 s ; timeout typé | Tests du rendu des deux healthchecks et timeout invalide |
| Espace / répertoires de backup / verrou backup | Un problème apparaît sinon après pull ou arrêt des writers | Détection capacité, accès et verrou existant avant modification | Contrôles lecture seule et tests du parcours fail-closed |
| Outils / connexion des cinq DB | pg_dump/pg_restore ou DB injoignable | Versions et SELECT 1 avant toute interruption d’écriture | Test pg_restore indisponible : les cinq DB sont diagnostiquées |
| Accès aux 13 images | Pull pouvait échouer seulement sur le dernier composant | Inspection du cache épinglé ou du registre, sans pull ; aucune dépendance registre ajoutée si le cache est valide | Tests deux images indisponibles : 13 tentatives ; cache valide utilisable sans registre |
| Tag mutable et second téléchargement après backup | Vérification inutile du tag avant référence immutable, répétée après backup | RECETTE inspecte/cache/pull la référence épinglée seulement ; le digest reste exigé | Test cache : 13 inspections, aucun pull de tag ; PREPROD inchangée |
| Couverture documentaire de la sauvegarde | Le backup RECETTE existant archive les justificatifs Factures, pas les pièces jointes Contrats | Montage Contrats strictement préservé ; ne pas revendiquer une restauration documentaire globale ni inventer une copie de sécurité | Limite existante explicitée ; aucun volume Contrats détaché ou modifié |
| Backup réel / arrêt forcé / archive invalide / reprise KO | Ce sont des résultats d’exécution, pas des faits démontrables par lecture seule | Protections conservées ; lot incomplet conservé, reprise des writers, aucun restore implicite | 11 tests documents ; aucune exécution métier réelle ici |
| Migrations / disponibilité / Nginx après remplacement | Un résultat futur dépend des images, données, ressources et réseau | Contrôles d’exécution maintenus ; aucune protection neutralisée pour obtenir un GO | Tests ordre/échecs installateur ; pas d’attestation d’exécution VM |
| IA incomplète | Menu disponible ne signifie pas fournisseur configuré | Warning provider/modèle/clé ; aucun appel IA pendant diagnostic | Test rapport sans clé ni contenu secret ; parcours métier non certifié |
| PREPROD | Promotion exige décision humaine de la même cohorte, orchestration sécurisée, backups chiffrés et smoke | Aucun changement des Compose, gardes, migrations ou réservations PREPROD | Tests configuration/gardes PREPROD existants |

## Paramètres initiaux à connaître avant une prochaine installation autorisée

Le diagnostic liste une seule fois leurs défauts ; aucune nouvelle campagne
fonctionnelle n’est exigée à chaque release :

- Hostname exact, projet `wavy-recette`, daemon Unix système local et pas de réservation MSI.
- Mode `technical`, disponibilité PWA et écritures demandées, origine HTTPS exacte et CORS cohérent.
- Profils actuels préservés ; Socle `local` n’est pas transformé en `recette` pour satisfaire un validateur.
- Secrets DB et compte Tiers correspondant à l’existant ; ne pas les réinitialiser depuis un exemple.
- Nom réel du volume documentaire ; création initiale autorisée seulement s’il est absent, sinon aucun chown/réparation automatique.
- Proxy compatible avec le futur bind loopback, répertoires privés et capacité suffisante.

**Les valeurs de ces paramètres sur la VM restent inconnues ici.** Le diagnostic
MSI exécuté sur son dotenv local remonte ses propres défauts et sa réservation
locale, en une seule réponse ; il ne constitue pas un diagnostic distant.

## Validation et limites

**126 tests ciblés réussis** : diagnostic (18), installateur (17), images (6),
PWA (25), documents (11), CORS (3), configuration PREPROD (36), gardes PREPROD (10).
Historique versions/digests, syntaxe Bash et `git diff --check` passent également.

Les tests ciblés utilisent un vrai rendu Compose et de vrais dépôts Git temporaires,
avec runtime Docker/HTTPS simulé. Les tests de conservation comparent les octets
des configurations et historiques et vérifient l’absence de création de verrou.
Le probe documentaire est aussi exécuté localement sur une fixture privée à deux
modes incorrects, sans modification par le probe. Aucun conteneur métier, base,
volume ou document existant n’est démarré, arrêté ou modifié pendant cette revue.

La CI existante intègre la nouvelle suite de diagnostic. Les tests des composants
métier ne sont pas relancés puisqu’aucun code applicatif ni profil actif n’a changé.
Les 13 références et digests de release et les historiques demeurent inchangés.

Le diagnostic ne peut pas garantir à l’avance un arrêt gracieux, une sauvegarde
réellement réussie, une migration réelle ou la disponibilité après remplacement.
Il les indique explicitement comme contrôles d’exécution, en plus des prérequis
observés. Il ne transforme pas une inspection incomplète en autorisation de déployer.
La publication est autorisée ; tout contrôle sur VM ou toute reprise d’installation
reste soumis à votre accord préalable.
