#!/usr/bin/env python3
"""Synchronisation ponctuelle, sur RECETTE ; primitives de backup et Compose existantes."""
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone

sys.dont_write_bytecode = True
from delivery_batch import locked, backup_folders
from preprod_operation import atomic_json, read_private
from preprod_config import dotenv
from preprod_backup_manifest import DATABASES, run as authenticate
from preprod_document_archive import validate as validate_source_documents
from recette_documents import verify as verify_recette
from release_images import COMPONENTS, release, recette_compose, verify
from delivery_check import machine
from recette_pwa import policy as pwa_policy

ROOT = Path(__file__).resolve().parent.parent
STATE = 'deployments/recette-sync.json'
POLICY = 'deployments/recette-sync-policy.json'
SUCCESS = {'complete', 'rolled-back', 'cancelled'}
SOURCE_FILES = {db+'.dump.enc' for db in DATABASES} | {'documents.tar.enc', 'manifest.json', 'source.json'}
REMOTE_PHASES = {'preprod-preflight', 'preprod-backup', 'preprod-resume',
                 'preprod-finalize', 'preprod-snapshot', 'preprod-transfer'}
RUNTIME_CONTAINERS = ['wavy-'+c+'-recette' for c in COMPONENTS] + [db+'-db-recette' for db in DATABASES]
SHELL_UPSTREAMS = {'API_UPSTREAM': 'http://wavy-gateway-recette:8088',
                   **{c.upper()+'_UPSTREAM': 'http://wavy-'+c.lower().replace('_','-')+'-recette/'
                      for c in ('SOCLE_FRONT', 'TIERS_FRONT', 'CONTRATS_FRONT', 'FACTURES_FRONT', 'TRESORERIE_FRONT')}}


def sync_restart_policy(root):
    path = root/STATE
    if path.exists():
        state = read_private(path)
        if state.get('phase') == 'complete' and not state.get('failure'):
            return 'unless-stopped'
    return 'no'

def require(ok, message):
    if not ok:
        raise ValueError(message)


def command(args, **kwargs):
    # Docker/SQL/Compose peuvent exposer des secrets : jamais recopier leurs sorties.
    return subprocess.run([str(x) for x in args], check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, **kwargs).stdout


def inspect(name, kind='container'):
    return json.loads(command(['docker', kind, 'inspect', name]))[0]


def environment(obj):
    return dict(x.split('=', 1) for x in obj['Config'].get('Env', []) if '=' in x)


def same_reference(actual, expected):
    tag, digest = expected.split('@')
    # Le chemin PREPROD existant recrée par repository@digest, RECETTE par tag@digest.
    return actual in (expected, tag.rsplit(':', 1)[0]+'@'+digest)


def snapshot(env):
    result = {}
    for component in COMPONENTS:
        obj = inspect(f'wavy-{component}-{env}')
        require(obj['Config']['Labels'].get('com.docker.compose.project') == 'wavy-'+env,
                'Conteneur hors projet : '+component)
        require(obj['State']['Running'], 'Service arrêté : '+component)
        require(not obj['HostConfig'].get('Privileged') and not obj['HostConfig'].get('NetworkMode') == 'host',
                'Conteneur privilégié ou réseau host refusé')
        result[component] = {'reference': obj['Config']['Image'], 'id': obj['Image'],
                             'restart': obj['HostConfig']['RestartPolicy']}
    return result


def declared_snapshot(root, env):
    versions, digests, images = release(root, env)
    current = snapshot(env)
    for c in COMPONENTS:
        require(same_reference(current[c]['reference'], images[c]), 'Image active différente du manifeste : '+c)
    return {'versions': versions, 'digests': digests, 'images': images, 'runtime': current}


def psql(db, sql, environment_name='recette'):
    name = db+'-db-'+environment_name
    obj = inspect(name)
    require(obj['Config']['Labels'].get('com.docker.compose.project') == 'wavy-'+environment_name, 'Base hors environnement')
    env = environment(obj)
    return command(['docker', 'exec', '-i', name, 'psql', '-X', '-v', 'ON_ERROR_STOP=1',
                    '-U', env['POSTGRES_USER'], '-d', env['POSTGRES_DB'], '-qAt'], input=sql.encode())


def shared_database_guard(environment_name='recette'):
    # Les routages tenant dédiés contiennent une configuration d'environnement.
    # Ne jamais les recopier aveuglément, ni remapper des tenants par simple ID.
    count = psql('socle', "SELECT (SELECT count(*) FROM tenant WHERE base_dediee OR cle_base_donnee IS NOT NULL) + "
                  "(SELECT count(*) FROM tenant_base_donnee WHERE "
                  "hote IS NOT NULL OR port IS NOT NULL OR nom_base IS NOT NULL OR nom_schema IS NOT NULL);", environment_name)
    require(count.strip() == b'0', 'Routage tenant dédié : synchronisation automatique refusée')


