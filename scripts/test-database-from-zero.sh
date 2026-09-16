#!/usr/bin/env bash
# Ancien test destructif : incompatible avec les noms fixes et le projet PREPROD.
set -euo pipefail
printf '%s\n' 'Test désactivé : créer un Compose éphémère réellement isolé avant de tester une reconstruction. Ne jamais supprimer les volumes PREPROD. Voir README_PREPROD.md.' >&2
exit 1
