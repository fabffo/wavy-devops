# Validation réelle Factures sur MSI — 2 novembre 2026

**GO pour le fonctionnement local testé.** À la clôture de cette validation, aucun commit, push, publication d'image ou déploiement distant n'avait été effectué. Le relevé JSON conserve cet état de preuve antérieur à la publication. Les services nécessaires restent démarrés sur https://recettelocal.wavyservices.fr. La publication reste soumise à l'accord utilisateur.

## Sources effectivement utilisées

Le démarrage a été effectué par le même cycle existant :

```sh
./wavy local up factures --build-frontends --build-apis
```

L'option locale `--build-apis` complète les montages de fronts existants pour compiler et monter le JAR Factures API non publié. Les prochains `local up` conservent ces artefacts ; refaire les options de build après modification des sources. Aucun nouveau parcours de livraison : la suite distante reste publication autorisée, puis `./wavy install recette`.

- Factures Front : build compilé depuis les sources corrigées et monté en lecture seule sur `/usr/share/nginx/html`. Les cas d'URL partielle réussis dans Chrome exercent la correction exécutée, pas seulement les sources.
- Factures API : JAR corrigé monté en lecture seule sur `/app/app.jar`, utilisé par `java -jar /app/app.jar`. SHA256 hôte et conteneur identiques : `bdd49f6ceb58bcb11336cba7556a135c952b5eb9c8ef4ca5141ae21d4f297c65`. Empreinte des sources identique à celle relevée lors de la compilation.
- Les images de base restent celles du mécanisme local ; leurs labels ne décrivent pas le JAR ou les fichiers statiques montés. Aucun tag ni digest de livraison n'est remplacé pour ces tests.
- Création automatique achat désactivée ; schéma existant validé, Flyway et initialisation SQL désactivés pour le JAR local.

Deux défauts du démarrage local ont été corrigés dans le mécanisme existant : chargement du fichier de digests requis par Compose et préservation des blocs Caddy distants actuels au lieu de leur comparer un ancien modèle. Les blocs RECETTE/PREPROD sont conservés octet pour octet lors de la construction du candidat local. Aucun fichier de protection PREPROD ni manifeste version/digest n'est modifié.

## Tests Chrome réels

Chrome Windows `156.0.8078.73`, fenêtre isolée, connexion au compte de test existant, HTTPS avec validation TLS. Aucune réponse API simulée. Les paramètres du navigateur personnel de l'utilisateur sont conservés.

| Contrôle | Résultat |
|---|---|
| Première ouverture sans filtre | Début `2026-01-01`, fin vide |
| Dates explicitement choisies | `2025-03-01` à `2028-05-01` conservées après navigation |
| URL partielle avec seulement une nouvelle fin | Début mémorisé conservé, nouvelle fin appliquée |
| URL avec seulement `returnUrl` | Dates choisies conservées |
| URL avec `dateFin=` | Fin effacée, début conservé |
| Anciennes dates signalées sur RECETTE | Conservées tant qu'elles sont explicites dans l'URL |
| Réinitialisation | Début `2026-01-01`, fin vide ; requête HTTP réelle sans `dateFin` |
| Navigation après réinitialisation | Nouveaux défauts conservés |

## Extraction réelle du loyer

Le fichier original `LOYER WAVY IMMO janvier 26.pdf`, retrouvé dans OneDrive professionnel, a été lu sans modification. Son texte contient « Montant : 3000,00 € TTC », sans ventilation fiscale. L'appel réel a utilisé la configuration MSI existante : Anthropic / `claude-sonnet-4-5-20250929`. Clé présente et identique au dotenv MSI ; aucune valeur de clé affichée ou modifiée.

Le premier appel réel a exposé un défaut jusque-là non couvert dans le parcours de prévisualisation achats : ce parcours utilisait un prompt distinct avec des exemples à zéro et remplaçait les valeurs absentes avant la normalisation commune. Il retournait HT 0 / TTC 3000, sans avertissement de TVA inconnue. Ce n'était pas un refus de clé ou de modèle.