def database_guard(environment_name):
    for db in DATABASES:
        count = psql(db, "SELECT count(*) FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' "
                    "AND nspname NOT IN ('public','information_schema');", environment_name)
        require(count.strip() == b'0', 'Schéma PostgreSQL supplémentaire non pris en charge : '+db)
        version = psql(db, "SELECT current_setting('server_version_num')::int / 10000;", environment_name)
        require(version.strip() == b'16', 'PostgreSQL 16 requis : '+db)


def source_export(root):
    phase = 'preprod-preflight'
    try:
        require(socket.gethostname().split('.')[0] == 'wavy-preprod', 'Export réservé à wavy-preprod')
        with locked(root, 'preprod') as (fd, env):
            database_guard('preprod'); shared_database_guard('preprod')
            before = declared_snapshot(root, 'preprod')
            folders = backup_folders(root, 'preprod')
            phase = 'preprod-backup'
            # Le backup existant garde ses contrôles host, réservations et reprise des writers.
            subprocess.run(['bash', str(root/'scripts/backup-preprod.sh')], env=env,
                           pass_fds=(fd,), stdout=sys.stderr, check=True)
            phase = 'preprod-snapshot'
            added = backup_folders(root, 'preprod') - folders
            require(len(added) == 1, 'Lot PREPROD non identifiable')
            require(declared_snapshot(root, 'preprod') == before, 'Images PREPROD modifiées pendant la capture')
            folder = added.pop()
            before['capturedAt'] = datetime.now(timezone.utc).isoformat()
            data = json.dumps(before).encode()
            phase = 'preprod-transfer'
            with tarfile.open(fileobj=sys.stdout.buffer, mode='w|') as archive:
                for name in sorted(SOURCE_FILES - {'source.json'}):
                    archive.add(folder/name, arcname=name, recursive=False)
                member = tarfile.TarInfo('source.json'); member.size = len(data); member.mode = 0o600
                archive.addfile(member, io.BytesIO(data))
    except Exception as exc:
        code = exc.returncode if isinstance(exc, subprocess.CalledProcessError) else 1
        print(f'WAVY_SYNC_ERROR phase={phase} code={code}', file=sys.stderr)
        raise


def source_ssh(values, action):
    host = values.get('WAVY_SYNC_PREPROD_SSH', '')
    remote = values.get('WAVY_SYNC_PREPROD_ROOT', '')
    require(re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.@-]*', host) is not None, 'Destination SSH PREPROD absente/invalide')
    require(remote.startswith('/') and '\n' not in remote, 'Checkout distant PREPROD absolu requis')
    return ['ssh', '-n', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=15',
            '--', host, 'cd '+shlex.quote(remote)+' && '+action]


# Le lecteur et le dotenv existent déjà sur PREPROD : aucune installation distante
# requise pour lire le secret, aucune sauvegarde ni écriture déclenchée ici.
REMOTE_KEY_READER = '''import os, socket, stat, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'scripts'))
from preprod_config import dotenv
path = Path('.env.preprod')
info = path.lstat()
if (socket.gethostname().split('.')[0] != 'wavy-preprod'
        or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
        or info.st_mode & 0o077):
    raise ValueError('Configuration PREPROD privée requise')
key = dotenv(path).get('WAVY_BACKUP_ENCRYPTION_PASSPHRASE', '')
if len(key) < 32 or 'CHANGE_ME' in key:
    raise ValueError('Passphrase PREPROD absente ou invalide')
sys.stdout.write(key)
'''


def backup_key(values):
    try:
        raw = command(source_ssh(values, 'python3 -B -c '+shlex.quote(REMOTE_KEY_READER)), timeout=30)
        key = raw.decode('utf-8')
        require(32 <= len(key) <= 65536 and '\n' not in key and '\r' not in key and 'CHANGE_ME' not in key,
                'Passphrase PREPROD invalide')
        return key
    except (subprocess.SubprocessError, UnicodeError, OSError):
        raise ValueError('Lecture sécurisée de la passphrase PREPROD impossible : vérifier que le compte SSH '
                         'configuré peut lire son .env.preprod privé.') from None


