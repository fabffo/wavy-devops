# Système de Rapprochement Fournisseur IA - Implémentation Complète

## 📋 Vue d'ensemble

Le système permet aux utilisateurs de créer des règles de rapprochement automatique des fournisseurs lors de l'extraction IA de factures d'achat. Si un fournisseur extrait ne correspond à aucun fournisseur existant, l'utilisateur peut :

1. Créer un nouveau fournisseur directement depuis l'écran d'extraction
2. Créer une règle de rapprochement pour automatiser les futures extractions

## ✅ Implémentation Backend

### Architecture
```
rapprochement/
├── model/
│   ├── RegleRapprochementFournisseur.java (JPA entity)
│   └── TypeMotifRapprochementFournisseur.java (enum)
├── dto/
│   ├── CreationRegleRapprochementFournisseurDemande.java
│   ├── ModificationRegleRapprochementFournisseurDemande.java
│   └── RegleRapprochementFournisseurReponse.java
├── repository/
│   └── RegleRapprochementFournisseurRepository.java
├── service/
│   ├── RegleRapprochementFournisseurService.java
│   └── FactureAchatExtractionNormalisationService.java
└── controller/
    └── RegleRapprochementFournisseurControleur.java
```

### Base de données
```sql
CREATE TABLE regle_rapprochement_fournisseur (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    tenant_id BIGINT NOT NULL,
    societe_courante_id BIGINT NOT NULL,
    tiers_id BIGINT NOT NULL,
    libelle VARCHAR(255) NOT NULL,
    motif TEXT NOT NULL,
    type_motif VARCHAR(30) NOT NULL,
    score_priorite INT NOT NULL DEFAULT 100,
    actif BOOLEAN NOT NULL DEFAULT true,
    date_creation DATETIME NOT NULL,
    date_modification DATETIME
);
```

### API Endpoints

```
GET  /api/factures/achats/rapprochement-fournisseurs/regles
POST /api/factures/achats/rapprochement-fournisseurs/regles
PUT  /api/factures/achats/rapprochement-fournisseurs/regles/{id}
DELETE /api/factures/achats/rapprochement-fournisseurs/regles/{id}
```

### Logique de matching
- **Ordre de priorité**: Score (décroissant) → Date création (plus récente)
- **Types de motif**:
  - EGAL : Match case-insensitive exact
  - CONTIENT : Substring case-insensitive (recommandé pour les noms)
  - SIREN/SIRET/TVA_INTRACOM : Réservés pour utilisation future
- **Filtrage automati**: par tenantId et societeCouranteId via ContexteRequete

## ✅ Implémentation Frontend

### Architecture
```
components/
├── extraction-facture-achat-dialog.component.ts (MODIFIÉ)
├── extraction-facture-achat-dialog.component.html (MODIFIÉ)
├── creer-fournisseur-dialog.component.ts (CRÉÉ)
└── creer-regle-rapprochement-dialog.component.ts (CRÉÉ)

services/
├── rapprochement-fournisseur.service.ts (CRÉÉ)
└── tiers-api.service.ts (MODIFIÉ - ajout creerTiers)

models/
└── facture-achat-extraction-ia.model.ts (MODIFIÉ - ajout champs)
```

### Fonctionnalités

1. **Dialog de création de fournisseur**
   - Sélection type: Personne morale / Personne physique
   - Champs dynamiques selon type
   - Validation email
   - Créé le fournisseur via TiersApiService
   - Ajoute le fournisseur créé à la liste dropdown

2. **Dialog de création de règle**
   - Champs: Libellé, Motif, Type motif, Score priorité, Actif
   - Préremplit le motif avec fournisseurNomExtrait
   - Score par défaut: 100
   - Type motif par défaut: CONTIENT
   - Appel RapprochementFournisseurService.creerRegle()

3. **Alerte dans l'extraction**
   - Affichée si: pas de tiersId ET fournisseurNomExtrait fourni
   - Message: "Fournisseur non rapproché"
   - Actions: Bouton "Créer fournisseur" + "Créer règle" (si tiersId)

4. **Intégration extraction**
   - Affiche fournisseurNomExtrait en lecture seule
   - Affiche fournisseurNom en éditable (rempli après matching)
   - Champ tiersId sélectionnable via dropdown

