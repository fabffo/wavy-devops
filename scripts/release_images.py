#!/usr/bin/env python3
"""Références de release partagées par les chemins Compose existants."""
import json
import fcntl
import stat
from contextlib import contextmanager
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile

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


def release(root, env, components=None):
    versions = manifest(root / f'versions/{env}.env')
    digests = manifest(root / f'versions/{env}.digests')
    images = {}
    for component in COMPONENTS if components is None else components:
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
                if not line.strip(): continue
                fields = line.split('\t')
                if len(fields) < 2:
                    raise ValueError(f'Historique invalide : {env}/{component}')
                if fields[0] == version and fields[1] != digest:
                    raise ValueError(f'Digest incompatible avec la release {env}/{component}/{version}')
        images[component] = f"{versions['WAVY_IMAGE_REGISTRY']}/wavy-{component}:{version}@{digest}"
    return versions, digests, images


def verify(root, env, references=None):
    _, _, images = release(root, env)
    if references is not None:
        images = references
    # Vérifier l'ensemble avant toute recréation, même pour une commande ciblée.
    for component, pinned in images.items():
        tag, expected = pinned.split('@')
        if env == 'recette':
            # Le digest est l'autorité ; un tag mutable ne doit pas décider du
            # contenu installé. Réutiliser une image épinglée déjà vérifiable
            # évite un second téléchargement après la sauvegarde.
            result = subprocess.run(['docker','image','inspect',pinned],capture_output=True,text=True)
            if result.returncode:
                subprocess.run(['docker','pull',pinned],check=True,stdout=subprocess.DEVNULL)
                result = subprocess.run(['docker','image','inspect',pinned],check=True,capture_output=True,text=True)
            repo = tag.rsplit(':',1)[0]
            if repo+'@'+expected not in json.loads(result.stdout)[0].get('RepoDigests',[]):
                raise ValueError(f'Digest incompatible avec la release {env}/{component}')
            continue
        subprocess.run(['docker', 'pull', tag], check=True, stdout=subprocess.DEVNULL)
        result = subprocess.run(['docker', 'image', 'inspect', tag], check=True,
                                capture_output=True, text=True)
        repo = tag.rsplit(':', 1)[0]
        if repo+'@'+expected not in json.loads(result.stdout)[0].get('RepoDigests', []):
            raise ValueError(f'Digest incompatible avec la release {env}/{component} : {tag}, attendu {expected}')
        subprocess.run(['docker', 'pull', pinned], check=True, stdout=subprocess.DEVNULL)


def historical_image(root, component, version, registry):
    if component not in COMPONENTS or not re.fullmatch(r'\d+\.\d+\.\d+-[0-9a-f]{7,40}', version):
        raise ValueError('Cible historique RECETTE invalide')
    path = root/f'versions/history/recette/{component}.tsv'
    rows = [line.split('\t') for line in path.read_text().splitlines()[1:]]
    digests = {row[1] for row in rows if len(row)>1 and row[0]==version}
    if len(digests)!=1 or not re.fullmatch(r'sha256:[0-9a-f]{64}', next(iter(digests),'')):
        raise ValueError('Aucun digest historique unique validé pour la cible RECETTE')
    return f'{registry}/wavy-{component}:{version}@{next(iter(digests))}'


@contextmanager
def recette_operation(root, mutation):
    if not mutation:
        yield
        return
    path = root/'deployments/recette.lock'
    path.parent.mkdir(exist_ok=True)
    if path.is_symlink():
        raise ValueError('Verrou RECETTE symbolique refusé')
    inherited = os.environ.get('WAVY_RECETTE_LOCK_FD')
    fd = int(inherited) if inherited else os.open(path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        obj = os.fstat(fd)
        if not stat.S_ISREG(obj.st_mode) or obj.st_uid!=os.getuid() or not os.path.samestat(obj,path.stat()):
            raise ValueError('Verrou RECETTE hérité invalide')
        try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('Une opération RECETTE est déjà en cours') from None
        yield
    finally:
        if not inherited: os.close(fd)


def recette_compose(root, args, rollback=None, capture=False):
    with recette_operation(root,args[0] in ('up','create','run','stop','down','restart','kill','pause','unpause','exec')):
        return _recette_compose(root,args,rollback,capture)


def migration_services(root, args, images, overlay, rollback):
    from delivery_batch import SESSION_KEY, validate_session

    if rollback or args[0] != 'up' or '--wait' not in args or SESSION_KEY not in os.environ:
        return []
    before = validate_session(root, 'recette')['before']
    services = []
    for component, image in images.items():
        if not component.endswith('-api'):
            continue
        service = f'wavy-{component}-recette'
        environment = overlay.get('services', {}).get(service, {}).get('environment', {})
        # Le Compose standard des environnements sans politique de reproduction
        # laisse déjà Spring démarrer Flyway normalement.
        if environment.get('SPRING_FLYWAY_ENABLED') != 'false':
            continue
        if before[component]['reference'].partition('@')[2] == image.partition('@')[2]:
            continue
        image_id = subprocess.check_output(['docker', 'image', 'inspect', '-f', '{{.Id}}', image], text=True).strip()
        if image_id != before[component]['id']:
            services.append(service)
    return services


def compose_with_migrations(command, args, env, directory, services):
    # Ces conteneurs n'ont pas vocation à rester actifs une fois le schéma prêt.
    label = f'fr.wavy.delivery.migration={directory.name}'
    migration = directory/'migration.json'
    migration.write_text(json.dumps({'services': {
        service: {'environment': {'SPRING_FLYWAY_ENABLED': 'true'},
                  'restart': 'no', 'labels': [label]}
        for service in services
    }}))

    def interrupted(signum, _frame):
        raise SystemExit(128 + signum)

    previous = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGINT, signal.SIGTERM)}
    completed = False
    try:
        result = subprocess.run([*command, '-f', str(migration), *args, '--no-deps', *services], env=env)
        if result.returncode:
            return result.returncode
        result = subprocess.run([*command, *args], env=env)
        completed = result.returncode == 0
        return result.returncode
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        if not completed:
            containers = subprocess.check_output(['docker', 'ps', '-aq', '--filter', f'label={label}'], text=True).split()
            if containers:
                subprocess.run(['docker', 'rm', '-f', *containers], check=True)