def receive(root, values, folder):
    args = source_ssh(values, 'python3 -B scripts/sync_recette.py _export')
    # Pas de copie de dotenv ; SSH transporte seulement les dumps déjà chiffrés et les images.
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=errors)
        transfer_error = False
        try:
            unpack_bundle(process.stdout, folder)
        except (ValueError, OSError, EOFError, tarfile.TarError):
            transfer_error = True
        finally:
            process.stdout.close()
            # Attendre la fin du backup et de son trap de reprise, sans tuer SSH.
            code = process.wait()
        if code != 0 or transfer_error:
            phase, remote_code = ('ssh', code) if code == 255 else ('preprod-export', code)
            if code == 0: phase, remote_code = 'transfer', 1
            errors.seek(0)
            # Ne restituer que des phases connues et des codes numériques, jamais
            # les sorties brutes Docker/OpenSSL, chemins, dotenv ou exceptions.
            markers = []
            for line in errors:
                match = re.fullmatch(rb'WAVY_SYNC_ERROR phase=([a-z-]+) code=(-?[0-9]{1,5})\r?\n?', line)
                if match and match[1].decode('ascii') in REMOTE_PHASES and int(match[2]) != 0:
                    markers.append((match[1].decode('ascii'), int(match[2])))
            if markers and code != 255:
                # Le trap Bash indique la sous-phase précise avant le marqueur
                # générique du wrapper Python (preprod-backup).
                phase, remote_code = next((m for m in markers if m[0] in {'preprod-resume', 'preprod-finalize'}), markers[-1])
            raise ValueError(f'Échec distant : phase={phase}, code={remote_code}, ssh_code={code}. '
                             'Aucun remplacement RECETTE.') from None


def unpack_bundle(stream, folder):
    seen = set()
    with tarfile.open(fileobj=stream, mode='r|') as archive:
        for member in archive:
            require(member.name in SOURCE_FILES and member.name not in seen and member.isfile(), 'Lot source invalide')
            require(member.size > 0 and (member.name != 'source.json' or member.size < 131072), 'Taille source invalide')
            seen.add(member.name)
            with (folder/member.name).open('xb') as target:
                shutil.copyfileobj(archive.extractfile(member), target)
    require(seen == SOURCE_FILES, 'Lot source incomplet')


def crypt(source, destination, key, decrypt=False):
    args = ['openssl', 'enc', '-aes-256-cbc', '-pbkdf2', '-pass', 'env:WAVY_BACKUP_PASSPHRASE']
    args += ['-d'] if decrypt else ['-salt']
    command(args + ['-in', source, '-out', destination], env=dict(os.environ, WAVY_BACKUP_PASSPHRASE=key))


def auth(folder, key, env, files=None, action='verify'):
    old = os.environ.get('WAVY_BACKUP_PASSPHRASE')
    os.environ['WAVY_BACKUP_PASSPHRASE'] = key
    try:
        authenticate(action, folder, environment=env, filenames=files)
    finally:
        if old is None: os.environ.pop('WAVY_BACKUP_PASSPHRASE', None)
        else: os.environ['WAVY_BACKUP_PASSPHRASE'] = old


def validate_tar(path):
    with tarfile.open(path) as archive:
        seen = set()
        for entry in archive:
            name = entry.name
            while name.startswith('./'): name = name[2:]
            name = name.rstrip('/') or '.'
            parts = Path(name).parts
            require(not name.startswith('/') and '..' not in parts and name not in seen and
                    (entry.isfile() or entry.isdir()) and not entry.mode & 0o7000,
                    'Archive documentaire dangereuse')
            seen.add(name)


def volume_for(component, destination):
    obj = inspect('wavy-'+component+'-recette')
    matches = [m for m in obj['Mounts'] if m['Destination'] == destination]
    require(len(matches) == 1 and matches[0]['Type'] == 'volume', 'Volume documentaire absent : '+component)
    volume = matches[0]['Name']
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', volume) is not None and 'preprod' not in volume.lower(), 'Volume source interdit')
    info = inspect(volume, 'volume')
    require(info.get('Driver') == 'local' and not info.get('Options'), 'Volume local sans options requis')
    return volume


def db_restore(folder):
    for db in DATABASES:
        env = environment(inspect(db+'-db-recette'))
        # --clean seul conserve les tables spécifiques à l'ancienne version RECETTE.
        # Les identités PostgreSQL et la configuration du serveur restent inchangées.
        psql(db, 'DROP SCHEMA public CASCADE; CREATE SCHEMA public AUTHORIZATION CURRENT_USER;')
        with (folder/(db+'.dump')).open('rb') as stream:
            command(['docker', 'exec', '-i', db+'-db-recette', 'pg_restore', '-U', env['POSTGRES_USER'],
                     '-d', env['POSTGRES_DB'], '--clean', '--if-exists', '--no-owner', '--no-acl',
                     '--exit-on-error', '--single-transaction'], stdin=stream)


def check_dumps(folder):
    for db in DATABASES:
        with (folder/(db+'.dump')).open('rb') as stream:
            command(['docker', 'exec', '-i', db+'-db-recette', 'pg_restore', '--list'], stdin=stream)


def document_restore(path, volume, image):
    validate_tar(path)
    # Noms Docker vérifiés, aucune interpolation de chemin provenant de l'archive.
    with path.open('rb') as stream:
        command(['docker', 'run', '--rm', '-i', '--pull', 'never', '--network', 'none', '--read-only',
                 '--security-opt', 'no-new-privileges:true', '--user', '0:0',
                 '--mount', f'type=volume,source={volume},target=/store,volume-nocopy',
                 '--entrypoint', 'sh', image, '-ec',
                 'find /store -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +; tar -xpf - -C /store'], stdin=stream)


