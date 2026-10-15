#!/usr/bin/env python3
"""Validation statique du futur lot ; aucune commande de déploiement."""
import json,re,sys
from pathlib import Path
COMPONENTS=['factures-api','pwa','factures-front','erp-shell']
def validate(data):
    if data['components']!=COMPONENTS or set(data['images'])!=set(COMPONENTS):raise ValueError('Les quatre images vérifiées sont requises ; livraison partielle interdite')
    for component in COMPONENTS:
        image=data['images'][component]
        if not re.fullmatch(r'\d+\.\d+\.\d+-[a-f0-9]{7,40}',image['version']):raise ValueError('Version immuable requise')
        if not re.fullmatch(r'sha256:[a-f0-9]{64}',image['digest']):raise ValueError('Digest complet requis')
    return True
if __name__=='__main__':
    try:validate(json.loads(Path(sys.argv[1] if len(sys.argv)>1 else Path(__file__).with_name('release-plan.json')).read_text()));print('Lot complet ; vérifier encore les labels OCI et RepoDigests GHCR avant toute activation.')
    except (ValueError,KeyError) as error:print(str(error),file=sys.stderr);sys.exit(1)
