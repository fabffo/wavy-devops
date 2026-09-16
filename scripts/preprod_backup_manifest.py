#!/usr/bin/env python3
"""Authentifie cinq dumps + archive documentaire chiffrés (format 2)."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import sys

DATABASES = ['socle', 'tiers', 'contrats', 'factures', 'tresorerie']

def checksum(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def run(action, folder):
    path = Path(folder)
    password = os.environ['WAVY_BACKUP_PASSPHRASE'].encode()
    if action == 'sign':
        meta = {'environment': 'preprod', 'project': 'wavy-preprod', 'format': 2,
                'salt': os.urandom(16).hex(),
                'files': {name: checksum(path/name) for name in [db+'.dump.enc' for db in DATABASES]+['documents.tar.enc']}}
    else:
        meta = json.loads((path/'manifest.json').read_text())
    payload = {k: v for k, v in meta.items() if k != 'hmac'}
    key = hashlib.pbkdf2_hmac('sha256', password, bytes.fromhex(meta['salt']), 200000)
    signature = hmac.new(key, json.dumps(payload, sort_keys=True).encode(), 'sha256').hexdigest()
    if action == 'sign':
        meta['hmac'] = signature
        (path/'manifest.json').write_text(json.dumps(meta, indent=2)+'\n')
    else:
        if not hmac.compare_digest(meta['hmac'], signature):
            raise ValueError('HMAC')
        if meta['environment'] != 'preprod' or meta['project'] != 'wavy-preprod' or meta['format'] != 2:
            raise ValueError('Provenance/format')
        if set(meta['files']) != {db+'.dump.enc' for db in DATABASES} | {'documents.tar.enc'}:
            raise ValueError('Lot incomplet')
        for filename, digest in meta['files'].items():
            if not hmac.compare_digest(checksum(path/filename), digest):
                raise ValueError('Intégrité')

if __name__ == '__main__':
    try:
        run(sys.argv[1], sys.argv[2])
    except Exception:
        print('ERREUR : lot PREPROD incomplet, altéré ou passphrase incorrecte.', file=sys.stderr)
        sys.exit(1)