def split_documents(source, target):
    # Retire uniquement la racine PREPROD : chemins relatifs, IDs et contenu conservés.
    with tarfile.open(source) as archive:
        for root, filename in [('contrats', 'contrats.tar'), ('notes-frais', 'justificatifs.tar')]:
            with tarfile.open(target/filename, 'w') as output:
                for member in archive.getmembers():
                    parts = member.name.split('/')
                    if parts[0] != root: continue
                    member.name = '/'.join(parts[1:]) or '.'
                    output.addfile(member, archive.extractfile(member) if member.isfile() else None)


def compose(root, args):
    require(recette_compose(root, args) == 0, 'Commande Compose RECETTE en échec')


def runtime_stop(previous):
    existing = set(command(['docker', 'container', 'ls', '-a', '--format', '{{.Names}}']).decode().splitlines())
    for name in RUNTIME_CONTAINERS:
        if name not in existing: continue
        command(['docker', 'update', '--restart=no', name])
    for c in ['gateway'] + [x for x in COMPONENTS if x != 'gateway']:
        name = 'wavy-'+c+'-recette'
        if name not in existing: continue
        was_running = inspect(name)['State']['Running']
        command(['docker', 'stop', '--time', '60', name])
        require(not was_running or inspect(name)['State']['ExitCode'] != 137, 'Arrêt forcé ; restauration automatique non sûre')


def restart_policies(previous, databases=None):
    policies = {'wavy-'+c+'-recette': item['restart'] for c, item in previous.items()}
    policies.update({db+'-db-recette': policy for db, policy in (databases or {}).items()})
    for container, policy in policies.items():
        name = policy['Name'] or 'no'
        if name == 'on-failure' and policy.get('MaximumRetryCount'): name += ':'+str(policy['MaximumRetryCount'])
        command(['docker', 'update', '--restart='+name, container])


def activate_restarts(root):
    require(sync_restart_policy(root) == 'unless-stopped', 'Redémarrage automatique interdit avant validation complète')
    command(['docker', 'update', '--restart=unless-stopped', *RUNTIME_CONTAINERS])


def write_versions(root, data):
    for filename, key in [('recette.env', 'versions'), ('recette.digests', 'digests')]:
        path = root/'versions'/filename
        temporary = path.with_suffix(path.suffix+'.sync-tmp')
        temporary.write_text(''.join(k+'='+v+'\n' for k,v in data[key].items()))
        os.replace(temporary, path)


def recover(root, state, key, work):
    # Restaurer tout le lot : jamais seulement la base où l'erreur est survenue.
    folder = Path(state['backup'])
    auth(folder, key, 'recette', ['recette.tar.enc'])
    crypt(folder/'recette.tar.enc', work/'recette.tar', key, True)
    unpack_rollback(work/'recette.tar', work)
    check_dumps(work)
    validate_tar(work/'contrats.tar'); validate_tar(work/'justificatifs.tar')
    runtime_stop(state['before']['runtime'])
    db_restore(work)
    for name, volume in state['volumes'].items():
        document_restore(work/(name+'.tar'), volume, state['toolImage'])
    for name, content in state['savedFiles'].items():
        path = root/name
        if content is None: path.unlink(missing_ok=True)
        else: path.write_text(content)
    state['phase'] = 'recovering'; atomic_json(root/STATE, state)
    compose(root, ['up', '-d', '--force-recreate', '--wait', '--wait-timeout', '600'])
    command(['bash', root/'scripts/healthcheck.sh', 'recette'])
    restart_policies(state['before']['runtime'], state.get('databaseRestart'))
    state['phase'] = 'rolled-back'; atomic_json(root/STATE, state)


def unpack_rollback(path, work):
    expected = {x+'.dump' for x in DATABASES} | {'contrats.tar', 'justificatifs.tar'}
    seen = set()
    with tarfile.open(path) as archive:
        for member in archive:
            require(member.isfile() and member.name in expected and member.name not in seen, 'Lot de secours invalide')
            seen.add(member.name)
            with (work/member.name).open('wb') as output:
                shutil.copyfileobj(archive.extractfile(member), output)
    require(seen == expected, 'Lot de secours incomplet')


def safe_recover(root, state, key, work):
    try:
        recover(root, state, key, work)
    except BaseException:
        # Même règle après panne machine et après échec dans le processus courant.
        try: runtime_stop(state['before']['runtime'])
        except BaseException: pass
        state['phase'] = 'recovery-failed'; atomic_json(root/STATE, state)
        raise


