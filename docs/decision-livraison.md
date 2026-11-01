# Décision de livraison Wavy — correctif ciblé

Le parcours reste **`./wavy install recette`, puis tests manuels dans Chrome**.
Aucun nouveau contrôle, orchestrateur ou campagne fonctionnelle n’est ajouté.
Les contrôles existants sont reclassés et leurs faux positifs corrigés. Ce
correctif est préparé localement ; aucun accès VM, publication ou déploiement
n’a été effectué.

Chaque ligne du diagnostic porte désormais une catégorie :

- **BLOQUANT** : la livraison ne peut pas être exécutée en sécurité ou correctement.
- **AVERTISSEMENT** : l’écart est explicite, sans empêcher une installation sûre.
- **INFORMATION** : état, action prévue ou vérification restant à faire.

Le code de sortie reste non nul uniquement pour les blocages. Un avertissement
ou une vérification ultérieure ne produit plus `INCOMPLET` / NO-GO. Le GO concerne
l’installation technique, jamais la validation fonctionnelle ou le HTTPS public
non observé. Une lecture impossible porte `evidence=NON_VERIFIE` ; elle ne prouve
pas une défaillance de l’application. Si cette lecture est indispensable à la
préservation des données (volumes, projet, images, backup), l’installation reste
bloquée pour absence de garantie, sans affirmer une panne applicative.

## Classement de tous les contrôles existants

| Contrôles existants | Catégorie / règle | Justification |
| --- | --- | --- |
| Arguments CLI, Python/outils, daemon local et capacités Compose | BLOQUANT si nécessaires et indisponibles | La commande ne pourrait pas installer / sauvegarder correctement |
| Hôte, projet, propriétaire des conteneurs, réservation MSI, verrous | BLOQUANT | Évite une mauvaise cible et les opérations concurrentes |
| Dotenv absent, syntaxe illisible, fichier non privé | BLOQUANT | Configuration inutilisable ou secrets exposés |
| Doublons dotenv identiques | AVERTISSEMENT | Aucune contradiction effective ; même valeur conservée |
| Doublons contradictoires, versions/digests machine remplaçant la release | BLOQUANT | Priorité ambiguë ou release non reproductible |
| Ancienne variable CORS Gateway inutilisée | AVERTISSEMENT | Elle n’est plus transmise ; le CORS effectivement rendu reste contrôlé |
| Git modifié sur scripts/Compose/manifestes actifs | BLOQUANT | Contenu de livraison non synchronisé ; historiques runtime exclus comme auparavant |
| Versions, digests, historique version/digest incompatibles | BLOQUANT | Mauvaise release ou image mutable/incompatible |
| Image épinglée disponible dans le cache | INFORMATION | Pas de téléchargement nécessaire ; aucun rebuild |
| Image ni vérifiable dans le cache ni disponible au registre | BLOQUANT, non vérifié si la lecture échoue | Aucun moyen démontré d’installer cette image ; pas une panne applicative prouvée |
| Socle et Tiers `local` déjà actifs | AVERTISSEMENT | Contrat historique conservé, aucune activation implicite de `secure` |
| Transition de profil, profil non couvert, Gateway incompatible | BLOQUANT | Évite un changement implicite des droits, du DDL ou du comportement |
| Déclarations PostgreSQL absentes / valeurs historiques dans le dotenv RECETTE | AVERTISSEMENT | Le rendu Compose, les métadonnées actives et la connexion DB existante font foi ; aucun secret injecté, modifié ou affiché |
| Secret candidat réellement vide, DB/compte/secret candidat différent de l’actif | BLOQUANT | La recréation serait incohérente avec les bases existantes ; aucun reset automatique |
| Compte interservices effectivement absent dans le rendu | BLOQUANT | Les appels applicatifs requis ne fonctionneraient pas correctement |
| CORS effectivement contradictoire, wildcard, origine ou paramètres HTTPS invalides | BLOQUANT | Risque de sécurité ou routes/cookies non fonctionnels |
| Paramètres PWA/Notes fermés pour le parcours demandé, mode incompatible | BLOQUANT pour l’installation PWA demandée | Le rendu n’installerait pas le fonctionnement demandé ; pas de qualification fonctionnelle ajoutée |
| Volume Factures absent/invalide, non durable, mauvais montage, bind/sous-chemin remplacé | BLOQUANT | Protection des justificatifs et absence de détachement / masquage |
| UID/GID, modes privés, liens, types documentaires, hiérarchie ou tailles invalides | BLOQUANT | Stockage privé et sauvegarde intègre non garantis |
| Premier volume absent, création initiale explicitement autorisée | INFORMATION | Provisionnement privé existant, aucun chown ou effacement d’un volume existant |
| Volume initial non vide / ancienne racine non vide ou lien symbolique | BLOQUANT | Aucune migration documentaire ou dissimulation de contenu implicite |
| Racine d’un volume non monté inaccessible depuis l’hôte | INFORMATION, non vérifié | Le probe de stockage existant devra conclure avant le backup ; aucun succès inventé |
| Entrée HTTP ERP Shell joignable par Caddy Windows | AVERTISSEMENT sur son filtrage réseau non observé | Cette entrée est nécessaire à la topologie ; elle n’est pas un port backend |
| Ports des API, bases, PWA et fronts internes exposés dans le candidat | BLOQUANT | Évite le contournement de Gateway et du Shell |
| Exposition backend actuelle corrigée par le candidat | INFORMATION | Les données et réseaux internes ne changent pas ; publications réservées à loopback |
| Origine CORS globale réellement observée sur une réponse publique | BLOQUANT | C’est une non-conformité de sécurité observée, pas une impossibilité de joindre Caddy |
| HTTPS public inaccessible depuis la VM, certificat / DNS / retour distant non concluant | AVERTISSEMENT, non vérifié | Caddy est sur Windows ; pas de `-k`, faux certificat ou attestation de réussite |
| Routes ERP/PWA, manifeste, service worker, CORS et refus de session via l’entrée HTTP VM | BLOQUANT si le contrôle interne échoue après installation | Même contrôle déjà existant, exécuté sur le chemin local réellement joignable |
| Front statique arrêté avant installation | INFORMATION | Il n’écrit aucune donnée et Compose le démarrera |
| DB ou writer nécessaire au backup arrêté, métadonnées inaccessibles | BLOQUANT | Le parcours de sauvegarde existant ne peut pas conclure en sécurité |
| Espace inférieur au seuil indicatif de 1 Gio | AVERTISSEMENT | Ce seuil n’est pas la preuve d’un disque plein ; pas de rejet arbitraire |
| Mesure de capacité inaccessible | AVERTISSEMENT, non vérifié | Aucune corruption ou saturation déduite d’un refus de statvfs |
| Disque réellement plein, répertoire de backup non inscriptible | BLOQUANT | Installation / sauvegarde impossible ou documents non inscriptibles |
| Outils backup/connexion DB indisponibles, arrêt forcé, dump/archivage/scellement/reprise en échec | BLOQUANT | Aucun remplacement sans sauvegarde réussie ; lots incomplets conservés |
| Couverture du backup RECETTE limitée aux cinq DB + justificatifs Factures | INFORMATION | Aucune restauration documentaire globale revendiquée ; montage Contrats conservé |
| Erreur de migration, image active différente, API non healthy, Nginx invalide | BLOQUANT | Installation réellement incorrecte, protections inchangées |
| Sauvegarde/migration/disponibilité futures non encore exécutées | INFORMATION | Leur résultat ne peut pas être attesté avant exécution |
| IA non entièrement configurée | AVERTISSEMENT | Aucun appel fournisseur ni déduction de réussite métier |
| Tests utilisateur HTTPS / authentification / PWA dans Chrome | INFORMATION après installation | Validation humaine existante, sans nouvelle campagne complète imposée |

