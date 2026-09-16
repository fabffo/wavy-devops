#!/usr/bin/env python3
"""Contrôle une archive documentaire AVANT toute extraction destructive."""
from pathlib import PurePosixPath
import sys
import tarfile


def validate(filename):
    source = {'fileobj': sys.stdin.buffer, 'mode': 'r|'} if filename == '-' else {'name': filename, 'mode': 'r:'}
    with tarfile.open(**source) as archive:
        seen = set()
        for entry in archive:
            path = PurePosixPath(entry.name)
            if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != 'contrats':
                raise ValueError('Chemin documentaire interdit')
            if not (entry.isfile() or entry.isdir()) or entry.mode & 0o7000:
                raise ValueError('Type ou permissions documentaires interdits')
            if str(path) in seen:
                raise ValueError('Entrée documentaire dupliquée')
            if entry.uid != 100 or entry.gid != 101:
                raise ValueError('Propriétaire documentaire différent de Contrats (100:101)')
            seen.add(str(path))
        if 'contrats' not in seen:
            raise ValueError('Racine contrats absente')


if __name__ == '__main__':
    try:
        validate(sys.argv[1])
    except (ValueError, OSError, tarfile.TarError):
        print('ERREUR : archive documentaire invalide ; aucune restauration autorisée.', file=sys.stderr)
        sys.exit(1)