def save_rollback(root, backup, target, key):
    verify_recette(backup)
    validate_tar(backup/'contrats.tar')
    with tarfile.open(target/'recette.tar', 'w') as archive:
        for name in [x+'.dump' for x in DATABASES] + ['contrats.tar', 'justificatifs.tar']:
            archive.add(backup/name, arcname=name, recursive=False)
    crypt(target/'recette.tar', target/'recette.tar.enc', key)
    auth(target, key, 'recette', ['recette.tar.enc'], 'sign')
    auth(target, key, 'recette', ['recette.tar.enc'])
    (target/'recette.tar').unlink()
    # Le backup historique est privé ; supprimer le clair seulement après scellement réussi.
    shutil.rmtree(backup)


def check_shell(values):
    """GET internes : Shell -> fronts et Shell -> Gateway -> Tiers, sans session."""
    command(['docker', 'exec', 'wavy-erp-shell-recette', 'nginx', '-t'])

    def get(path, status=200):
        # Curl est déjà présent dans Socle et utilisé par les smoke tests PREPROD.
        payload = command(['docker', 'exec', 'wavy-socle-api-recette', 'curl', '-sS',
                           '--max-time', '10', '--write-out', '\n%{http_code}',
                           'http://wavy-erp-shell-recette'+path])
        body, _, code = payload.rpartition(b'\n')
        require(code == str(status).encode(), 'Statut ERP Shell inattendu : '+path)
        return body

    require(b'<html' in get('/').lower(), 'Page ERP Shell invalide')
    for module in ('socle', 'tiers', 'contrats', 'factures', 'tresorerie'):
        path = '/modules/'+module+'/'
        body = get(path)
        require(b'<html' in body.lower() and
                re.search(rb'<base\s+href=["\x27]'+re.escape(path.encode())+rb'["\x27]', body, re.I),
                'Proxy ERP Shell invalide : '+module)
    health = json.loads(get('/api/tiers/health'))
    require(isinstance(health, dict) and health.get('module') == 'wavy-tiers-api' and health.get('status') == 'OK',
            'Réponse Tiers via ERP Shell/Gateway invalide')
    get('/api/auth/session', status=401)
    enabled = values.get('WAVY_PWA_ENABLED', 'false') == 'true'
    integration = json.loads(get('/pwa-integration.json'))
    require(isinstance(integration, dict) and integration.get('enabled') is enabled, 'Manifeste PWA du Shell incohérent')
    if enabled:
        require(b'<html' in get('/pwa/').lower(), 'Proxy PWA du Shell invalide')
        worker = get('/pwa/ngsw-worker.js')
        require(worker and b'<html' not in worker.lower(), 'Service worker PWA invalide')


def check_shell_ingress():
    # Même point d'entrée que le tunnel SSH Windows ; aucun accès extérieur requis.
    curl = ['curl', '--noproxy', '*', '-fsS', '--max-time', '10', '--retry', '12',
            '--retry-connrefused', '--retry-delay', '1', '--retry-max-time', '30']
    body = command([*curl, 'http://127.0.0.1:24207/'])
    require(b'<html' in body.lower(), 'Entrée HTTP ERP Shell invalide')
    health = json.loads(command([*curl, 'http://127.0.0.1:24207/api/tiers/health']))
    require(isinstance(health, dict) and health.get('module') == 'wavy-tiers-api' and health.get('status') == 'OK',
            'Entrée HTTP Shell/Gateway/Tiers invalide')


def guard_host(root, values):
    require(values.get('WAVY_INSTALL_HOSTNAME') == socket.gethostname().split('.')[0] and
            socket.gethostname().split('.')[0] != 'wavy-preprod', 'Hôte RECETTE non attesté par WAVY_INSTALL_HOSTNAME')
    require(not os.environ.get('DOCKER_HOST') and not os.environ.get('DOCKER_CONTEXT'), 'Override Docker interdit')
    require(command(['docker', 'context', 'inspect', '--format', '{{.Endpoints.docker.Host}}']).strip() == b'unix:///var/run/docker.sock', 'Daemon système local requis')
    require(not (root/'deployments/recette-https-reservation.json').exists() and
            not (Path.home()/'.local/state/wavy/recettelocal/runtime-info.json').exists(), 'RECETTE locale/réservée refusée')


