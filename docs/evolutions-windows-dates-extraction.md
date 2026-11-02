# Évolutions Windows, recherches par date et extraction à montant unique

Préparation locale initiale sur MSI, suivie de la publication autorisée le 2 novembre 2026. Voir le [bilan de publication](publication-windows-dates-extraction-2026-11-02.md) pour les commits, digests et réserves. Aucun déploiement ni modification des données RECETTE/PREPROD.

## Dépôts concernés

| Dépôt | Correction |
| --- | --- |
| `wavy-devops` | Superviseur Windows, tâche d'ouverture de session, commandes de contrôle et documentation |
| `wavy-factures-front` | Dates par défaut, mémorisation, dashboard financier ; propositions et confirmation des montants achats/ventes |
| `wavy-factures-api` | Règle commune aux normalisations achats/ventes, instructions IA, consommation à la création, maintien du contrôle humain si TVA indéterminée |
| `wavy-tresorerie-front` | Dates et mémorisation des filtres d'échéances |
| `wavy-pwa` | Même repli de création achat/vente et confirmation explicite de la TVA provisoire |

Les autres modules inspectés n'exposent pas de recherche avec filtres par date. Les dates des contrats, rattachements, budgets, générations d'abonnements, documents et notes de frais sont des données métier : elles sont conservées. Les KPI mensuels de l'accueil ERP Shell restent explicitement mensuels, sans filtre de recherche utilisateur. Aucun changement de dépôt Gateway/Socle/Tiers/Contrats ou API Trésorerie n'est nécessaire.

## Windows

Voir [les commandes et limites](../windows/README.md). Le Caddyfile et les connexions existants sont réutilisés. La tâche utilisateur `Wavy-Connections` est installée et le superviseur est actif. Le démarrage, l'arrêt et la réinstallation ont été exercés sur MSI ; Caddy et le tunnel RECETTE préexistants ont été conservés.

La vérification locale de configuration PREPROD a précédé toute modification : 36 tests de configuration et 10 tests de gardes. Les vrais secrets de la VM n'ont pas été lus. Le Caddyfile actif a été validé, sans modification.

Observation HTTPS Windows : RECETTE **200** ; PREPROD **502**, son point SSH existant `localhost:2223` refuse la connexion et son relais `24443` est absent. Le superviseur retente sans commande distante. Le service `ssh-agent` était désactivé ; si la clé existante est chiffrée, son déverrouillage dans l'agent par l'utilisateur reste requis. Aucune passphrase ni clé privée n'est ajoutée aux fichiers préparés.

## Dates de recherche

Les listes achats/ventes et le dashboard réutilisent `CrudListStateService`. Les valeurs vides des dates restent dans l'URL et le stockage de session, afin qu'un effacement volontaire ne soit pas remplacé au retour par la valeur par défaut. La politique de dates est centralisée dans `shared/filters/date-search.ts` pour les écrans Factures ; Trésorerie possède son propre utilitaire partagé dans son application indépendante.

À la première visite ou après réinitialisation : début au **1er janvier de l'année civile locale**, fin **vide**. Aucun calcul UTC de minuit, aucune fin d'année implicite. Un choix explicite est conservé au retour, y compris après changement d'année dans la même session. Sans choix mémorisé, une nouvelle année donne son nouveau 1er janvier.

Les API utilisent déjà des bornes optionnelles. Les tests de recherche enregistrent des factures de 2032 dans PostgreSQL de test et vérifient leur présence sans date de fin, puis leur exclusion avec une date de fin explicite. Aucune borne serveur n'est ajoutée.

## Montant unique

`MontantGlobalFacture` porte la règle commune Java, utilisée par les normalisations achats et ventes et le repli de création achat. Les consommateurs frontend utilisent un utilitaire commun achats/ventes dans chaque application ; la PWA et Factures restent des dépôts indépendants, sans nouveau package ou dépendance de build entre dépôts.

