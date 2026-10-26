# Préparation de publication Wavy — MSI, 26 octobre 2026

Aucun commit, push Git, push GHCR ni déploiement effectué. Les index habituels et les services MSI restent intacts. Les lots sont préparés dans des index séparés et des copies filtrées. Les images de validation sont locales, marquées avec un arbre source Git et `validation.only=true` : elles ne portent pas de faux SHA de commit de release.

## Résultats exécutés

| Contrôle | Résultat |
|---|---|
| Fronts : Shell / PWA / Tiers / Contrats / Factures / Trésorerie | 22 / 55 / 52 / 88 / 163 / 12 tests réussis (392) |
| Gateway | 42 tests réussis |
| API Factures, justificatifs | 5 tests réussis sur PostgreSQL Testcontainers isolé |
| DevOps sur copie publique filtrée | 130 tests réussis ; 8 contrôles d’historique et syntaxe Bash validés |
| Navigation/import/IA sur fichiers extraits des nouvelles images | 4 scénarios réussis, API simulées, aucun appel fournisseur |
| Docker | 6 constructions linux/amd64 réussies ; Nginx et HTTP vérifiés sans réseau ni port publié |
| Images réemployées | 7 manifestes GHCR consultables par digest exact, sans publication |

Les 247 validations d’isolation historiques restent conservées, sans nouvelle exécution ni attestation PREPROD. Les validations HTTPS/Chrome/layout antérieures restent des preuves locales privées ; elles ne sont pas ajoutées aux commits.

## Lots de commits proposés

Un commit source par dépôt modifié, puis un commit DevOps distinct pour les versions finales après publication. La version fonctionnelle proposée pour les six fronts reconstruits est **0.2.0**. Les versions définitives comporteront les vrais SHA des commits approuvés.

### wavy-devops

Base : `e965e1d0ff01fab4f3e797dac349e4e9f2ba0c9d` ; branche : `master`.

Message : `feat(devops): unifie le cycle HTTPS local et le menu interactif`.

- `.gitignore`
- `docs/wavy-local.md`
- `docs/wavy-menu.md`
- `preparation/https-msi/Caddyfile.candidate`
- `preparation/https-msi/Caddyfile.local-only.candidate`
- `preparation/https-msi/INSTALLATION.txt`
- `preparation/https-msi/WAVY-LOCAL-CYCLE.txt`
- `preparation/https-msi/check_caddy_adapter.py`
- `preparation/https-msi/chrome-bundle-diagnostic.cjs`
- `preparation/https-msi/chrome-diagnostics.cjs`
- `preparation/https-msi/chrome-navigation.cjs`
- `preparation/https-msi/chrome-notes.cjs`
- `preparation/https-msi/chrome-probe.cjs`
- `preparation/https-msi/functional_preflight.py`
- `preparation/https-msi/local_auth.py`
- `preparation/https-msi/local_functional.py`
- `preparation/https-msi/prepare-functional-fixtures.cjs`
- `preparation/https-msi/test-chrome-diagnostics.cjs`
- `preparation/https-msi/test_https_msi.py`
- `preparation/https-msi/test_local_auth.py`
- `preparation/https-msi/test_manual_session.py`
- `preparation/https-msi/test_nginx_runtime.py`
- `preparation/https-msi/test_session_challenge_runtime.py`
- `preparation/https-msi/wavy_deploy.py`
- `scripts/test-wavy-local.py`
- `scripts/test-wavy-menu.py`
- `scripts/wavy-deploy.sh`
- `wavy`

- `preparation/publication-candidate/COMMANDES-APRES-ACCORD.txt`
- `preparation/publication-candidate/RAPPORT.md`
- `preparation/publication-candidate/cohort-candidate.json`
- `preparation/publication-candidate/inventaire.json`
- `preparation/publication-candidate/release-plan.json.template`
- `preparation/publication-candidate/versions/preprod.digests.template`
- `preparation/publication-candidate/versions/preprod.env.template`
- `preparation/publication-candidate/versions/recette.digests.template`
- `preparation/publication-candidate/versions/recette.env.template`

### wavy-erp-shell

Base : `0cfb699d6c6b2f81e70af938ecabb93bcc696068` ; branche : `master`.

Message : `feat(shell): integre Mobile PWA et remplit la zone de travail`.

- `e2e/pwa-notes-frais.local.spec.ts`
- `src/app/app.html`
- `src/app/app.scss`
- `src/app/app.ts`
- `src/app/core/pwa-integration.service.ts`
- `src/app/core/wavy-context.service.ts`
- `src/app/navigation.spec.ts`
- `src/styles.scss`

### wavy-pwa

Base : `6944c31eaa1b970a73092e885bd5280f88efead3` ; branche : `main`.

Message : `fix(pwa): adapte le layout integre et isole le service worker`.

- `ngsw-config.json`
- `src/app/app.config.ts`
- `src/app/app.css`
- `src/app/app.html`
- `src/app/app.ts`
- `src/styles.css`

### wavy-tiers-front

Base : `527527b96522153f0da74de4d8b1b5d0f0da9032` ; branche : `master`.