def run(root):
    os.umask(0o077)
    values = machine(root); guard_host(root, values)
    with locked(root, 'recette') as (fd, env):
        key = backup_key(values)
        with tempfile.TemporaryDirectory(prefix='wavy-sync-') as temporary:
            work = Path(temporary)
            if (root/STATE).exists():
                pending = read_private(root/STATE)
                if pending['phase'] not in SUCCESS:
                    require(pending.get('backupVerified'), 'Synchronisation interrompue avant secours validé : reprise opérateur requise')
                    pending['owner'] = os.getpid(); atomic_json(root/STATE, pending)
                    safe_recover(root, pending, key, work)
                    print('Ancien RECETTE restauré ; relancer la commande pour une nouvelle synchronisation.')
                    return
            before = declared_snapshot(root, 'recette')
            pwa = pwa_policy(root, values, before['images'])
            require(pwa['mode'] == 'technical' and pwa['go'],
                    'Prérequis du parcours standard RECETTE technique non satisfaits')
            volumes = {'contrats': volume_for('contrats-api', '/app/data/contrats/pieces-jointes'),
                       'justificatifs': volume_for('factures-api', '/app/justificatifs')}
            require(len(set(volumes.values())) == 2, 'Volumes documentaires distincts requis')
            require(pwa['volume'] == volumes['justificatifs'], 'Volume configuré différent du montage Factures')
            database_guard('recette'); shared_database_guard()
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
            target = root/'backups'/'sync'/timestamp; target.mkdir(parents=True, mode=0o700)
            source = target/'source'; source.mkdir(mode=0o700)
            print('Sauvegarde cohérente PREPROD (interruption temporaire), puis réception chiffrée…', flush=True)
            receive(root, values, source)
            auth(source, key, 'preprod')
            data = json.loads((source/'source.json').read_text())
            # Validation stricte des références avant toute écriture de manifeste.
            require(set(data['versions']) == {'WAVY_IMAGE_REGISTRY'} | {c.upper().replace('-', '_')+'_VERSION' for c in COMPONENTS}
                    and set(data['digests']) == {c.upper().replace('-', '_')+'_DIGEST' for c in COMPONENTS}
                    and data['versions']['WAVY_IMAGE_REGISTRY'] == before['versions']['WAVY_IMAGE_REGISTRY'],
                    'Registre ou clés de release source incompatibles')
            for c in COMPONENTS:
                k = c.upper().replace('-', '_')
                require(re.fullmatch(r'\d+\.\d+\.\d+-[0-9a-f]{7,40}', data['versions'][k+'_VERSION']) is not None and
                        re.fullmatch(r'sha256:[0-9a-f]{64}', data['digests'][k+'_DIGEST']) is not None,
                        'Version source invalide')
                expected = data['versions']['WAVY_IMAGE_REGISTRY']+'/wavy-'+c+':'+data['versions'][k+'_VERSION']+'@'+data['digests'][k+'_DIGEST']
                require(expected == data['images'][c] and same_reference(data['runtime'][c]['reference'], expected),
                        'Référence source incohérente')
            verify(root, 'recette', data['images'])
            for c in COMPONENTS:
                require(inspect(data['images'][c], 'image')['Id'] == data['runtime'][c]['id'],
                        'Image/architecture différente de PREPROD : '+c)
            for db in DATABASES:
                crypt(source/(db+'.dump.enc'), work/(db+'.dump'), key, True)
            crypt(source/'documents.tar.enc', work/'documents.tar', key, True)
            validate_source_documents(str(work/'documents.tar')); check_dumps(work)
            split_documents(work/'documents.tar', work)
            validate_tar(work/'contrats.tar'); validate_tar(work/'justificatifs.tar')
            require(sys.stdin.isatty(), 'Confirmation interactive requise ; aucun remplacement effectué')
            print('Source : PREPROD '+data['capturedAt']+' ; destination : '+socket.gethostname()+
                  '/wavy-recette. Remplacement des cinq bases, documents et 13 images ; sorties externes bloquées.')
            require(input('Saisir ECRASER RECETTE pour confirmer : ') == 'ECRASER RECETTE', 'Annulé')
            names = ['versions/recette.env', 'versions/recette.digests', POLICY]
            state = {'phase': 'backup', 'owner': os.getpid(), 'before': before, 'volumes': volumes,
                     'databaseRestart': {db: inspect(db+'-db-recette')['HostConfig']['RestartPolicy'] for db in DATABASES},
                     'toolImage': before['runtime']['factures-api']['id'], 'backup': str(target),
                     'backupVerified': False,
                     'savedFiles': {n: (root/n).read_text() if (root/n).exists() else None for n in names}}
            atomic_json(root/STATE, state)
            mutated = False
            check = 'backup'
            try:
                old = backup_folders(root, 'recette')
                subprocess.run(['bash', str(root/'scripts/backup-db.sh'), '--sync-hold'],
                               env=dict(env, WAVY_ENV='recette'), pass_fds=(fd,), check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                added = backup_folders(root, 'recette') - old
                require(len(added) == 1, 'Backup RECETTE non identifiable')
                save_rollback(root, added.pop(), target, key)
                state['backupVerified'] = True; state['phase'] = 'stopping'; atomic_json(root/STATE, state)
                check = 'stop'
                runtime_stop(before['runtime'])
                state['phase'] = 'restoring'; atomic_json(root/STATE, state)
                mutated = True
                check = 'restore-databases'
                db_restore(work)
                check = 'tenant-routing'
                shared_database_guard()
                check = 'restore-documents'
                for name, volume in volumes.items():
                    document_restore(work/(name+'.tar'), volume, state['toolImage'])
                check = 'release-config'
                write_versions(root, data)
                atomic_json(root/POLICY, {'format': 1, 'contractsVolume': volumes['contrats']})
                check = 'compose-start'
                compose(root, ['up', '-d', '--force-recreate', '--wait', '--wait-timeout', '600'])
                check = 'isolation'
                verify_isolation(restart='no')
                check = 'healthcheck'
                command(['bash', root/'scripts/healthcheck.sh', 'recette'])
                check = 'smoke-test'
                command(['bash', root/'scripts/smoke-test.sh', 'recette'])
                check = 'erp-shell'
                check_shell(values)
                check = 'erp-ingress'
                check_shell_ingress()
                state['phase'] = 'complete'; atomic_json(root/STATE, state)
                check = 'restart-policy'
                activate_restarts(root)
                verify_isolation(restart='unless-stopped')
                print('Synchronisation terminée. Secours chiffré : '+str(target))
            except BaseException as exc:
                # Conserver la cause initiale même si recover() remplace la phase.
                # Aucune sortie brute, commande, réponse HTTP ou valeur de secret.
                state['failure'] = {'check': check, 'code': exc.returncode if isinstance(exc, subprocess.CalledProcessError)
                                    else (130 if isinstance(exc, KeyboardInterrupt) else 1)}
                try:
                    atomic_json(root/STATE, state)
                except OSError:
                    print('Écriture du diagnostic impossible ; retour arrière toujours tenté.', file=sys.stderr)
                if mutated and state['backupVerified']:
                    try:
                        safe_recover(root, state, key, work)
                        print('Échec de synchronisation ; ancien RECETTE restauré.', file=sys.stderr)
                    except BaseException:
                        print('RECETTE en maintenance. Secours : '+str(target)+'. Relancer la commande pour retenter le retour arrière.', file=sys.stderr)
                elif state['backupVerified']:
                    state['phase'] = 'stopped'; atomic_json(root/STATE, state)
                else:
                    state['phase'] = 'backup-failed'; atomic_json(root/STATE, state)
                raise


def verify_isolation(restart=None):
    restart = restart or sync_restart_policy(ROOT)
    net = inspect('wavy-recette-sync', 'network')
    require(net.get('Internal') is True, 'Réseau RECETTE non isolé')
    ingress = inspect('wavy-recette', 'network')
    require(ingress.get('Internal') is False and ingress.get('Driver') == 'bridge', 'Réseau d’entrée RECETTE invalide')
    require(all(c.get('Name') == 'wavy-erp-shell-recette' for c in ingress.get('Containers', {}).values()),
            'Conteneur supplémentaire sur le réseau d’entrée')
    for c in COMPONENTS:
        obj = inspect('wavy-'+c+'-recette')
        expected = {'wavy-recette-sync', 'wavy-recette'} if c == 'erp-shell' else {'wavy-recette-sync'}
        require(set(obj['NetworkSettings']['Networks']) == expected, 'Réseau supplémentaire interdit : '+c)
        require(obj['HostConfig']['RestartPolicy']['Name'] == restart, 'Politique de redémarrage incohérente : '+c)
        if c == 'erp-shell':
            check_shell_boundary(obj)
        else:
            require(not any(obj['NetworkSettings'].get('Ports', {}).values()), 'Port métier publié interdit : '+c)
    for db in DATABASES:
        obj = inspect(db+'-db-recette')
        require(set(obj['NetworkSettings']['Networks']) == {'wavy-recette-sync'},
                'Réseau supplémentaire sur une base RECETTE')
        require(obj['HostConfig']['RestartPolicy']['Name'] == restart, 'Politique de redémarrage incohérente : '+db)
        require(not any(obj['NetworkSettings'].get('Ports', {}).values()), 'Port de base publié interdit : '+db)


def check_shell_boundary(obj):
    host = obj['HostConfig']
    added = {c.upper().removeprefix('CAP_') for c in host.get('CapAdd') or []}
    dropped = {c.upper().removeprefix('CAP_') for c in host.get('CapDrop') or []}
    require(not host.get('Privileged') and not added.intersection({'NET_ADMIN','NET_RAW','ALL'}),
            'Privilèges réseau interdits sur le Shell')
    require({'NET_ADMIN','NET_RAW'} <= dropped, 'Capacités réseau du Shell non retirées')
    require(all(host.get('Sysctls', {}).get(k) == '0' for k in ('net.ipv4.ip_forward','net.ipv6.conf.all.forwarding')),
            'Forwarding IP du Shell interdit')
    require(command(['docker','exec','wavy-erp-shell-recette','cat','/proc/sys/net/ipv4/ip_forward',
                     '/proc/sys/net/ipv6/conf/all/forwarding']).split() == [b'0',b'0'], 'Forwarding IP actif sur le Shell')
    published = {k:v for k,v in obj['NetworkSettings'].get('Ports', {}).items() if v}
    require(published == {'80/tcp':[{'HostIp':'127.0.0.1','HostPort':'24207'}]}, 'Publication du Shell non privée ou absente')
    env = environment(obj)
    require(all(env.get(k) == v for k,v in SHELL_UPSTREAMS.items()), 'Destination externe interdite dans le Shell')
    config = command(['docker','exec','wavy-erp-shell-recette','nginx','-T']).decode('utf-8')
    config = '\n'.join(line.split('#',1)[0] for line in config.splitlines())
    allowed = set(SHELL_UPSTREAMS.values()) | {'$private_api_origin', '$wavy_pwa_origin$uri$is_args$args'}
    targets = re.findall(r'\bproxy_pass\s+([^;]+);', config)
    require(targets and all(t.strip() in allowed for t in targets), 'Proxy sortant interdit dans le Shell')
    for variable, target in [('private_api_origin',SHELL_UPSTREAMS['API_UPSTREAM']), ('wavy_pwa_origin','http://wavy-pwa-recette')]:
        assignments = re.findall(r'\bset\s+\$'+variable+r'\s+([^;]+);',config)
        used = any('$'+variable in t for t in targets)
        require((assignments or not used) and all(x.strip() == target for x in assignments), 'Destination variable du Shell invalide')


def sync_overlay(root, overlay, mutation=True):
    """Extension du seul chemin Compose RECETTE, persistante et fermée par défaut."""
    state_path = root/STATE
    if mutation and state_path.exists():
        state = read_private(state_path)
        require(state['phase'] in SUCCESS or state.get('owner') == os.getpid(),
                'Synchronisation incomplète : relancer ./wavy sync preprod recette pour restaurer le secours')
    path = root/POLICY
    if not path.exists():
        require(not path.is_symlink(), 'Politique sync symbolique interdite')
        if state_path.exists():
            require(read_private(state_path).get('phase') != 'complete', 'Politique sync requise pour conserver l’isolation')
        return overlay
    policy = read_private(path)
    require(policy.get('format') == 1 and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', policy.get('contractsVolume','')),
            'Politique sync RECETTE invalide')
    overlay.setdefault('networks', {})['wavy-recette'] = {'name': 'wavy-recette-sync', 'internal': True}
    # Réseau d'entrée déjà provisionné par le Compose RECETTE initial.
    overlay['networks']['recette-ingress'] = {'name':'wavy-recette','external':True}
    restart = sync_restart_policy(root)
    for c in COMPONENTS:
        service = overlay.setdefault('services', {}).setdefault('wavy-'+c+'-recette', {})
        service['restart'] = restart
        if c.endswith('-api'):
            service.setdefault('environment', {}).update({
                'SPRING_JPA_HIBERNATE_DDL_AUTO': 'validate', 'SPRING_FLYWAY_ENABLED': 'false',
                'SPRING_SQL_INIT_MODE': 'never', 'WAVY_BOOTSTRAP_ENABLED': 'false',
                'WAVY_AI_ACHAT_AUTO_CREATION_ENABLED': 'false',
                'SPRING_MAIL_HOST': '127.0.0.1', 'SPRING_MAIL_PORT': '9',
                'HTTP_PROXY': '', 'HTTPS_PROXY': '', 'ALL_PROXY': ''})
    for db in DATABASES:
        overlay['services'].setdefault(db+'-postgres', {})['restart'] = restart
    shell = overlay['services']['wavy-erp-shell-recette']
    shell['networks'] = {'wavy-recette':{}, 'recette-ingress':{}}
    shell['sysctls'] = {'net.ipv4.ip_forward':'0','net.ipv6.conf.all.forwarding':'0'}
    shell['cap_drop'] = ['NET_ADMIN','NET_RAW']
    shell['security_opt'] = ['no-new-privileges:true']
    shell.setdefault('environment', {}).update(SHELL_UPSTREAMS)
    overlay.setdefault('volumes', {})['sync-contrats'] = {'name': policy['contractsVolume'], 'external': True}
    # Les chemins Contrats sont absolus en base. Un alias conserve les chemins PREPROD
    # et le montage historique RECETTE, sans réécriture de données métier.
    overlay['services']['wavy-contrats-api-recette'].setdefault('volumes', []).append(
        {'type': 'volume', 'source': 'sync-contrats', 'target': '/app/data/contrats', 'volume': {'nocopy': True}})
    return overlay


def main(args):
    if args == ['_export']:
        source_export(ROOT); return
    require(args == ['preprod', 'recette'], 'Usage : ./wavy sync preprod recette (seul sens autorisé)')
    def interrupt(signum, frame):
        raise InterruptedError('Synchronisation interrompue')
    signal.signal(signal.SIGTERM, interrupt)
    run(ROOT)


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except (Exception, KeyboardInterrupt) as exc:
        if isinstance(exc, ValueError): print(str(exc), file=sys.stderr)
        print('ERREUR : synchronisation refusée ou interrompue. Consulter l’état privé deployments/recette-sync.json ; aucune sortie technique sensible affichée.', file=sys.stderr)
        sys.exit(1)
