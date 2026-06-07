# Wavy PWA

`wavy-pwa` est une application Angular séparée, mobile-first et installable en PWA, dédiée au scan rapide de factures.

## Objectif

- Prendre une photo ou importer un PDF/JPG/PNG.
- Choisir facture d’achat ou facture de vente.
- Envoyer le fichier à `wavy-factures-api` via `wavy-gateway`.
- Afficher le résultat IA dans une prévisualisation éditable.
- Créer la facture uniquement après validation manuelle.

## Démarrage local

```bash
cd ~/projets/wavy-pwa
npm start
```

Port local : `http://localhost:4204`

La gateway locale attendue est `http://localhost:8088/api`.

## Routes

- `/scan` : scanner principal.
- `/scan/achat` : scanner préconfiguré achat.
- `/scan/vente` : scanner préconfiguré vente.
- `/scans` : historique local des scans.
- `/profil` : contexte local.

## Contexte MVP

Par défaut, les headers envoyés à l’API sont :

- `X-Tenant-Id: 100`
- `X-Utilisateur-Id: 100`
- `X-Societe-Courante-Id: 100`

Ils sont modifiables dans `/profil` et sauvegardés en `localStorage`.

## Utilisation Mobile

Sur téléphone, le champ fichier utilise `capture="environment"` pour ouvrir la caméra arrière quand le navigateur le permet. En desktop, il fonctionne comme un import classique.

Pour installer la PWA, servir l’application en HTTPS ou via un environnement considéré comme sécurisé par le navigateur.

## Limites MVP

- Pas de login complet.
- Pas de création fournisseur/client depuis la PWA.
- L’historique `/scans` est local au navigateur et n’est pas une source comptable.
- La création facture est toujours déclenchée par un clic utilisateur après correction.