Message : `fix(layout): transmet la surface disponible au module tiers`.

- `src/app/app.scss`
- `src/styles.scss`

### wavy-contrats-front

Base : `9af670cd01a017a43dbd8a221638799feaaf537d` ; branche : `master`.

Message : `fix(layout): transmet la surface disponible au module contrats`.

- `src/app/app.scss`
- `src/environments/environment.preprod.ts`
- `src/styles.scss`

### wavy-factures-front

Base : `a201858b251f271c2294b83ee1e953cecdf1acfd` ; branche : `master`.

Message : `fix(layout): remplit la zone de travail factures`.

- `src/app/app.css`
- `src/environments/environment.preprod.ts`
- `src/styles.css`

### wavy-tresorerie-front

Base : `4bda80b8eaa464fd369cef14372abe288f2e6a0a` ; branche : `master`.

Message : `fix(layout): remplit la surface du module tresorerie`.

- `src/app/app.scss`
- `src/app/features/tresorerie/pages/tresorerie.page.css`
- `src/styles.scss`

### wavy-gateway

Base : `98e2ced416d33009c7d92f4c9fa3aa5838c62760` ; branche : `master`.

Message : `test(gateway): verifie CORS HTTPS et les entetes du proxy`.

- `src/test/java/fr/wavy/gateway/ActuatorRecetteTest.java`
- `src/test/java/fr/wavy/gateway/HttpsProxyRecetteTest.java`

Les fichiers `environment.preprod.ts` des fronts Contrats et Factures sont des sources publiques sans secret ; ils sont inclus explicitement, sans ajouter de configuration Angular ni changer leur usage. Les modifications Gateway concernent uniquement les tests : aucune reconstruction de son image n’est nécessaire.

## API et cohortes

Les cinq API ne contiennent aucune modification non commitée. Socle API et Contrats API ont néanmoins un HEAD plus récent que l’image MSI. La cohorte candidate conserve les images réellement testées au lieu de reconstruire aveuglément ces HEAD. Leurs versions/digests exacts sont consignés dans `cohort-candidate.json`. L’API Factures testée est déjà commitée (`09fcd98`) avec son image de justificatifs.

Les manifestes actifs RECETTE et PREPROD sont différents. Les candidats créés ici tirent les **13 digests d’une même cohorte** ; les fichiers `.digests.template` sont byte-identiques. Les URL/CORS restent propres à chaque environnement. Les six digests des fronts restent explicitement `PENDING_…` jusqu’aux commits et à la publication autorisés. Ce ne sont pas des manifestes installables. Un identifiant local Docker (`imageId`) est fourni comme preuve de build, jamais comme digest GHCR.

Le fichier `release-plan.json.template` prépare également la mise à jour du plan PWA existant, qui surcharge certains pins du moteur. Il doit être matérialisé avec les mêmes références ; ne pas mettre à jour seulement `versions/*.digests`.

## Exclusions et intégrité

Les caches Python, `.env` réels, fichiers `*.private.*`, comptes/cookies, dossiers de session, sauvegardes et preuves privées sont exclus. Les listes d’ajout sont explicites : aucun `git add .`. Aucun secret structuré n’a été détecté dans les copies candidates filtrées ; cela ne transforme pas les dépôts annexes en lots approuvés.

Hors lot ERP : `wavy-launchpad` (dont un `.env` suivi et modifié), `wavy-services-fr`, les worktrees de build historiques, `wavyfintalent` et `wavyflow-suite` non utilisés par la cohorte. Leurs modifications ne sont ni ajoutées, ni effacées, ni publiées. L’inventaire privé conserve les listes de chemins, sans exposer les valeurs des secrets.

## Séquence après accord

1. Vérifier les listes et les arbres sources, créer les huit commits proposés et pousser les branches convenues.
2. Utiliser `scripts/build-image.sh <front> 0.2.0 --push` sur MSI, après commits propres et fourniture sécurisée des identifiants GHCR. Le garde « arbre propre » reste intact. Ces builds de release porteront les vrais SHA.
3. Relever les six digests effectivement publiés, vérifier leurs labels, puis renseigner une seule cohorte définitive. Conserver les sept digests réemployés qui ont été vérifiés.
4. Matérialiser les deux ensembles de versions depuis cette cohorte, comparer les 13 pins RECETTE/PREPROD et le plan PWA, puis préparer le commit DevOps de versions. Ne jamais reconstruire sur les VMs.
5. Qualifier ultérieurement la configuration HTTPS et la compatibilité schéma/données sur les cibles avant toute installation. La préparation actuelle ne vaut pas GO de déploiement.

## Verdict

**GO POUR COMMIT/PUSH ET PUBLICATION GHCR**, pour les huit lots listés et le pipeline de release ci-dessus. Aucun de ces actes n’est exécuté avant accord. Les nouveaux digests définitifs ne peuvent pas être annoncés avant les commits et la publication ; les candidats restent bloquants tant qu’ils ne sont pas résolus. **Aucun GO de déploiement VM** : état et schémas distants non consultés.