Correctif appliqué : montants absents conservés à null dans le prompt et le convertisseur de prévisualisation, utilisation de la règle commune pour la proposition globale et la confirmation TVA. Une contradiction explicite entre totaux reste bloquante ; un taux explicite reste prioritaire. Trois nouveaux tests couvrent ces cas.

Le nouvel appel réel depuis Chrome retourne HTTP 200 et :

| Élément | Valeur |
|---|---|
| Nombre de propositions / lignes | 1 / 1 |
| Quantité | 1 |
| PU HT / total HT / total TTC | 3 000 € / 3 000 € / 3 000 € |
| TVA | 0 € provisoire, **inconnue à confirmer** |
| Confirmation | Case présente et non cochée |
| Création | Bouton désactivé ; aucune requête de création émise |

L'interface affiche les avertissements `LIGNE_MONTANT_GLOBAL` et `TVA_NON_DETERMINEE`. Le fournisseur n'étant pas rapproché automatiquement dans ce contexte, `FOURNISSEUR_NON_RAPPROCHE` reste également à confirmer. Aucune règle fournisseur, fiche ou facture n'a été créée pour contourner ce contrôle.

Deux appels IA réels ont été nécessaires : constat initial, puis validation du correctif. Les contrôles de dates n'ont pas appelé l'IA. Le test navigateur refuse les autres mutations métier ; aucune tentative de création n'a été observée. La confirmation ou l'enregistrement final de la facture n'a pas été testé, conformément au périmètre utilisateur.

## Données et non-régression

- **20 contrôles Chrome réels réussis** ; aucune facture enregistrée.
- **286 tests API réussis**, zéro échec, erreur ou skip ; Maven `BUILD SUCCESS`, code de sortie 0.
- **179 tests Front réussis** lors de la préparation, build production réussi et recompilé pour le montage local.
- **63 tests du cycle local réussis** : cycle 29, menu 17, HTTPS 10, gardes d'authentification 7.
- **14 contrôles `./wavy local test factures` réussis** : services nécessaires, HTTPS, authentification et PWA non sélectionnée fermée.
- Comparaison avant/après des empreintes de **50 tables** dans les quatre bases utilisées (Socle, Tiers, Contrats, Factures) : aucune différence.
- Empreinte du stockage documentaire et contenu du PDF source inchangés.
- `git diff --check` réussi ; commits HEAD, manifestes et fichiers PREPROD conservés.

Les erreurs de configuration absente, HTTP 401, HTTP 403, modèle introuvable et réponse IA invalide sont distinguées par des codes, avec tests simulés. Aucun refus fournisseur n'a été provoqué avec la vraie clé pour tester ces branches.

Le [relevé synthétique](validation-msi-factures-dates-ia.json) ne contient aucun secret. Captures et journaux détaillés restent dans le dossier privé local `~/.local/state/wavy/recettelocal/validation-factures`.

## Ce qui reste propre à RECETTE distante

La réussite MSI établit que la configuration et les droits du fournisseur utilisés sur MSI fonctionnent. Elle ne prouve ni la présence ni la validité des paramètres dans le conteneur distant. Le refus antérieur sur RECETTE doit encore être départagé par son statut HTTP exact et le relevé expurgé configuration rendue/conteneur actif, sans copier ou remplacer une clé.

Les corrections de priorité URL, de classification des erreurs et du parcours de prévisualisation achats ne sont pas dans les images distantes actuelles. Après accord de publication, il faudra publier les seuls composants modifiés selon le parcours existant, installer avec `./wavy install recette`, puis vérifier le digest actif et refaire les tests fonctionnels distants. Les anciens paramètres URL explicites doivent toujours être conservés ; Réinitialiser est l'action de retour aux nouveaux défauts.

Aucune validation runtime ou intervention PREPROD n'a été effectuée. Aucun accès VM n'a été utilisé pour cette campagne.
