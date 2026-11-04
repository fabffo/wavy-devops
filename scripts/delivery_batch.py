#!/usr/bin/env python3
"""Moteur commun : precontroles, une sauvegarde coordonnee verifiee, application."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import uuid

sys.dont_write_bytecode = True
from preprod_operation import Operation, atomic_json, command_environment, read_private
from release_images import COMPONENTS, recette_operation, release
ROOT = Path(__file__).resolve().parent.parent
SESSION_KEY = 'WAVY_DELIVERY_SESSION_FD'
SEALS = fcntl.F_SEAL_SEAL | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE


def validate_session(root, environment, component=None, version=None, digest=None):
    """Une variable seule ne dispense jamais de sauvegarde : preuve scellee et moteur vivant."""
    root = Path(root).resolve()
    raw = os.environ.get(SESSION_KEY, '')
    if not raw.isdecimal(): raise ValueError('Contexte de livraison absent')
    fd = int(raw)
    if fcntl.fcntl(fd, fcntl.F_GET_SEALS) & SEALS != SEALS:
        raise ValueError('Contexte de livraison non scelle')
    state = json.loads(os.pread(fd, 131072, 0))
    if (state.get('root') != str(root) or state.get('environment') != environment
            or state.get('backupVerified') is not True or state.get('images') != release(root, environment)[2]):
        raise ValueError('Contexte de livraison incompatible')
    owner = Path('/proc')/str(state['issuerPid'])
    if not os.path.samestat(os.fstat(fd), (owner/'fd'/str(state['issuerFd'])).stat()):
        raise ValueError('Moteur de livraison termine')
    command = (owner/'cmdline').read_bytes().split(b'\0')
    if str(root/'scripts/delivery_batch.py').encode() not in command or b'run' not in command or environment.encode() not in command:
        raise ValueError('Emetteur du contexte invalide')
    backup = Path(state['backup'])
    if backup.is_symlink() or not backup.is_dir() or root/'backups' not in backup.parents:
        raise ValueError('Sauvegarde de livraison absente')
    if component is not None:
        if component not in COMPONENTS: raise ValueError('Composant inconnu')
        tag, expected = state['images'][component].split('@')
        if tag.rsplit(':', 1)[1] != version or expected != digest:
            raise ValueError('Image hors livraison sauvegardee')
    return state


@contextmanager
def locked(root, environment):
    if environment == 'preprod':
        with Operation(root) as operation:
            yield operation.fd, command_environment(root, operation.fd)
    else:
        path = root/'deployments/recette.lock'
        path.parent.mkdir(exist_ok=True)
        inherited = os.environ.get('WAVY_RECETTE_LOCK_FD')
        fd = int(inherited) if inherited else os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        old = os.environ.get('WAVY_RECETTE_LOCK_FD')
        os.environ['WAVY_RECETTE_LOCK_FD'] = str(fd)
        try:
            with recette_operation(root, True):
                yield fd, dict(os.environ)
        finally:
            if old is None: os.environ.pop('WAVY_RECETTE_LOCK_FD', None)
            else: os.environ['WAVY_RECETTE_LOCK_FD'] = old
            if not inherited: os.close(fd)


def backup_folders(root, environment):
    base = root/'backups'/('preprod' if environment == 'preprod' else '')
    if not base.is_dir(): return set()
    return {p for p in base.iterdir() if p.is_dir() and not p.is_symlink() and
            re.fullmatch(r'\d{8}T\d{6}Z-[A-Za-z0-9]+' if environment == 'preprod'
                         else r'\d{4}-\d{2}-\d{2}_\d{6}(?:-\d+)?', p.name)}


def verify_backup(root, environment, path):
    if environment == 'preprod':
        from preprod_config import dotenv
        from preprod_backup_manifest import run
        old = os.environ.get('WAVY_BACKUP_PASSPHRASE')
        os.environ['WAVY_BACKUP_PASSPHRASE'] = dotenv(root/'.env.preprod')['WAVY_BACKUP_ENCRYPTION_PASSPHRASE']
        try: run('verify', str(path))
        finally:
            if old is None: os.environ.pop('WAVY_BACKUP_PASSPHRASE', None)
            else: os.environ['WAVY_BACKUP_PASSPHRASE'] = old
    else:
        from recette_documents import verify
        verify(path)


def snapshot(environment):
    result = {}
    for component in COMPONENTS:
        name = f'wavy-{component}-{environment}'
        fields = {}
        for key, template in (('id', '{{.Image}}'), ('reference', '{{.Config.Image}}')):
            fields[key] = subprocess.check_output(['docker', 'inspect', '-f', template, name], stderr=subprocess.DEVNULL).decode().strip()
        result[component] = fields
    return result


def child(command, env, descriptors):
    # Arret gracieux du groupe, sans SIGKILL : laisser les traps reprendre les writers.
    process = subprocess.Popen(command, env=env, pass_fds=tuple(descriptors), start_new_session=True)
    interrupted = []
    def stop(signum, frame):
        if interrupted: return
        interrupted.append(signum)
        try: os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError: pass
    previous = {sig:signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        code = process.wait()
        if interrupted:
            # Le wrapper peut finir avant le trap de son fils Bash.
            while group_running(process.pid): time.sleep(0.1)
            return 128 + interrupted[0]
        return code
    finally:
        for sig, handler in previous.items(): signal.signal(sig, handler)


def group_running(group):
    for path in Path('/proc').iterdir():
        if not path.name.isdecimal(): continue
        try:
            fields = (path/'stat').read_text().rsplit(')', 1)[1].split()
            if fields[0] != 'Z' and int(fields[2]) == group: return True
        except (OSError, ValueError, IndexError): pass
    return False


def run(root, environment):
    with locked(root, environment) as (lock_fd, env):
        env.pop(SESSION_KEY, None)
        record_path = root/'deployments'/f'{environment}-delivery-{uuid.uuid4().hex}.private.json'
        state = {'environment':environment, 'phase':'preflight', 'images':release(root, environment)[2],
                 'backup':None, 'backupVerified':False, 'before':{}, 'completed':[]}
        stage = 'preflight'; capsule = None
        try:
            code = child(['bash', str(root/'scripts/delivery-preflight.sh'), environment], env, [lock_fd])
            if code: return fail(record_path, state, stage, code)
            state['before'] = snapshot(environment)
            atomic_json(record_path, state)
            stage = 'backup'
            state['phase'] = 'backup'
            atomic_json(record_path, state)
            before = backup_folders(root, environment)
            provider = 'backup-preprod.sh' if environment == 'preprod' else 'backup-db.sh'
            backup_env = dict(env, WAVY_ENV=environment)
            code = child(['bash', str(root/'scripts'/provider)], backup_env, [lock_fd])
            if code: return fail(record_path, state, stage, code)
            created = backup_folders(root, environment) - before
            if len(created) != 1: raise ValueError('Lot coordonne unique introuvable')
            path = created.pop()
            stage = 'backup_integrity'
            state.update(backup=str(path), phase='backup_integrity')
            atomic_json(record_path, state)
            verify_backup(root, environment, path)
            state.update(backup=str(path), backupVerified=True, phase='applying')
            atomic_json(record_path, state)
            capsule = os.memfd_create('wavy-delivery', os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
            proof = dict(state, root=str(root), issuerPid=os.getpid(), issuerFd=capsule)
            payload = json.dumps(proof).encode()
            if os.write(capsule, payload) != len(payload): raise ValueError('Contexte incomplet')
            fcntl.fcntl(capsule, fcntl.F_ADD_SEALS, SEALS)
            apply_env = dict(env, **{SESSION_KEY:str(capsule)})
            print(f'Livraison {environment} : un lot coordonne verifie ; application des 13 images.', flush=True)
            stage = 'apply'
            journal = root/f'deployments/{environment}.tsv'
            previous_lines = len(journal.read_text().splitlines()) if journal.is_file() else 0
            code = child(['bash', str(root/'scripts/delivery-apply.sh'), environment], apply_env, [lock_fd, capsule])
            if environment == 'preprod' and journal.is_file():
                for line in journal.read_text().splitlines()[previous_lines:]:
                    fields = line.split('\t')
                    if len(fields) >= 9 and fields[2] == environment and fields[3] in COMPONENTS:
                        if fields[8] == 'OK': state['completed'].append(fields[3])
                        elif fields[8] == 'KO': state['failedComponent'] = fields[3]
            if code: return fail(record_path, state, stage, code)
            state.update(phase='complete', completed=COMPONENTS)
            atomic_json(record_path, state)
            print(f'Livraison {environment} complete : 13 composants, une sauvegarde. Bilan : {record_path}', flush=True)
            return 0
        except KeyboardInterrupt:
            return fail(record_path, state, stage, 130)
        except Exception:
            return fail(record_path, state, stage, 1)
        finally:
            if capsule is not None: os.close(capsule)


def fail(path, state, stage, code):
    status = code if code > 0 else 128 - code
    state.update(phase='failed', failedStage=stage, code=status)
    atomic_json(path, state)
    print(f'ERREUR livraison {state["environment"]} : etape={stage}, code={status}. Aucune restauration automatique. Bilan : {path}', file=sys.stderr)
    return status


def main():
    try:
        action, environment = sys.argv[1:3]
        if environment not in ('recette','preprod'): raise ValueError('Environnement')
        if action == 'run' and len(sys.argv) == 3: return run(ROOT, environment)
        if action == 'check' and len(sys.argv) in (3,6):
            validate_session(ROOT, environment, *sys.argv[3:]); return 0
        raise ValueError('Arguments')
    except Exception:
        print('ERREUR livraison : contexte, verrou ou prerequis invalide ; details bruts masques.', file=sys.stderr)
        return 1


if __name__ == '__main__': raise SystemExit(main())
