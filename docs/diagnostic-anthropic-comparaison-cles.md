# Diagnostic ciblé Anthropic — comparaison sans divulgation

Diagnostic préparé puis autorisé à la publication le 2 novembre 2026. Aucun accès aux VMs, appel Anthropic, changement de clé, modification applicative ou déploiement. La publication concerne uniquement les deux scripts de diagnostic/tests et cette documentation. Les fichiers de configuration, images, données et protections ne sont pas modifiés. Seuls le script de diagnostic, ses tests et ce compte rendu sont préparés dans DevOps.

## Constats sur MSI et limites

Le contrôle MSI expurgé a été exécuté sur le conteneur local actif ; le relevé détaillé reste local et ne fait pas partie de la publication. La clé de l'environnement du processus Java PID 1 est identique à celle de la définition Docker et à celle du rendu Compose employé par l'installateur. Un seul emplacement de définition est détecté dans le dotenv. Aucun espace, CR/LF, caractère invisible, caractère non ASCII, guillemet parasite ou interpolation non résolue n'est détecté. Aucun override Spring/configuration externe ou indice de proxy JVM n'est détecté.

Le JAR actif contient les constantes du client relu : endpoint `https://api.anthropic.com/v1/messages`, en-tête `x-api-key`, `anthropic-version: 2023-06-01`. Le client passe la propriété `apiKey` directement à l'en-tête ; le setter ne corrige ni ne normalise la clé. Le corps est JSON. Cela vérifie le contrat du client et les constantes du JAR, pas les octets d'une requête interceptée sur le réseau.

