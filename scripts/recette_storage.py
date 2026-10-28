#!/usr/bin/env python3
"""Provisionnement initial contrôlé ; aucun changement de droits sur l'existant."""
import json
import re
import subprocess
import uuid
from recette_pwa import STORAGE_PROBE


def run(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs).stdout.strip()


def tool(volume, image, script, user=None):
    args = ['docker', 'run', '--rm', '--pull', 'never', '--network', 'none', '--read-only',
            '--security-opt', 'no-new-privileges:true', '--cap-drop', 'ALL']
    if user:
        args += ['--user', user, '--cap-add', 'CHOWN', '--cap-add', 'FOWNER', '--cap-add', 'DAC_OVERRIDE']
    return run(args + ['--mount', f'type=volume,source={volume},target=/app/justificatifs,volume-nocopy',
                      '--entrypoint', 'sh', image, '-ec', script], timeout=60)


def check_volume(volume, image):
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*', volume):
        raise ValueError('Nom du volume documentaire invalide')
    obj = json.loads(run(['docker', 'volume', 'inspect', volume]))[0]
    if obj.get('Driver') != 'local' or obj.get('Options'):
        raise ValueError('Volume documentaire local sans options requis')
    if tool(volume, image, STORAGE_PROBE) != 'private-storage-ok':
        raise ValueError('Volume documentaire privé non conforme')


def provision(volume, image, allowed=False):
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*', volume):
        raise ValueError('Nom du volume documentaire invalide')
    # Un échec du daemon ne doit pas être interprété comme un volume absent.
    names = run(['docker', 'volume', 'ls', '--format', '{{.Name}}']).splitlines()
    if volume not in names:
        if not allowed:
            raise ValueError('Volume absent : autoriser une fois WAVY_RECETTE_PROVISION_JUSTIFICATIFS=true')
        uid, gid = run(['docker', 'run', '--rm', '--pull', 'never', '--network', 'none', '--read-only',
                        '--cap-drop', 'ALL', '--entrypoint', 'sh', image, '-ec',
                        'printf "%s %s" "$(id -u)" "$(id -g)"']).split()
        if not re.fullmatch(r'[1-9][0-9]*', uid) or not gid.isdecimal():
            raise ValueError('Utilisateur documentaire non root requis')
        token = uuid.uuid4().hex
        run(['docker', 'volume', 'create', '--driver', 'local', '--label', 'wavy.environment=recette', '--label', 'wavy.provision='+token, volume])
        created = json.loads(run(['docker','volume','inspect',volume]))[0]
        if created.get('Labels', {}).get('wavy.provision') != token:
            raise ValueError('Volume créé concurremment : aucun changement de permissions autorisé')
        # Pas de chown récursif ; refus si un fichier existe, même caché.
        tool(volume, image, 'test -z "$(ls -A /app/justificatifs)"; '
             f'chown {uid}:{gid} /app/justificatifs; chmod 0700 /app/justificatifs', user='0:0')
    check_volume(volume, image)