def _recette_compose(root, args, rollback=None, capture=False):
    from recette_pwa import overlay, literal
    versions, digests, images = release(root, 'recette')
    if rollback:
        component, version = rollback
        images[component] = historical_image(root,component,version,versions['WAVY_IMAGE_REGISTRY'])
        key = component.upper().replace('-','_')
        versions[key+'_VERSION'] = version
        digests[key+'_DIGEST'] = images[component].split('@')[1]
    machine = manifest(root / '.env.recette', strict=False)
    pwa = overlay(root, machine, images, mutation=args[0] in ('up', 'create', 'run'),
                  enforce=args[0] not in ('stop', 'down', 'ps', 'logs', 'images', 'restart', 'kill', 'pause', 'unpause', 'exec', 'version', 'config'))
    # Même moteur Compose ; politique de reproduction persistante après synchronisation.
    from sync_recette import sync_overlay
    pwa = sync_overlay(root, pwa, mutation=args[0] in ('up', 'create', 'run', 'restart', 'unpause'))
    raw = (root / 'docker-compose.recette.yml').read_text()
    keys = set(re.findall(r'\$\{([A-Z][A-Z0-9_]*)', raw))
    clean = {k: v for k, v in os.environ.items() if k not in keys and not k.startswith('COMPOSE_')}
    # Les manifestes ont priorité sur le shell et le dotenv machine.
    clean.update(versions)
    clean.update(digests)
    if (root/'deployments/recette-sync-policy.json').exists():
        # La même entrée locale que le tunnel Windows, sans modifier le dotenv.
        clean['WAVY_RECETTE_PRIVATE_BIND_ADDRESS'] = '127.0.0.1'
        clean['WAVY_ERP_SHELL_HOST_PORT'] = '24207'
    if args[0] == 'build':
        print('RECETTE : commande build historique → téléchargement des images validées.', flush=True)
        if rollback: verify(root,'recette',images)
        else: verify(root,'recette')
        return 0
    if args[0] in ('up', 'create', 'run'):
        if '--build' in args:
            raise ValueError('Build interdit en RECETTE ; utiliser les images de release.')
        if rollback: verify(root,'recette',images)
        else: verify(root,'recette')
        args = [args[0], '--no-build', *args[1:]]
    migrations = [] if capture else migration_services(root, args, images, pwa, rollback)
    # Seul le fichier Compose intermédiaire est temporaire ; tous les bind mounts
    # pointent sur les fichiers persistants versionnés du dépôt, jamais sur /tmp.
    with tempfile.TemporaryDirectory(prefix='wavy-recette-compose-') as temporary:
        override = Path(temporary)/'pwa.json'
        override.write_text(json.dumps(pwa))
        command = ['docker', 'compose', '--env-file', str(root / '.env.recette'),
                   '--env-file', str(root / 'versions/recette.env'),
                   '--env-file', str(root / 'versions/recette.digests'),
                   '-p', literal(machine.get('COMPOSE_PROJECT_NAME', 'wavy-recette')),
                   '-f', str(root / 'docker-compose.recette.yml'), '-f', str(override)]
        if migrations:
            return compose_with_migrations(command, args, clean, Path(temporary), migrations)
        result = subprocess.run([*command, *args], env=clean,
                                **({'capture_output': True, 'text': True} if capture else {}))
        if capture:
            if result.returncode:
                raise ValueError('Rendu Compose RECETTE refusé (sortie masquée)')
            return json.loads(result.stdout)
        return result.returncode



if __name__ == '__main__':
    try:
        root = Path(__file__).resolve().parent.parent
        if sys.argv[1] == 'recette-rollback':
            if len(sys.argv)<5: raise ValueError('Cible et commande rollback RECETTE requises')
            raise SystemExit(recette_compose(root,sys.argv[4:],rollback=(sys.argv[2],sys.argv[3])))
        elif sys.argv[1] == 'verify':
            verify(root, sys.argv[2])
        else:
            raise SystemExit(recette_compose(root, sys.argv[1:]))
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        print(f'ERREUR release images : {exc}', file=sys.stderr)
        sys.exit(1)
