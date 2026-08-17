# Extraction IA des factures de vente et d'achat

Le module `wavy-factures-api` expose des flux d'extraction IA séparés pour les ventes et les achats.

En pur local, via le gateway lancé par `./scripts/start-local-tmux.sh` :

```bash
curl -i -X POST http://localhost:8088/api/factures/ventes/extraction-ia \
  -H "X-Tenant-Id: 100" \
  -H "X-Utilisateur-Id: 100" \
  -H "X-Societe-Courante-Id: 100" \
  -F "fichier=@/chemin/facture.pdf"
```

Pour une facture fournisseur :

```bash
curl -i -X POST http://localhost:8088/api/factures/achats/extraction-ia \
  -H "X-Tenant-Id: 100" \
  -H "X-Utilisateur-Id: 100" \
  -H "X-Societe-Courante-Id: 100" \
  -F "categorieAchat=FRAIS_GENERAUX" \
  -F "fichier=@/tmp/facture-achat-test.pdf"
```

La catégorie achat peut être `ACHAT_EXPLOITATION` ou `FRAIS_GENERAUX`. Si elle est fournie, elle est prioritaire sur la proposition IA.

Avec Docker local, remplacer le port `8088` par `18088`.

En recette Docker locale, utiliser le port `28088` :

```bash
curl -i -X POST http://localhost:28088/api/factures/achats/extraction-ia \
  -H "X-Tenant-Id: 3" \
  -H "X-Utilisateur-Id: 2" \
  -H "X-Societe-Courante-Id: 4" \
  -F "categorieAchat=ACHAT_EXPLOITATION" \
  -F "fichier=@/chemin/facture-fournisseur.pdf"
```

## Configuration

Renseigner les variables suivantes dans `.env.local` ou `.env.recette` :

```env
WAVY_AI_PROVIDER=anthropic
WAVY_AI_MODEL=
WAVY_AI_API_KEY=
WAVY_AI_TIMEOUT_SECONDS=60
WAVY_AI_MAX_FILE_SIZE_MB=10
WAVY_AI_ACHAT_AUTO_CREATION_ENABLED=true
WAVY_AI_ACHAT_MINIMUM_CONFIDENCE=0.90
```

Ne jamais committer de vraie clé API. Si la clé ou le modèle est absent, l’endpoint répond avec une erreur de prévisualisation contrôlée et ne tente aucun appel externe.

## Sécurité et limites

- La clé IA reste uniquement côté backend.
- Le PDF n’est pas stocké en base dans cette étape.
- Le PDF/base64 n’est pas loggué.
- La taille maximale est configurable.
- Les tests automatisés mockent le client IA et ne font aucun appel réel.
- Les coûts dépendent du fournisseur, du modèle et de la taille des PDF.
- Un fichier non PDF ou trop volumineux est refusé avant tout appel IA.
- Les flux achats et ventes ont des prompts, DTO et endpoints distincts.

Un fichier non PDF renvoie une erreur HTTP `400` avec le code `PDF_INVALIDE`. Exemple de contrôle :

```bash
curl -i -X POST http://localhost:8088/api/factures/achats/extraction-ia \
  -H "X-Tenant-Id: 100" \
  -H "X-Utilisateur-Id: 100" \
  -H "X-Societe-Courante-Id: 100" \
  -F "fichier=@/tmp/facture-invalide.txt"
```

Comportement après extraction :

- Vente : l’utilisateur valide la prévisualisation, choisit un tiers avec le rôle `CLIENT`, puis déclenche le `POST /api/factures/ventes`.
- Achat : les extractions entièrement valides sont créées automatiquement ; les autres restent modifiables et peuvent être créées manuellement par `POST /api/factures/achats`.

Pour les achats, le backend crée et valide automatiquement la facture lorsque le fournisseur Wavy est rapproché,
que les champs et montants sont cohérents, qu'aucun doublon n'est détecté et que le score de confiance atteint le seuil.
Sinon, la réponse contient `creationAutomatiquePossible=false`, `factureCreeeAutomatiquement=false` et la liste `anomalies` ;
le front conserve alors la validation manuelle. La création automatique ne crée jamais de tiers.
