# Raccordement PWA PREPROD — bilan unique

4 novembre 2026. Correctif préparé et validé sur MSI ; publication autorisée par l’utilisateur. Aucun déploiement ni activation exécuté par Codex. La préparation ciblée du stockage et du dotenv sur PREPROD a été exécutée conformément au GO explicite de l’utilisateur.

## Cause et correction regroupée

La release PREPROD utilisait les bons digests mais pas les surcharges fonctionnelles PWA de RECETTE : le JSON désactivé inclus dans ERP Shell était servi sans montage persistant. Le stockage Notes n’était pas raccordé à Factures, le sous-répertoire `notes-frais` était absent, et le dotenv restait configuré pour HTTP localhost.

Le correctif réutilise le template Shell, le JSON d’intégration et la politique Nginx Notes de RECETTE. Seule la destination du proxy PWA devient `wavy-pwa-preprod`. Il est raccordé au wrapper Compose existant ; aucun nouvel orchestrateur, commande de livraison ou cycle de qualification n’est ajouté.

## Préparation PREPROD exécutée et vérifiée

- Répertoire `notes-frais` créé dans le volume documentaire PREPROD existant ; propriétaire `100:101`, mode `0700`. Aucun autre répertoire n’a été corrigé ou déplacé.
- Lecture du stockage vérifiée avec l’image Factures réellement installée, son utilisateur non root et un montage en lecture seule du seul sous-répertoire Notes. Aucun fichier de test métier créé.
- Sauvegarde privée du dotenv conservée sur PREPROD, hors Git, permissions 0600. Aucun secret transféré, affiché, remplacé ou publié.
- Exactement six paramètres préparés dans `.env.preprod` :

```dotenv
WAVY_ACCESS_MODE=https
WAVY_PUBLIC_URL=https://preprod.wavyservices.fr
WAVY_CORS_ALLOWED_ORIGIN_PATTERNS=https://preprod.wavyservices.fr
WAVY_COOKIE_SECURE=true
WAVY_PWA_ENABLED=true
WAVY_NOTES_WRITES_ENABLED=false
```

Les autres paramètres privés sont conservés. Le dotenv est validé par le validateur PREPROD existant. Ces valeurs sont **préparées pour la prochaine installation autorisée** : aucun service n’a été recréé pour les charger. Le JSON actuellement servi demeure `enabled=false`, conformément à l’absence d’activation.

Comparaisons avant/après confirmées : contenu et métadonnées des documents existants inchangés, versions/digests et historiques inchangés, état Git inchangé, mêmes images et dates de démarrage pour les treize composants. Aucune commande SQL, restauration, sauvegarde de release ou déploiement exécuté.

## Fonctionnement préparé

Quand `WAVY_PWA_ENABLED=true`, le wrapper Compose ajoute `docker-compose.preprod-pwa.yml`. ERP Shell monte en lecture seule ses quatre fichiers de configuration PWA et sert `/pwa/` sur la même origine HTTPS que l’ERP. Le lien reste soumis aux rôles `NOTE_DE_FRAIS` ou `SUPER_NOTE_DE_FRAIS` ; aucune permission applicative n’est accordée automatiquement.

Les écritures Notes restent désactivées : la politique Nginx refuse POST/PUT/PATCH/DELETE sur Notes et ses justificatifs. Le montage Factures expose uniquement `notes-frais` à `/app/justificatifs`, en lecture seule, sans copie initiale. Les documents Contrats ne sont pas exposés à Factures. L’activation des écritures n’est pas incluse dans ce correctif.

Les protections indispensables restent actives : API non publiées, sessions et rôles existants, CORS exact, cookies sécurisés et HttpOnly/SameSite Strict, montages limités aux chemins approuvés, verrou d’opération, sauvegarde coordonnée unique, chiffrement/signature PREPROD, migrations, santé, smoke et historiques. Le contrôle du stockage refuse un répertoire absent ou illisible ; il ne crée rien et ne corrige aucun droit pendant les livraisons.

Les différences restantes sont intentionnelles : RECETTE utilise un volume Notes dédié et autorise les écritures validées ; PREPROD réutilise son volume documentaire chiffré, avec isolation par sous-répertoire et lecture seule. Aucune donnée n’est migrée entre les deux environnements.

## Fichiers du correctif

- `.env.preprod.example` : deux commutateurs optionnels, fermés par défaut.
- `docker-compose.preprod-pwa.yml` et `docker/preprod-pwa/routes-open.conf` : raccordement persistant, références d’images inchangées.
- `scripts/preprod_config.py` : prise en compte des commutateurs, validation des montages précis et contrôle du stockage en lecture seule.
- `scripts/_preprod.sh` et `scripts/delivery-preflight.sh` : inclusion de ces fichiers dans les protections Git et le parcours existant.
- `scripts/test-preprod-config.py` et `scripts/test-preprod-backup-transition.py` : tests du raccordement et du parcours de livraison existant.
- Ce bilan. Les autres travaux locaux Anthropic/Windows restent exclus.

## Procédure unique après accord de publication et d’installation

Sur PREPROD, après publication autorisée du correctif :

```bash
git pull --ff-only
./wavy install preprod
```

Le dotenv et le répertoire sont déjà préparés ; aucune édition supplémentaire n’est prévue. La commande conserve le moteur commun : précontrôles, un seul lot coordonné des cinq bases/documents, puis les treize cibles dans l’ordre. Aucun build, changement de digest, script candidat historique ou commande spéciale PWA n’est nécessaire. Aucune restauration automatique.

Après cette installation autorisée, vérifier dans le navigateur le JSON activé, le lien PWA avec un compte autorisé, les lectures Notes/justificatifs et le maintien du refus des écritures. La séparation réelle entre deux tenants/sociétés nécessite des sessions autorisées ; les réponses 401 observées sans session ne la prouvent pas. Aucun test métier créateur n’est exécuté pendant la préparation.

Après validation fonctionnelle PREPROD, figer les scripts de livraison RECETTE/PREPROD. Les modifier seulement pour un défaut démontré, avec son test de non-régression ; conserver cette procédure unique. Aucun déploiement PRODUCTION n’est activé.

## État de validation

La validation complète du candidat est exécutée dans une copie Git temporaire, excluant les travaux locaux non concernés. Les tests utilisent les mêmes scripts de livraison avec services simulés ; Nginx est également testé dans un conteneur local jetable sans données métier. **172 tests Python réussis**, dont Nginx réel isolé, configuration PREPROD et cycle complet des treize composants avec sauvegarde unique, interruption et reprise. Les tests d’historique version/digest, la syntaxe Bash de tous les scripts et `git diff --check` sont conformes. Aucun contrôle supplémentaire n’a été ajouté après cette validation.

Aucun blocage technique de stockage n’est encore identifié après la préparation et la lecture réelle réussie. La validation fonctionnelle de la PWA active attend volontairement le déploiement autorisé. Une sonde HTTPS depuis le terminal a précédemment rencontré une erreur TLS pour les deux environnements ; elle ne démontre pas une panne PREPROD et ne remplace pas la vérification dans le navigateur habituel.
