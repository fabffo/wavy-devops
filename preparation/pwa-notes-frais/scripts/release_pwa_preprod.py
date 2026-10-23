#!/usr/bin/env python3
"""Orchestrateur candidat : prepare, validate, activate, rollback ; aucune restauration DB."""
import argparse
from datetime import datetime, timezone, timedelta
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import socket
import stat
import subprocess
import sys
import uuid

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ORDER = ['factures-api', 'factures-front', 'pwa', 'erp-shell']


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


config = load(HERE / 'preprod_config.py', 'candidate_config')
operation = load(ROOT / 'scripts/preprod_operation.py', 'shared_operation')
edge = load(HERE / 'edge_gate.py', 'edge_gate')


def fingerprint(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def private_json(path):
    fd = os.open(Path(path), os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError('Fichier de preuve/état privé requis')
        return json.load(stream)


def write_json(path, data):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(data, stream, sort_keys=True, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


class GlobalLock:
    """Même inode/verrou que release-preprod.sh, backup et restore ; jamais supprimé."""
    def __init__(self, path):
        self.path = Path(path)
        self.fd = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(self.fd)
            self.fd = None
            raise
        return self.fd

    def __exit__(self, *args):
        os.close(self.fd)


class Engine:
    def __init__(self, backend, directory, plan, lock):
        self.backend = backend
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError('Répertoire état privé 0700 requis')
        self.path = self.directory / 'state.json'
        self.journal = self.directory / 'journal.jsonl'
        self.plan = plan
        self.lock = lock
        self.state = None
        self.reservation = Path(lock).parent / 'preprod-reservation.json'
        self.run_id = None

    def event(self, action, outcome):
        # Seulement des codes internes : jamais sortie enfant, exception, URL, dotenv ou secret.
        if not re.fullmatch(r'[a-z-]+', action) or outcome not in ('START', 'OK', 'FAILED', 'CLOSED', 'CLOSE_FAILED'):
            raise ValueError('Événement invalide')
        fd = os.open(self.journal, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'a') as stream:
            stream.write(json.dumps({'time': now(), 'action': action, 'result': outcome,
                                     'run': self.state.get('run') if self.state else None}) + '\n')
            stream.flush()
            os.fsync(stream.fileno())

    def operation(self, name, function, *args):
        self.event(name, 'START')
        try:
            result = function(*args)
        except BaseException:
            self.event(name, 'FAILED')
            raise
        self.event(name, 'OK')
        return result

    def save(self):
        write_json(self.path, self.state)

    def require_phase(self, phases):
        self.state = private_json(self.path)
        if (self.state['run'] != self.run_id or self.state['planHash'] != fingerprint(self.plan) or self.state['phase'] not in phases
                or self.state['configurationHash'] != self.backend.identity()):
            raise ValueError('État incompatible')

    def attest(self, evidence, checks, functional=False):
        if evidence.get('planHash') != fingerprint(self.plan):
            raise ValueError('Preuve hors lot')
        checked = datetime.fromisoformat(evidence['checkedAt'])
        age = (datetime.now(timezone.utc) - checked).total_seconds()
        if not 0 <= age <= 86400 or not evidence.get('reviewer'):
            raise ValueError('Preuve expirée ou sans relecteur')
        if any(evidence.get('checks', {}).get(key) is not True for key in checks):
            raise ValueError('Validation incomplète')
        if functional and (evidence.get('run') != self.state['run'] or
                           evidence.get('observed') != self.state['observed'] or
                           evidence.get('backup') != self.state['backup'] or
                           checked < datetime.fromisoformat(self.state['preparedAt'])):
            raise ValueError('Validation antérieure ou images différentes')

    def prepare(self, evidence):
        self.attest(evidence, ['restore-five-databases-and-documents', 'https-certificate', 'storage-provisioned'])
        self.state['prerequisites'] = evidence
        self.save()
        self.operation('preflight', self.backend.preflight, self.plan)
        self.operation('verify-images', self.backend.images, self.plan)
        self.state['previous'] = self.operation('snapshot', self.backend.snapshot, self.plan)
        self.save()
        self.deploy_bundle()

    def deploy_bundle(self):
        self.operation('close-edge', self.backend.close)
        self.operation('storage', self.backend.storage)
        self.state['backup'] = self.operation('backup', self.backend.backup)
        self.state['completed'] = []
        self.state['observed'] = {}
        self.state.pop('validation', None)
        self.save()
        for component in ORDER:
            self.event('deploy-' + component, 'START')
            self.state['mutationStarted'] = True
            self.save()
            self.backend.deploy(component, self.plan, 'closed')
            self.backend.healthy(component)
            self.state['observed'][component] = self.backend.observed(component, self.plan)
            self.state['completed'].append(component)
            self.save()
            self.event('deploy-' + component, 'OK')
        self.operation('runtime-checks', self.backend.checks)
        self.operation('closed-route', self.backend.route, 'closed')
        self.backend.allow_notes()  # Cohorte prête : API Notes commune ERP disponible, PWA encore fermée.
        self.state['preparedAt'] = now()
        self.state['closureConfirmed'] = True
        self.state['phase'] = 'prepared'
        self.save()

    def resume(self, evidence=None):
        self.require_phase(('preparing', 'failed'))
        evidence = evidence if evidence is not None else self.state.get('prerequisites')
        self.attest(evidence, ['restore-five-databases-and-documents', 'https-certificate', 'storage-provisioned'])
        self.state['prerequisites'] = evidence
        self.save()
        self.operation('close-edge', self.backend.close)
        self.state['closureConfirmed'] = True
        self.state['phase'] = 'preparing'
        self.save()
        self.operation('preflight', self.backend.preflight, self.plan)
        self.operation('verify-images', self.backend.images, self.plan)
        if self.state['previous'] is None:
            self.state['previous'] = self.operation('snapshot', self.backend.snapshot, self.plan)
            self.save()
        self.deploy_bundle()  # Snapshot initial préservé ; nouvelle preuve fonctionnelle obligatoire.

    def abandon(self):
        self.require_phase(('preparing', 'failed', 'rolled-back', 'rollback-failed'))
        self.operation('close-edge', self.backend.close, True)
        if self.state['mutationStarted'] and self.state['phase'] != 'rolled-back':
            raise ValueError('Rollback complet requis avant abandon')
        self.state['phase'] = 'abandoned'
        self.state['closureConfirmed'] = True
        self.save()
        write_json(self.directory / ('archive-' + self.state['run'] + '.json'), self.state)
        self.event('abandon-reservation', 'OK')
        self.reservation.unlink()
        operation.sync_directory(self.reservation.parent)

    def validate(self, evidence):
        self.require_phase(('prepared',))
        self.attest(evidence, self.plan['requiredChecks'], functional=True)
        self.verify_current()
        self.operation('runtime-checks', self.backend.checks)
        self.operation('closed-route', self.backend.route, 'closed')
        self.state['validation'] = evidence
        self.state['phase'] = 'validated'
        self.save()

    def verify_current(self):
        for component in ORDER:
            self.backend.healthy(component)
            if self.backend.observed(component, self.plan) != self.state['observed'][component]:
                raise ValueError('Images runtime différentes de la validation')

    def activate(self):
        self.require_phase(('validated',))
        self.attest(self.state['validation'], self.plan['requiredChecks'], functional=True)
        self.operation('preflight', self.backend.preflight, self.plan)
        self.operation('verify-images', self.backend.images, self.plan)
        self.operation('storage', self.backend.storage)
        self.verify_current()
        self.operation('closed-route', self.backend.route, 'closed')
        if self.state.get('closureConfirmed') is not True:
            raise ValueError('ALERTE : fermeture edge non confirmée')
        self.state['phase'] = 'activating'
        self.save()
        # Les précontrôles peuvent avoir consommé la durée de validité restante.
        self.attest(self.state['validation'], self.plan['requiredChecks'], functional=True)
        self.backend.deploy('erp-shell', self.plan, 'open')
        # Une expiration pendant la recréation déclenche immédiatement la fermeture.
        self.attest(self.state['validation'], self.plan['requiredChecks'], functional=True)
        # Le conteneur Shell est recréé ; son ID change, son image doit rester identique.
        self.backend.healthy('erp-shell')
        self.backend.observed('erp-shell', self.plan)
        self.operation('runtime-checks', self.backend.checks)
        self.attest(self.state['validation'], self.plan['requiredChecks'], functional=True)
        expiry = datetime.fromisoformat(self.state['validation']['checkedAt']) + timedelta(days=1)
        self.backend.open_edge(expiry.isoformat())
        self.operation('opened-route', self.backend.route, 'opened')
        for component in ORDER[:-1]:
            if self.backend.observed(component, self.plan) != self.state['observed'][component]:
                raise ValueError('Composant modifié pendant activation')
        self.attest(self.state['validation'], self.plan['requiredChecks'], functional=True)
        self.backend.record(self.plan)
        self.attest(self.state['validation'], self.plan['requiredChecks'], functional=True)
        self.state['phase'] = 'active'
        self.save()

    def rollback(self):
        self.require_phase(('preparing', 'prepared', 'validated', 'activating', 'active', 'failed', 'rollback-failed', 'rolling-back'))
        previous = self.state['previous']
        config.bundle.validate(previous)
        self.backend.close(True)
        self.backend.images(previous)
        self.state['phase'] = 'rolling-back'
        self.state['rollbackCompleted'] = []
        self.save()
        failed = False
        for component in ORDER:
            if component == 'erp-shell' and failed:
                break  # Ne jamais remettre de point d'entrée public sur un rollback partiel.
            try:
                self.event('rollback-' + component, 'START')
                if component == 'erp-shell':
                    self.backend.deploy(component, previous, 'stopped')
                    self.backend.stopped_shell(previous)
                else:
                    self.backend.deploy(component, previous, 'closed')
                    self.backend.healthy(component)
                    self.backend.observed(component, previous)
                self.state['rollbackCompleted'].append(component)
                self.save()
                self.event('rollback-' + component, 'OK')
            except Exception:
                failed = True
                self.event('rollback-' + component, 'FAILED')
        # Le vieux code ne peut pas écraser des métadonnées documentaires : aucun accès public.
        self.backend.close()
        self.state['phase'] = 'rollback-failed' if failed else 'rolled-back'
        self.save()
        if failed:
            raise ValueError('Rollback incomplet ; reprise nécessaire')

    def run(self, action, evidence=None, run_id=None):
        with GlobalLock(self.lock) as fd:
            self.backend.lock_fd = fd
            if self.reservation.is_symlink():
                raise ValueError('Réservation invalide : intervention explicite requise')
            reserved = private_json(self.reservation) if self.reservation.exists() else None
            owner = run_id or (self.state['run'] if self.state else None)
            if action == 'prepare':
                if reserved:
                    raise ValueError('Réservation persistante : reprise/abandon explicite requis')
                owner = uuid.uuid4().hex
            elif not reserved or not owner or reserved['run'] != owner or reserved['planHash'] != fingerprint(self.plan):
                raise ValueError('Identité de réservation incorrecte')
            if not re.fullmatch(r'[a-f0-9]{32}', owner):
                raise ValueError('Identifiant de réservation invalide')
            self.run_id = self.backend.run_id = owner
            self.backend.guard(self.plan)  # Host refusal/concurrent invocation never closes another release.
            if action == 'prepare':
                operation.atomic_json(self.reservation, {'run':owner,'planHash':fingerprint(self.plan),'createdAt':now()})
            try:
                if action == 'prepare':
                    self.state = {'run':owner,'planHash':fingerprint(self.plan),'phase':'preparing',
                                  'previous':None,'completed':[],'observed':{},'createdAt':now(),
                                  'configurationHash':self.backend.identity(),'closureConfirmed':False,'mutationStarted':False}
                    self.save()
                elif self.state is None:
                    self.state = private_json(self.path)
                self.event(action, 'START')
                if isinstance(evidence, (str, Path)):
                    evidence = private_json(evidence)
                if action in ('prepare', 'validate', 'resume'):
                    getattr(self, action)(evidence)
                else:
                    getattr(self, action)()
                self.event(action, 'OK')
            except BaseException:
                confirmed = False
                try:
                    self.backend.close(action in ('rollback', 'abandon'))
                    confirmed = True
                    self.event(action, 'CLOSED')
                except BaseException:
                    self.event(action, 'CLOSE_FAILED')
                    print('ALERTE : FERMETURE EDGE NON CONFIRMÉE ; ACTIVATION INTERDITE ; RÉSERVATION CONSERVÉE.', file=sys.stderr)
                if self.state:
                    self.state['closureConfirmed'] = confirmed
                    self.state['phase'] = 'rollback-failed' if action == 'rollback' else 'failed'
                    self.save()
                self.event(action, 'FAILED')
                raise


class DockerBackend:
    def __init__(self, env_path, directory):
        self.env_path = Path(env_path)
        self.directory = Path(directory)
        self.lock_fd = None
        self.current_plan = None
        self.run_id = None
        self.gate = edge.Gate(self.directory / 'edge.json')

    def identity(self):
        paths = [ROOT / 'docker-compose.preprod.yml', ROOT / 'versions/preprod.env',
                 ROOT / 'versions/preprod.digests', self.env_path]
        paths += sorted((ROOT / 'scripts').glob('*'))
        paths += sorted(HERE.parent.glob('*.yml')) + sorted(HERE.parent.glob('*.conf'))
        paths += sorted(HERE.parent.glob('*.json')) + sorted(HERE.glob('*.py')) + sorted(HERE.glob('*.sh'))
        return fingerprint({str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()})

    def command(self, args, env=None, combined=False):
        result = subprocess.run(args, env=env, capture_output=True, timeout=900,
                                pass_fds=(() if self.lock_fd is None else (self.lock_fd,)))
        if result.returncode:
            raise ValueError('Commande runtime refusée')
        return result.stdout + (result.stderr if combined else b'')

    def select(self, plan):
        self.current_plan = plan
        write_json(self.directory / 'runtime-plan.json', plan)

    def helper(self, action, *args):
        env = dict(os.environ, PWA_RELEASE_ENV=str(self.env_path),
                   PWA_RELEASE_PLAN=str(self.directory / 'runtime-plan.json'),
                   PWA_RELEASE_LOCK_FD=str(self.lock_fd), PWA_RELEASE_RUN=self.run_id, PYTHONDONTWRITEBYTECODE='1',
                   WAVY_PREPROD_LOCK_FD=str(self.lock_fd))
        self.command(['bash', str(HERE / 'runtime-action.sh'), action, *args], env)

    def guard(self, plan):
        self.select(plan)
        self.helper('host')

    def preflight(self, plan):
        self.select(plan)
        self.helper('guard')
        self.helper('https')

    def images(self, plan):
        config.bundle.validate(plan)
        host_platform = self.command(['docker', 'version', '--format', '{{.Server.Os}}/{{.Server.Arch}}']).decode().strip()
        if any(image['platform'] != host_platform for image in plan['images'].values()):
            raise ValueError('Plateforme du daemon incompatible')
        for component, expected in plan['images'].items():
            actual = self.image(expected['reference'])
            if expected['reference'] not in actual.get('RepoDigests', []):
                raise ValueError('RepoDigest absent')
            config.bundle.validate_labels(component, expected, actual['Config'].get('Labels') or {})
            if actual['Os'] + '/' + actual['Architecture'] != expected['platform']:
                raise ValueError('Plateforme incompatible')

    def image(self, ref):
        return json.loads(self.command(['docker', 'image', 'inspect', ref]))[0]

    def container(self, component):
        actual = json.loads(self.command(['docker', 'inspect', 'wavy-' + component + '-preprod']))[0]
        labels = actual['Config'].get('Labels') or {}
        if labels.get('com.docker.compose.project') != 'wavy-preprod' or labels.get('com.docker.compose.service') != 'wavy-' + component + '-preprod':
            raise ValueError('Conteneur hors PREPROD')
        return actual

    def snapshot(self, plan):
        previous = json.loads(json.dumps(plan))
        for component in ORDER:
            container = self.container(component)
            image = self.image(container['Image'])
            prefix = 'ghcr.io/fabffo/wavy-' + component + '@'
            refs = [ref for ref in image.get('RepoDigests', []) if ref.startswith(prefix)]
            if len(refs) != 1:
                raise ValueError('Snapshot non reproductible')
            labels = image['Config']['Labels']
            version = labels['org.opencontainers.image.version'] + '-' + labels['org.opencontainers.image.revision']
            history = ROOT / 'versions/history/preprod' / (component + '.tsv')
            matches = [line.split('\t') for line in history.read_text().splitlines()[1:]
                       if line.split('\t')[0] == version]
            digest = refs[0].split('@')[1]
            if not matches or any(row[1] != digest for row in matches):
                raise ValueError('Rollback absent ou contradictoire dans historique')
            previous['images'][component] = {'version': version, 'digest': digest, 'reference': refs[0],
                                              'ociLabels': {k: labels[k] for k in ('org.opencontainers.image.version', 'org.opencontainers.image.revision', 'org.opencontainers.image.source')}, 'platform': image['Os'] + '/' + image['Architecture']}
        config.bundle.validate(previous)
        return previous

    def close(self, readonly=False):
        # Écrit la fermeture AVANT le moindre probe ; un échec laisse un latch persistant.
        readonly = readonly or self.gate.read().get('notesReadonly') is True
        self.gate.close(self.run_id, readonly)
        self.route('closed')  # TLS, 404 et marqueur edge, indépendamment du Shell.
        self.gate.confirm_closed()

    def allow_notes(self):
        self.gate.allow_notes(self.run_id)

    def open_edge(self, expiry):
        self.gate.open(self.run_id, expiry)

    def storage(self):
        self.helper('storage')

    def backup(self):
        base = ROOT / 'backups/preprod'
        before = set(base.glob('????????T??????Z-*'))
        self.helper('backup')
        created = set(base.glob('????????T??????Z-*')) - before
        if len(created) != 1:
            raise ValueError('Lot de sauvegarde non identifiable')
        folder = created.pop()
        manifest = folder / 'manifest.json'
        return {'directory': str(folder.relative_to(ROOT)),
                'manifestSha256': hashlib.sha256(manifest.read_bytes()).hexdigest()}

    def deploy(self, component, plan, mode):
        self.select(plan)
        compose_mode = 'closed' if mode == 'stopped' else mode
        if mode == 'stopped' and component != 'erp-shell':
            raise ValueError('Seul le Shell est restauré arrêté')
        config.validate(self.env_path, plan, compose_mode)
        cmd, env = config.compose_args(self.env_path,
            ['up', '--no-start' if mode == 'stopped' else '-d', '--no-deps', '--no-build', '--force-recreate', '--pull', 'never',
             'wavy-' + component + '-preprod'], plan, compose_mode)
        self.command(cmd, env)

    def healthy(self, component):
        self.helper('wait', component)
        if component == 'factures-api':
            started = self.container(component)['State']['StartedAt']
            logs = self.command(['docker', 'logs', '--since', started, 'wavy-factures-api-preprod'], combined=True)
            if re.search(rb'checksum mismatch|Validate failed|migration failed|FlywayValidateException|FlywayMigrateException', logs, re.I):
                raise ValueError('Validation Flyway en échec')

    def observed(self, component, plan):
        container = self.container(component)
        expected = plan['images'][component]['reference']
        if container['Config']['Image'] != expected or container['Image'] != self.image(expected)['Id']:
            raise ValueError('Image active non conforme')
        if not container['State']['Running'] or container['State'].get('Health', {}).get('Status') != 'healthy':
            raise ValueError('Service non healthy')
        return {'reference': expected, 'imageId': container['Image'], 'containerId': container['Id']}

    def stopped_shell(self, plan):
        container = self.container('erp-shell')
        expected = plan['images']['erp-shell']['reference']
        if (container['State']['Running'] or container['Config']['Image'] != expected or
                container['Image'] != self.image(expected)['Id']):
            raise ValueError('Shell de rollback non conforme ou non fermé')

    def checks(self):
        self.helper('checks')

    def route(self, mode):
        self.helper(mode)

    def record(self, plan):
        # Append-only après TOUS les contrôles du lot, jamais avant validation runtime.
        for component in ORDER:
            image = plan['images'][component]
            self.helper('record', component, image['version'], image['digest'],
                        image['ociLabels']['org.opencontainers.image.revision'])
        fd = os.open(self.directory / 'validated-bundles.jsonl', os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'a') as stream:
            stream.write(json.dumps({'time': now(), 'images': {c: {'version': i['version'], 'digest': i['digest']}
                                                              for c, i in plan['images'].items()}}) + '\n')
            stream.flush()
            os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'validate', 'activate', 'rollback', 'resume', 'abandon'])
    parser.add_argument('--plan', type=Path, default=HERE.parent / 'release-plan.json')
    parser.add_argument('--env', type=Path, default=ROOT / '.env.preprod')
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--run-id', help='Identifiant exact de réservation pour toute reprise/action après prepare')
    parser.add_argument('--execute-on-approved-host', action='store_true')
    args = parser.parse_args()
    if not args.execute_on_approved_host:
        parser.exit(2, 'Candidat inactif : exécution runtime non demandée.\n')
    # AVANT création d'état/verrou ou commande Docker. Aucun override distant autorisé.
    if socket.gethostname().split('.')[0] != 'wavy-preprod' or os.environ.get('DOCKER_HOST') or os.environ.get('DOCKER_CONTEXT'):
        parser.exit(2, 'Hôte PREPROD local approuvé requis.\n')
    if args.action != 'prepare' and not args.run_id:
        parser.exit(2, 'Identifiant de réservation --run-id requis.\n')
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: (_ for _ in ()).throw(InterruptedError()))
    try:
        plan = config.read_plan(args.plan)
        directory = ROOT / 'deployments/pwa-release'
        backend = DockerBackend(args.env.resolve(), directory)
        engine = Engine(backend, directory, plan, ROOT / 'deployments/preprod.lock')
        engine.run(args.action, args.evidence, args.run_id)
        print('Opération candidate terminée ; consulter le journal privé du lot.')
    except BaseException:
        parser.exit(1, 'Opération refusée ou échouée ; vérifier état privé et fermeture du Shell. Aucun détail secret affiché.\n')


if __name__ == '__main__':
    main()
