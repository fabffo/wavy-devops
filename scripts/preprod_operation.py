#!/usr/bin/env python3
"""Verrou et réservation PREPROD communs aux commandes supportées. Aucun Docker ici."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent


def read_private(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('État PREPROD non privé')
        data = json.load(stream)
        if not isinstance(data, dict): raise ValueError('Objet JSON privé requis')
        return data


def atomic_json(path, data):
    path = Path(path)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(data, stream, sort_keys=True)
        stream.flush(); os.fsync(stream.fileno())
    os.replace(tmp, path)
    sync_directory(path.parent)


def sync_directory(path):
    fd = os.open(path, os.O_DIRECTORY | os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


class Operation:
    def __init__(self, root, owner=None, inherited=None):
        self.root = Path(root)
        self.path = self.root / 'deployments/preprod.lock'
        self.reservation = self.root / 'deployments/preprod-reservation.json'
        self.owner = owner
        self.inherited = inherited
        self.fd = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink(): raise ValueError('Verrou symbolique interdit')
        inherited = self.inherited
        if inherited is None:
            value = os.environ.get('WAVY_PREPROD_LOCK_FD')
            inherited = int(value) if value and value.isdecimal() else None
        try:
            if inherited is not None and os.path.samestat(os.fstat(inherited), self.path.stat()):
                self.fd = os.dup(inherited)
        except (OSError, ValueError):
            pass
        if self.fd is None:
            self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(self.fd).st_mode):
                raise ValueError('Verrou invalide')
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if self.reservation.exists() or self.reservation.is_symlink():
                data = read_private(self.reservation)
                if not self.owner or data['run'] != self.owner:
                    raise ValueError('PREPROD réservé : reprise/abandon explicite requis')
        except BaseException:
            os.close(self.fd); self.fd = None
            raise
        return self

    def __exit__(self, *args):
        os.close(self.fd)

    def reserve(self, run, plan_hash, created):
        if self.reservation.exists():
            raise ValueError('Réservation déjà présente')
        atomic_json(self.reservation, {'run': run, 'planHash': plan_hash, 'createdAt': created})
        self.owner = run

    def release(self, run):
        if read_private(self.reservation)['run'] != run:
            raise ValueError('Propriétaire de réservation incorrect')
        self.reservation.unlink()
        sync_directory(self.reservation.parent)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command and not args.check: parser.error('Commande requise')
    try:
        # Le wrapper classique n'accepte JAMAIS de propriétaire par environnement.
        with Operation(args.root) as operation:
            if args.check: return 0
            env = dict(os.environ, WAVY_PREPROD_LOCK_FD=str(operation.fd))
            result = subprocess.run(command, env=env, pass_fds=(operation.fd,))
            return result.returncode
    except (OSError, ValueError, KeyError):
        print('Opération PREPROD refusée : verrou occupé ou réservation persistante.', file=sys.stderr)
        return 1


if __name__ == '__main__': sys.exit(main())