Sans ligne métier : une ligne de quantité 1 est proposée. Un montant TTC global seul donne le même HT par défaut et zéro TVA **provisoire**, avec avertissement et confirmation explicite. Il n'est pas qualifié d'exonéré. Un HT, un montant de TVA ou un taux explicite prévaut ; les contradictions entre totaux restent signalées. Une ligne déjà présente avec TTC seul est complétée plutôt que doublée. Plusieurs lignes existantes ne déclenchent pas de ligne globale supplémentaire.

Les instructions IA demandent de conserver les montants non explicités à `null`, sans fabriquer une ventilation fiscale. La normalisation et les convertisseurs appliquent ensuite la règle sans dépendre du fournisseur IA. Une extraction à montant global nécessitant confirmation ne peut pas créer/valider automatiquement une facture d'achat, même avec un score IA élevé. Les parcours achats simples, lots et ventes conservent leur création modifiable et leurs validations existantes.

La pièce source et son empreinte restent conservées. La provenance des montants et de la proposition est conservée dans la description de la ligne proposée, en réutilisant le stockage existant ; la création ajoute les valeurs finales confirmées pour permettre la relecture des corrections. Ce mécanisme n'ajoute pas un journal d'audit immuable. Aucune migration de schéma n'est nécessaire.

Le cas « LOYER WAVY IMMO mai 26.pdf » est couvert par une fixture : référence `LOY-2026-005`, date `2026-05-05`, désignation « Loyer mensuel — mai 2026 », quantité 1, PU HT/total HT/TTC 3000, TVA provisoire zéro. Ces données ne sont pas déduites du seul nom de fichier. Aucun document réel ni appel au fournisseur IA n'a été nécessaire aux tests.

## Livraison ultérieure

La publication des seuls composants applicatifs concernés (`factures-api`, `factures-front`, `tresorerie-front`, `pwa`) est désormais autorisée et réalisée ; le bilan lié ci-dessus fait foi pour la release publiée. Les résultats ci-dessous décrivent la préparation initiale.

Le parcours reste celui déjà validé : publication autorisée des images, synchronisation de la release, **`./wavy install recette`**, tests manuels Chrome ERP/PWA, puis décision humaine de promotion de la même cohorte vers PREPROD. Aucun nouveau critère de qualification ou orchestrateur de livraison n'est ajouté. Les contrôles de sécurité, données, stockage, sauvegarde et migrations restent en place.

## Résultats de validation

- API Factures : **278 tests réussis**, zéro erreur/échec/skip. Commande : `./mvnw -q -Dspring.test.context.cache.maxSize=4 test`. La limite de cache est réservée à la JVM de test, pour éviter l'accumulation des pools Spring dans PostgreSQL Testcontainers local ; le pool normal est conservé pour le test de concurrence. Aucun fichier de configuration applicative n'a changé pour cette adaptation.
- Factures Front : **173 tests réussis** (`npm test -- --watch=false`).
- Trésorerie Front : **15 tests réussis** (même commande).
- Mobile PWA : **58 tests réussis** (même commande).
- Livraison DevOps : **136 tests réussis** : diagnostic 28, installateur 17, images 6, PWA 25, documents 11, CORS 3, configuration PREPROD 36, gardes PREPROD 10.
- Windows : **17 assertions locales réussies**, sans SSH/Caddy réel dans les tests ; installation et cycle démarrage/arrêt exercés séparément. Une seule instance du superviseur observée. Le lanceur installé `check` confirme RECETTE 200 et PREPROD 502, avec code de sortie 1 comme attendu pour ce dernier état.
- `git diff --check` passe dans les cinq dépôts. Scan des fichiers préparés et revue des valeurs sensibles : aucun secret détecté. Le fichier Windows de configuration locale est ignoré par Git.
- Manifestes, 13 digests RECETTE/PREPROD, historiques : identiques à HEAD. Aucune image applicative construite/publiée, aucune migration sur les VMs et aucun déploiement.

Les tests API utilisent PostgreSQL Testcontainers isolé sur MSI ; les appels IA et référentiels externes sont simulés. Les tests Angular compilent les vues et vérifient les comportements et requêtes HTTP ; aucun test manuel Chrome sur une nouvelle image distante n'est revendiqué. La disponibilité future du tunnel PREPROD et l'ouverture de session suivante restent à confirmer avec le point SSH disponible.