### DTOs Frontend
```typescript
// Ajoutés à FactureAchatExtraite
fournisseurNomExtrait?: string | null;  // Raw IA output
fournisseurId?: number | null;           // Matched tiersId

// Interfaces service
interface CreationRegleRapprochementFournisseurDemande
interface RegleRapprochementFournisseurReponse
interface ModificationRegleRapprochementFournisseurDemande
interface CreationTiersDemande
```

## 🧪 Tests

### Backend (à exécuter)
```bash
cd /path/to/wavy-factures-api
./mvnw clean test
```

Tests implémentés:
- RegleRapprochementFournisseurServiceTest (7 tests)
- FactureAchatExtractionNormalisationServiceTest (2 tests)

### Frontend
À implémenter: Tests d'intégration des components dialogs

## 🚀 Utilisation en production

### 1. Créer une règle via API
```bash
POST /api/factures/achats/rapprochement-fournisseurs/regles
Headers: X-Tenant-Id: 1, X-Societe-Courante-Id: 1
Body: {
  "tiersId": 999,
  "libelle": "Lagardere vers Harvard Business Review",
  "motif": "LAGARDERE TR FRANCE SNC",
  "typeMotif": "CONTIENT",
  "scorePriorite": 100,
  "actif": true
}
```

### 2. Extraire une facture
- L'IA extrait le fournisseur → `fournisseurNomExtrait`
- Logique automatique teste les règles
- Si match: tiersId renseigné automatiquement
- Si pas de match: Affiche alerte avec boutons créer

### 3. Créer fournisseur depuis interface
- Utilisateur clique "Créer fournisseur"
- Modal s'ouvre
- Remplit le formulaire (type, raison sociale/nom, etc.)
- API crée le fournisseur
- Dropdown se met à jour
- Utilisateur sélectionne le nouveau fournisseur

### 4. Créer règle depuis interface
- Utilisateur sélectionne un fournisseur dans le dropdown
- Clique "Créer règle"
- Modal s'ouvre (motif pré-rempli avec fournisseurNomExtrait)
- Ajuste si nécessaire (motif, type, score)
- Sauvegarde
- Règle active pour futures extractions

## 📊 Flux d'extraction complet

```
1. Upload PDF
   ↓
2. Extraction IA (fournisseurNomExtrait obtenu)
   ↓
3. Matching automatique contre règles actives
   ├─ Match trouvé → tiersId renseigné
   └─ Pas de match → Alerte affichée
   ↓
4. Utilisateur peut:
   ├─ Créer fournisseur
   ├─ Sélectionner fournisseur manuellement
   └─ Créer règle pour next time
   ↓
5. Création facture avec tiersId
```

## ⚠️ Points importants

- **Sécurité**: Filtrage automatique par tenantId + societeCouranteId
- **Performance**: Règles triées par score puis date, seule la première applicable est utilisée
- **Immutabilité**: DTOs en records Java (immutables)
- **Audit**: Champs date_creation/date_modification automatiques via @PrePersist/@PreUpdate
- **Validation**: Demandes validées via @Valid + Validators côté front

## 📋 Checklist déploiement

- [ ] Tester backend: `./mvnw clean test` ✅ À faire
- [ ] Vérifier migrations DB (ddl-auto=update en dev) ✅ À faire
- [ ] Tester création fournisseur en UI ✅ À faire
- [ ] Tester création règle en UI ✅ À faire
- [ ] Tester matching automatique ✅ À faire
- [ ] Tester re-extraction après création règle ✅ À faire
- [ ] Documenter règles recommandées pour users ✅ À faire
- [ ] Déployer sur recette ✅ À faire
- [ ] Déployer sur production ✅ À faire

## 📞 Support

Fichiers d'implémentation:
- Backend: `wavy-factures-api/src/main/java/fr/wavy/factures/achat/rapprochement/`
- Frontend: `wavy-factures-front/src/app/features/factures-achats/components/` et `services/`

Documentation:
- [IMPLEMENTATION_BACKEND_RAPPROCHEMENT.md](../wavy-factures-api/IMPLEMENTATION_BACKEND_RAPPROCHEMENT.md)
- [EXTRACTION_IA_RAPPROCHEMENT_FOURNISSEUR.md](../EXTRACTION_IA_RAPPROCHEMENT_FOURNISSEUR.md) (spec initiale)