## Corrections des faux positifs

1. **Tiers `local`** est accepté comme Socle `local`, avec avertissement et maintien
   de la comparaison candidat/actif. Aucun profil actif ni aucune image ne change.
2. **PostgreSQL** : une clé absente du dotenv ou un ancien mot de passe par défaut
   n’est plus déclaré « secret DB absent ». Si le rendu correspond aux conteneurs
   existants, l’installation est permise avec avertissement. Si le rendu diffère
   réellement de leurs secrets, le blocage reste indispensable. Le correctif ne
   récupère pas les secrets pour les réécrire dans les fichiers et ne les réinitialise pas.
3. **Caddy Windows** : le bind déjà configuré de l’entrée Shell est conservé ; son
   repli historique est joignable sur les interfaces VM. La variable existante
   `WAVY_RECETTE_PRIVATE_BIND_ADDRESS` ne pilote désormais que cette entrée.
   Les 17 autres publications restent fixées à loopback, même si cette variable
   vaut `0.0.0.0`. Un bind Shell explicitement configuré en loopback n’est pas
   élargi silencieusement : Caddy doit alors emprunter le chemin protégé qui le
   joint déjà. Aucun réglage Windows/Caddy/VirtualBox/firewall n’est modifié.
4. **Disponibilité** : les mêmes routes ERP/PWA et contrôles CORS/session sont
   vérifiés par HTTP à l’entrée Shell de la VM. Le CORS conserve l’origine HTTPS
   publique. Les observations HTTPS publiques sont des avertissements si elles
   échouent depuis la VM ; Chrome reste la preuve du parcours via Caddy.
5. **Stockage** : propriétaires, modes, persistance et conservation restent
   bloquants. Le seuil documentaire arbitraire de 1 Gio ne bloque plus un volume
   inscriptible ; un volume réellement plein reste refusé avant ouverture des écritures.

## PREPROD

La même distinction s’applique : contrôles internes pour l’installation, parcours
public via Caddy/Chrome pour l’utilisateur, aucune panne déduite d’une mesure non
réalisable. PREPROD utilise déjà des healthchecks et smoke tests internes Docker,
qui sont conservés, sans ajouter de qualification fonctionnelle complète.

Ses protections renforcées restent inchangées : Compose et profils `preprod,secure`,
secrets explicites/distincts requis par son rendu sans défauts historiques RECETTE,
cookie Secure selon son mode d’accès, entrée protégée/loopback et accès existant,
réservations/verrous, sauvegardes chiffrées et documents, migrations, restauration,
vérification OCI et décision humaine de promotion de la même cohorte. Ce correctif
n’ouvre aucun port PREPROD et ne remplace pas son orchestrateur sécurisé.

## Validation

**136 tests ciblés réussis** : diagnostic (28), installateur (17), images (6),
PWA (25), documents (11), CORS (3), configuration PREPROD (36), gardes PREPROD (10).
Historique versions/digests, syntaxe Bash et `git diff --check` passent également.

Les tests existants ont été adaptés au classement demandé. Les régressions
reproduisent Tiers `local`, les cinq clés DB omises avec valeurs actives
correspondantes, le secret réellement différent qui reste refusé, Caddy public
inaccessible avec routes locales valides, une route locale incorrecte qui reste
bloquante, le Shell externe avec backends privés, les doublons identiques et
contradictoires, la capacité non mesurable / faible / nulle et la conservation des
fichiers. Les conteneurs et HTTPS sont simulés ; les rendus Compose sont réels.
Aucun état VM ou succès fonctionnel distant n’est attesté.
