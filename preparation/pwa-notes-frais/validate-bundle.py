#!/usr/bin/env python3
"""Contrôle du lot candidat ; aucune commande de déploiement ou de pull."""
import argparse
import json
from pathlib import Path
import re
import subprocess

COMPONENTS = ['factures-api', 'pwa', 'factures-front', 'erp-shell']


def validate_labels(component, image, labels):
    version, revision = image['version'].rsplit('-', 1)
    actual = labels.get('org.opencontainers.image.revision', '')
    if not re.fullmatch(r'[a-f0-9]{7,40}', actual) or not actual.startswith(revision):
        raise ValueError('Révision OCI incompatible : ' + component)
    if labels.get('org.opencontainers.image.version') != version:
        raise ValueError('Version OCI incompatible : ' + component)
    if labels.get('org.opencontainers.image.source') != 'https://github.com/fabffo/wavy-' + component:
        raise ValueError('Source OCI incompatible : ' + component)


def validate(data):
    if data['components'] != COMPONENTS or set(data['images']) != set(COMPONENTS):
        raise ValueError('Les quatre images vérifiées sont requises ; livraison partielle interdite')
    for component in COMPONENTS:
        image = data['images'][component]
        if not re.fullmatch(r'\d+\.\d+\.\d+-[a-f0-9]{7,40}', image['version']):
            raise ValueError('Version immuable requise')
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', image['digest']):
            raise ValueError('Digest complet requis')
        if image['reference'] != f"ghcr.io/fabffo/wavy-{component}@{image['digest']}":
            raise ValueError('Référence non épinglée ou dépôt incorrect')
        validate_labels(component, image, image['ociLabels'])
    if len({image['platform'] for image in data['images'].values()}) != 1:
        raise ValueError('Plateformes du lot incompatibles')
    if data['deploymentOrder'] != ['factures-api', 'factures-front', 'pwa', 'erp-shell']:
        raise ValueError('Ordre de déploiement incompatible')
    if data['requiredChecks'] != ['https', 'secure-cookie', 'volume-uid-gid', 'backup-restore',
                                  'session-isolation', 'browser', 'android', 'ios']:
        raise ValueError('Liste de contrôles fonctionnels incomplète')
    if data['pwaEnabledByDefault'] is not False:
        raise ValueError('PWA à fermer par défaut')
    return True


def validate_local_images(data):
    context = subprocess.check_output(['docker', 'context', 'inspect', '--format',
                                       '{{.Endpoints.docker.Host}}'], text=True).strip()
    import os
    if os.environ.get('DOCKER_HOST') or not context.startswith('unix://'):
        raise ValueError('Daemon Docker local Unix requis')
    for component, expected in data['images'].items():
        tag = f"ghcr.io/fabffo/wavy-{component}:{expected['version']}"
        actual = json.loads(subprocess.check_output(['docker', 'image', 'inspect', tag]))[0]
        if expected['reference'] not in actual.get('RepoDigests', []):
            raise ValueError('RepoDigest local incompatible : ' + component)
        validate_labels(component, expected, actual['Config'].get('Labels') or {})
        if actual['Os'] + '/' + actual['Architecture'] != expected['platform']:
            raise ValueError('Plateforme locale incompatible : ' + component)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', nargs='?', default=Path(__file__).with_name('release-plan.json'))
    parser.add_argument('--local-images', action='store_true')
    args = parser.parse_args()
    try:
        data = json.loads(Path(args.plan).read_text())
        validate(data)
        if args.local_images:
            validate_local_images(data)
        print('Lot statique conforme' + (' ; RepoDigests et labels OCI locaux conformes' if args.local_images else '')
              + '. Ceci ne valide ni le runtime ni une activation coordonnée.')
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError):
        parser.exit(1, 'Lot refusé : plan, références ou preuves OCI invalides.\n')