L'en-tête `x-api-key` reste accepté par Anthropic ; il n'y a pas de justification établie pour le remplacer. La documentation distingue HTTP 401 (authentification : clé incorrecte, altérée, révoquée ou expirée) de HTTP 403 (permissions). Un 401 ne démontre pas un problème de modèle. Sources officielles consultées : [authentification](https://platform.claude.com/docs/en/manage-claude/authentication), [erreurs](https://platform.claude.com/docs/en/api/errors), [versions](https://platform.claude.com/docs/en/api/versioning).

**L'égalité des clés MSI/RECETTE n'est pas encore vérifiée.** Les informations transmises sur RECETTE prouvent la cohérence entre son rendu Docker et son conteneur, pas l'identité de sa clé avec celle de MSI. Aucun diagnostic n'a été exécuté sur RECETTE ou PREPROD par l'agent.

## Outil préparé

`python3 -B scripts/diagnose-anthropic-key.py --environment msi`

Le même script accepte `recette` et `preprod`, mais doit toujours être exécuté par l'opérateur sur la machine concernée. Il refuse les contextes Docker distants. Il ne démarre aucun conteneur ou VM et ne fait aucun appel fournisseur.

Il confirme que PID 1 est Java puis lit seulement : contexte Docker, définition du conteneur Factures, `/proc/1/environ`, la classe du client dans le JAR actif, les métadonnées de syntaxe du dotenv et le rendu Compose existant. Aucun dump Docker, environnement brut ou corps de réponse fournisseur n'est imprimé. Le rendu de l'installateur utilise les fonctions existantes ; son éventuel fichier intermédiaire non secret est temporaire et supprimé, aucun fichier machine n'est réécrit.

Le JSON contient uniquement les identités provider/modèle reconnues, l'identifiant de l'image, des booléens d'égalité et de présence, les anomalies de caractères et les indices de configuration réseau. Aucun extrait de clé, longueur, empreinte stable ou preuve HMAC n'y figure. La lecture de l'environnement du processus vérifie les octets hérités par Java ; ce n'est pas une introspection du bean Spring résolu. Les éventuelles surcharges sont signalées pour éviter cette confusion.

## Comparer les deux clés avec l'opérateur

Utiliser deux terminaux interactifs non enregistrés. Ne pas faire cette comparaison via le chat ou un journal de session. Depuis le checkout DevOps à jour sur chaque machine, utiliser les commandes suivantes. Si une synchronisation est nécessaire, `git pull --ff-only` ne met à jour que le dépôt ; ne lancer aucun installateur. Ne transférer aucun fichier `.env`, clé ou configuration MSI.

1. Sur MSI, lancer :

   ```sh
   python3 -B scripts/diagnose-anthropic-key.py --environment msi --compare
   ```

   Le programme affiche un défi aléatoire **public** et attend une preuve en saisie masquée.

2. Dans le terminal de RECETTE ouvert par l'opérateur, depuis le checkout DevOps, lancer avec le défi donné par MSI :

   ```sh
   read -r -p 'Défi public affiché sur MSI : ' WAVY_AI_DIAG_CHALLENGE
   python3 -B scripts/diagnose-anthropic-key.py --environment recette --challenge "$WAVY_AI_DIAG_CHALLENGE"
   unset WAVY_AI_DIAG_CHALLENGE
   ```

   Le script affiche une preuve HMAC dans un écran temporaire séparé. La clé ne quitte pas la mémoire du processus de diagnostic de cette machine. La preuve n'est envoyée ni dans stdout ni dans le JSON.

3. Transférer uniquement cette preuve temporaire dans la saisie masquée du terminal MSI. Elle ne passe pas par un argument shell, l'historique des commandes ou un fichier. Ne pas la coller dans le chat, un ticket ou un rapport. Éviter tout terminal ou presse-papiers enregistré/synchronisé.

4. Après transfert, appuyer sur Entrée sur RECETTE pour effacer l'écran temporaire. MSI affiche uniquement **Clés identiques** ou **Clés différentes**. RECETTE ne produit aucun résultat ni preuve dans stdout. Ne conserver que cette conclusion. Recommencer avec un nouveau défi si la comparaison est interrompue.

Le mécanisme compare les octets UTF-8 exacts, sans `strip`, correction d'espaces ou normalisation Unicode. HMAC-SHA256 est calculé avec la clé locale sur un défi aléatoire unique de 256 bits, avec un domaine propre à ce diagnostic. Il n'exporte jamais un hash stable de la clé. Le script ne sauvegarde ni défi, ni preuve, ni empreinte. La saisie échoue si l'écho du terminal ne peut pas être désactivé ; aucun repli vers une saisie visible.

Pour éviter même de créer un fichier de diagnostic sur la VM, l'opérateur peut, depuis la racine du checkout DevOps, utiliser `python3 -B - --environment recette --challenge DEFI_PUBLIC`, fournir le contenu du script sur l'entrée standard et terminer cette entrée par EOF. Le script reconnaît cette forme et utilise le checkout courant. Cela ne change ni l'application ni sa configuration.

Le même mécanisme peut être réutilisé par l'opérateur sur PREPROD après son démarrage volontaire, avec `--environment preprod`. Aucune clé RECETTE/MSI n'y est copiée. L'arrêt actuel de PREPROD n'est pas un défaut à corriger par ce diagnostic.

## Interpréter sans modifier

| Observation | Conclusion permise | Vérification suivante, sans correction automatique |
|---|---|---|
| `keyHygiene` signale espaces, CR/LF, caractères invisibles ou guillemets | La valeur effective contient ces caractères | Localiser leur présence dans la configuration prévue ; ne pas nettoyer/remplacer la valeur sans accord |
| `dockerConfigEqualsProcessKey: false` | L'environnement du processus diffère de la définition Docker | Examiner l'entrée de démarrage et les surcharges ; ne pas redémarrer automatiquement |
| `intendedConfiguration.sameKeyAsProcess: false` | La clé actuellement utilisée ne correspond pas au rendu du dotenv actuel | Vérifier fichier machine, date d'installation et conteneur ; aucune réinstallation lancée |
| Comparaison MSI/RECETTE `false` | Les clés effectives sont distinctes ; le succès MSI ne qualifie pas la clé RECETTE | Vérifier en lecture seule dans la Console Anthropic le statut de la clé destinée à RECETTE ; des clés distinctes par environnement peuvent être intentionnelles |
| Comparaison `true`, hygiène correcte, aucun override, mais HTTP 401 | La différence de valeur de clé seule n'explique pas le refus observé | Vérifier la contemporanéité des essais, révocation/expiration côté fournisseur et chemin réseau/proxy ; ne pas attribuer l'échec au modèle sans preuve |

Une clé obsolète par rapport au dotenv courant est détectable par comparaison. Une clé révoquée/expirée côté Anthropic n'est pas identifiable hors ligne à partir de ses caractères ou de son empreinte. Un succès MSI antérieur ne garantit pas sa validité au moment de l'essai distant. La Console et/ou une observation fournisseur contemporaine restent nécessaires pour conclure dans ce dernier cas ; le diagnostic préparé ne les invente pas.

## Tests et état des dépôts

11 tests dédiés réussis : égalité exacte, différences d'espaces et retours à la ligne, invisibles Unicode, normalisation de la sérialisation Compose sans modification de clé, détection de doublons, valeur active obsolète, refus de Docker distant, erreurs expurgées et absence de preuve dans stdout/JSON. Un essai en pseudo-terminal réel avec une clé de fixture confirme la comparaison complète et l'absence d'écho de la preuve. Les 6 tests du diagnostic Factures existant et les 7 tests de rendu/transmission passent également.

Factures API et Factures Front sont inchangés et propres. Aucun correctif applicatif supplémentaire, aucune image ou nouvelle procédure de livraison ne fait partie de cette publication du diagnostic.
