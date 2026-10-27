#!/usr/bin/env python3
"""Références de release partagées par les chemins Compose existants."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

COMPONENTS = ('socle-api tiers-api contrats-api factures-api tresorerie-api gateway '
              'socle-front tiers-front contrats-front factures-front tresorerie-front pwa erp-shell').split()


def manifest(path, strict=True):
    values = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        key, value = line.split('=', 1)
        if strict and key in values:
            raise ValueError(f'Clé dupliquée : {path.name}/{key}')
        values[key] = value
    return values


def release(root, env):
    versions = manifest(root / f'versions/{env}.env')
    digests = manifest(root / f'versions/{env}.digests')
    images = {}
    for component in COMPONENTS:
        key = component.upper().replace('-', '_')
        version = versions.get(key+'_VERSION', '')
        digest = digests.get(key+'_DIGEST', '')
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
            raise ValueError(f'Digest absent ou invalide : {env}/{component}, release {version}')
        if not re.fullmatch(r'\d+\.\d+\.\d+-[0-9a-f]{7,40}', version):
            raise ValueError(f'Version de release invalide : {env}/{component}')
        history = root / f'versions/history/{env}/{component}.tsv'
        if history.exists():
            for line in history.read_text().splitlines()[1:]:
                fields = line.split('\t')
                if fields[0] == version and fields[1] != digest:
                    raise ValueError(f'Digest incompatible avec la release {env}/{component}/{version}')
        images[component] = f"{versions['WAVY_IMAGE_REGISTRY']}/wavy-{component}:{version}@{digest}"
    return versions, digests, images


def verify(root, env):
    _, _, images = release(root, env)
    # Vérifier l'ensemble avant toute recréation, même pour une commande ciblée.
    for component, pinned in images.items():
        tag, expected = pinned.split('@')
        subprocess.run(['docker', 'pull', tag], check=True, stdout=subprocess.DEVNULL)
        result = subprocess.run(['docker', 'image', 'inspect', tag], check=True,
                                capture_output=True, text=True)
        repo = tag.rsplit(':', 1)[0]
        if repo+'@'+expected not in json.loads(result.stdout)[0].get('RepoDigests', []):
            raise ValueError(f'Digest incompatible avec la release {env}/{component} : {tag}, attendu {expected}')
        subprocess.run(['docker', 'pull', pinned], check=True, stdout=subprocess.DEVNULL)


def recette_compose(root, args):
    versions, digests, _ = release(root, 'recette')
    raw = (root / 'docker-compose.recette.yml').read_text()
    keys = set(re.findall(r'\$\{([A-Z][A-Z0-9_]*)', raw))
    clean = {k: v for k, v in os.environ.items() if k not in keys and not k.startswith('COMPOSE_')}
    # Les manifestes ont priorité sur le shell et le dotenv machine.
    clean.update(versions)
    clean.update(digests)
    if args[0] == 'build':
        print('RECETTE : commande build historique → téléchargement des images validées.', flush=True)
        verify(root, 'recette')
        return 0
    if args[0] in ('up', 'create', 'run'):
        if '--build' in args:
            raise ValueError('Build interdit en RECETTE ; utiliser les images de release.')
        verify(root, 'recette')
        args = [args[0], '--no-build', *args[1:]]
    return subprocess.run(['docker', 'compose', '--env-file', str(root / '.env.recette'),
                           '--env-file', str(root / 'versions/recette.env'),
                           '--env-file', str(root / 'versions/recette.digests'),
                           '-p', manifest(root / '.env.recette', strict=False).get('COMPOSE_PROJECT_NAME', 'wavy-recette'),
                           '-f', str(root / 'docker-compose.recette.yml'), *args], env=clean).returncode


if __name__ == '__main__':
    try:
        root = Path(__file__).resolve().parent.parent
        if sys.argv[1] == 'verify':
            verify(root, sys.argv[2])
        else:
            raise SystemExit(recette_compose(root, sys.argv[1:]))
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        print(f'ERREUR release images : {exc}', file=sys.stderr)
        sys.exit(1)
