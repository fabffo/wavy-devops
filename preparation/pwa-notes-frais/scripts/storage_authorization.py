#!/usr/bin/env python3
"""Capacité de provisionnement : jeton en pipe hérité, reçu privé consommé avant Docker."""
import hashlib
import fcntl
from datetime import datetime
import importlib.util
import json
import os
from pathlib import Path
import secrets
import select
import stat
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('storage_operation', ROOT/'scripts/preprod_operation.py')
operation = importlib.util.module_from_spec(spec); spec.loader.exec_module(operation)


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def identity(path):
    s = os.stat(path, follow_symlinks=False)
    return [s.st_dev, s.st_ino, s.st_mtime_ns]


def issue(directory, reservation, run, plan):
    directory = Path(directory)
    state = operation.read_private(directory/'state.json')
    reserved = operation.read_private(reservation)
    checks = state.get('storagePreconditions', {})
    current = time.time()
    if not (state['phase'] == 'preparing' and state['run'] == reserved['run'] == run
            and state['planHash'] == reserved['planHash'] == digest(plan)
            and checks.get('run') == run and checks.get('closed') is True
            and checks.get('preflight') is True and state.get('previous') is not None
            and checks.get('snapshotHash') == digest(state['previous'])
            and 0 <= current - checks.get('checkedAt', 0) < 60):
        raise ValueError('Précontrôles courants requis')
    checked = datetime.fromisoformat(state['prerequisites']['checkedAt']).timestamp()
    if not 0 <= current-checked < 86400:
        raise ValueError('Prérequis expirés')
    expires = min(current+60, checks['checkedAt']+60, checked+86400)
    token = secrets.token_bytes(32)
    proof = {'action':'provision-storage', 'run':run, 'planHash':digest(plan),
             'stateHash':digest(state), 'reservationHash':digest(reserved),
             'stateIdentity':identity(directory/'state.json'), 'reservationIdentity':identity(reservation),
             'issuedAt':current, 'expiresAt':expires, 'tokenHash':hashlib.sha256(token).hexdigest()}
    operation.atomic_json(directory/'storage-authorization.json', proof)
    reader, writer = os.pipe()
    capability = None
    try:
        # Les adaptateurs Bash réservent 9 au verrou : ne jamais y placer le jeton.
        capability = fcntl.fcntl(reader, fcntl.F_DUPFD_CLOEXEC, 10)
        os.write(writer, token)
        return capability
    except BaseException:
        if capability is not None: os.close(capability)
        raise
    finally:
        os.close(reader); os.close(writer)


def claim_once(directory, proof):
    """O_EXCL crée un reçu terminal par jeton, indépendant de tout flock hérité."""
    token_hash = proof['tokenHash']
    if len(token_hash) != 64 or any(c not in '0123456789abcdef' for c in token_hash):
        raise ValueError('Identité de capacité incorrecte')
    path = directory / ('storage-consumed-' + token_hash + '.json')
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        raise ValueError('Autorisation déjà réclamée') from None
    # L'existence seule est terminale, même si une interruption laisse un fichier incomplet.
    # Aucun unlink, truncate ou remplacement de ce reçu n'est jamais autorisé ici.
    with os.fdopen(fd, 'w') as stream:
        json.dump({'consumed':True, 'run':proof['run'], 'planHash':proof['planHash']}, stream)
        stream.flush()
        os.fsync(stream.fileno())
    operation.sync_directory(directory)
    return path.name


def consume(root, plan_path, run, lock_fd, token_fd):
    root, plan_path = Path(root), Path(plan_path)
    directory = root/'deployments/pwa-release'
    if plan_path != directory/'runtime-plan.json': raise ValueError('Plan non canonique')
    if not os.path.samestat(os.fstat(lock_fd), (root/'deployments/preprod.lock').stat()):
        raise ValueError('FD de verrou incorrect')
    with operation.Operation(root, owner=run, inherited=lock_fd):
        proof = operation.read_private(directory/'storage-authorization.json')
        state = operation.read_private(directory/'state.json')
        reserved = operation.read_private(root/'deployments/preprod-reservation.json')
        gate = operation.read_private(directory/'edge.json')
        plan = json.loads(plan_path.read_text())
        current = time.time()
        if not (proof['action'] == 'provision-storage' and proof['run'] == state['run'] == reserved['run'] == run
                and proof['planHash'] == state['planHash'] == reserved['planHash'] == digest(plan)
                and proof['stateHash'] == digest(state) and proof['reservationHash'] == digest(reserved)
                and proof['stateIdentity'] == identity(directory/'state.json')
                and proof['reservationIdentity'] == identity(root/'deployments/preprod-reservation.json')
                and proof['issuedAt'] <= current < proof['expiresAt'] <= proof['issuedAt']+60
                and state['phase'] == 'preparing' and state['storagePreconditions']['closed'] is True
                and gate['mode'] == 'closed' and gate['run'] == run and gate['closureBlocked'] is False):
            raise ValueError('Autorisation périmée ou invalidée')
        if not stat.S_ISFIFO(os.fstat(token_fd).st_mode): raise ValueError('Pipe hérité requis')
        if not select.select([token_fd], [], [], 0)[0]: raise ValueError('Capacité absente')
        token = os.read(token_fd, 33)
        if len(token) != 32 or not secrets.compare_digest(hashlib.sha256(token).hexdigest(), proof['tokenHash']):
            raise ValueError('Capacité invalide')
        # Persisté AVANT le premier montage RW. Une interruption ne réarme jamais le reçu.
        claim = claim_once(directory, proof)
        operation.atomic_json(directory/'storage-authorization.json', {'consumed':True, 'run':run, 'claim':claim})
        if not proof['issuedAt'] <= time.time() < proof['expiresAt']:
            raise ValueError('Autorisation expirée pendant la consommation')
        return proof['expiresAt']


if __name__ == '__main__':
    try:
        print(consume(ROOT, Path(os.environ['PWA_RELEASE_PLAN']), os.environ['PWA_RELEASE_RUN'],
                      int(os.environ['PWA_RELEASE_LOCK_FD']), int(os.environ['PWA_STORAGE_AUTH_FD'])))
    except BaseException:
        sys.exit('Autorisation de provisionnement refusée.')
