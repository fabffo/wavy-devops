#!/usr/bin/env python3
"""Contrôles de livraison : rendu réel, prérequis locaux et HTTPS, sans test métier."""
import json
import getpass
import socket
from datetime import datetime, timezone
import os
import re
from pathlib import Path
import subprocess
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from release_images import release, manifest, recette_compose, recette_operation, COMPONENTS
from recette_pwa import policy, runtime_check, preserve_storage, literal

ROOT = Path(__file__).resolve().parent.parent


def require(condition, message):
    if not condition:
        raise ValueError(message)


def dotenv_literal(value):
    value = value.strip()
    if value.startswith(('"', "'")):
        require(len(value) >= 2 and value[-1] == value[0], 'Quotes dotenv incomplètes')
        return value[1:-1]
    return value


def machine(root):
    path = root/'.env.recette'
    require(not path.is_symlink() and path.stat().st_uid == os.getuid() and not path.stat().st_mode & 0o077,
            '.env.recette doit être privé (0600), propriétaire courant')
    values = manifest(path)  # les doublons sont des erreurs, même de valeur identique
    forbidden = [k for k in values if k.endswith(('_VERSION', '_DIGEST')) or k in ('WAVY_IMAGE_REGISTRY','WAVY_GATEWAY_CORS_ALLOWED_ORIGIN_PATTERNS')]
    require(not forbidden, 'Versions/digests ou ancien CORS Gateway présents dans le dotenv machine')
    return {k: dotenv_literal(v) for k,v in values.items()}


def profiles(value):
    return tuple(part.strip() for part in value.split(',') if part.strip())


def valid_profile(component, value, env='recette'):
    selected = profiles(value)
    if env != 'recette':
        return env in selected and not set(selected).intersection({'local','dev','test'})
    allowed = {('recette',), ('recette','secure')}
    if component == 'socle-api': allowed.add(('local',))
    return selected in allowed


def rendered_checks(config, env, images, origin=None, check=require):
    services = config.get('services', {})
    for c in COMPONENTS:
        svc = services.get(f'wavy-{c}-{env}')
        check(svc is not None, f'{env}/{c} : service absent')
        if svc is not None:
            check(svc.get('image') == images.get(c), f'{env}/{c} : image différente du manifeste')
    check(not any('build' in s for s in services.values()), 'Build distant interdit')
    cors = set()
    for c in ('socle-api','tiers-api','contrats-api','factures-api','tresorerie-api','gateway'):
        e = services.get(f'wavy-{c}-{env}', {}).get('environment', {})
        selected = profiles(e.get('SPRING_PROFILES_ACTIVE', ''))
        if env == 'recette':
            # Le nom de l'environnement Docker n'est pas un contrat de profil Spring.
            # Socle local est le contrat historique publié. Aucune activation de secure implicite.
            check(valid_profile(c,e.get('SPRING_PROFILES_ACTIVE','')),  f'Profil incohérent : {env}/{c}')
            check(e.get('SERVER_FORWARD_HEADERS_STRATEGY') == 'framework', f'{c} : transmission HTTPS Spring absente')
        else:
            check(env in selected and not set(selected).intersection({'local','dev','test'}), f'Profil incohérent : {env}/{c}')
        cors.add(e.get('WAVY_CORS_ALLOWED_ORIGIN_PATTERNS', ''))
    check(len(cors) == 1 and bool(next(iter(cors), '')) and all('*' not in v for v in cors), f'{env} : CORS contradictoire ou wildcard')
    if origin:
        check(all(origin in [part.strip() for part in value.split(',')] for value in cors), 'Origine HTTPS absente de CORS')
    for name, s in services.items():
        for port in s.get('ports', []):
            check(port.get('host_ip') in ('127.0.0.1','::1'), f'{env}/{name} : port publié hors loopback')
    if env == 'recette':
        factures = services.get('wavy-factures-api-recette', {})
        check(factures.get('environment', {}).get('WAVY_FACTURES_STOCKAGE_JUSTIFICATIFS') == '/app/justificatifs', 'Stockage Factures persistant absent')
        mounts = [m for m in factures.get('volumes', []) if m['target'] == '/app/justificatifs']
        valid = len(mounts) == 1 and mounts[0]['type'] == 'volume'
        check(valid, 'Montage documentaire invalide')
        if valid:
            check(config.get('volumes', {}).get(mounts[0]['source'], {}).get('external'), 'Le volume documentaire doit être externe')


def check_recette(root):
    values = machine(root)
    _, _, images = release(root, 'recette')
    state = policy(root, values, images)
    require(state['mode'] == 'technical', 'Installation standard : WAVY_RECETTE_VALIDATION_MODE=technical requis')
    require(state['enabled'] and state['writes'] and state['go'], 'RECETTE : activer PWA et écritures, volume privé et origine CORS requis')
    config = recette_compose(root, ['config', '--format', 'json'], capture=True)
    rendered_checks(config, 'recette', images, state['origin'])
    for s in config['services'].values():
        for key, value in s.get('environment', {}).items():
            if key.endswith('PASSWORD'):
                require(value and value not in ('motdepasse_recette','CHANGE_ME'), 'Mot de passe machine absent ou valeur exemple')
    return state, images


def promotion(root):
    _, _, recette = release(root, 'recette')
    _, _, preprod = release(root, 'preprod')
    require(recette == preprod, 'Promotion : RECETTE et PREPROD doivent référencer la même release')
    # Décision humaine persistante, aucune attestation produite par les tests.
    from preprod_operation import read_private
    path = root/'deployments/recette-validation.private.json'
    proof = read_private(path)
    require(proof.get('approved') is True and bool(proof.get('reviewer')) and proof.get('images') == recette,
            'Validation fonctionnelle RECETTE explicite requise pour ces 13 images avant PREPROD')


def preflight(root):
    state, images = check_recette(root)
    values = machine(root)
    require(values.get('COMPOSE_PROJECT_NAME', 'wavy-recette') == 'wavy-recette', 'Projet RECETTE fixe requis')
    names = [f'wavy-{c}-recette' for c in COMPONENTS]
    names += [f'{db}-db-recette' for db in ('socle','tiers','contrats','factures','tresorerie')]
    objects = json.loads(subprocess.check_output(['docker','inspect',*names]))
    require({o['Name'].lstrip('/') for o in objects} == set(names), 'Installation RECETTE existante incomplète')
    for obj in objects:
        require(obj['Config'].get('Labels', {}).get('com.docker.compose.project') == 'wavy-recette', 'Conteneur hors projet RECETTE')
        require(obj['State']['Running'], 'Reprendre les services existants avant installation')
        name = obj['Name'].lstrip('/')
        if name.startswith('wavy-') and ('-api-' in name or name == 'wavy-gateway-recette'):
            active = dict(item.split('=',1) for item in obj['Config'].get('Env',[]) if '=' in item)
            key = 'WAVY_'+name[5:-8].upper().replace('-','_').replace('_API','')+'_SPRING_PROFILES_ACTIVE'
            wanted = values.get(key, 'local' if name == 'wavy-socle-api-recette' else 'recette')
            require(profiles(active.get('SPRING_PROFILES_ACTIVE','')) == profiles(wanted),
                    'Changement de profil à tester avant installation : '+name)
    preserve_storage(state)
    docker_root = subprocess.check_output(['docker','info','--format','{{.DockerRootDir}}'], text=True).strip()
    for path in (root, root/'backups', Path(docker_root)):
        stats = os.statvfs(path if path.exists() else path.parent)
        require(stats.f_bavail * stats.f_frsize >= 1024**3, 'Espace libre insuffisant (1 Gio minimum)')


def check_storage(root):
    from recette_storage import provision
    state, images = check_recette(root)
    preserve_storage(state)
    values = machine(root)
    provision(state['volume'], images['factures-api'], values.get('WAVY_RECETTE_PROVISION_JUSTIFICATIFS') == 'true')


def request(origin, path, codes=(200,)):
    # TLS système obligatoire ; pas de -k, pas de cookies ni écriture.
    try:
        with urlopen(Request(origin+path), timeout=30) as response:
            require(response.url.startswith(origin+'/'), 'Redirection vers une autre origine')
            code = response.status
            body = response.read(2*1024*1024)
    except HTTPError as error:
        code, body = error.code, error.read(2*1024*1024)
    require(code in codes, f'HTTPS {path} : statut {code} inattendu')
    return body


def cors_runtime(origin):
    req = Request(origin+'/api/auth/session', method='OPTIONS', headers={
        'Origin': origin, 'Access-Control-Request-Method': 'GET'})
    with urlopen(req, timeout=30) as response:
        require(response.status in (200,204) and response.headers.get('Access-Control-Allow-Origin') == origin,
                'Préflight CORS HTTPS refusé ou origine incorrecte')


def runtime(root):
    state, images = check_recette(root)
    runtime_check(state, images)
    # Vérifier aussi les six interfaces non incluses dans le groupe PWA historique.
    for c, image in images.items():
        obj = json.loads(subprocess.check_output(['docker','inspect',f'wavy-{c}-recette']))[0]
        require(obj['State']['Running'] and obj['Config']['Image'] == image, f'Image runtime incorrecte : {c}')
        if c.endswith('-api') or c == 'gateway':
            require(obj['State'].get('Health', {}).get('Status') == 'healthy', f'API indisponible : {c}')
    origin = state['origin']
    request(origin, '/')
    integration = json.loads(request(origin, '/pwa-integration.json'))
    require(integration.get('enabled') is True, 'PWA masquée dans le Shell')
    for path in ('/pwa/', '/pwa/connexion', '/pwa/ngsw-worker.js', '/modules/socle/', '/modules/tiers/',
                 '/modules/contrats/', '/modules/factures/', '/modules/tresorerie/'):
        body = request(origin, path)
        require(bool(body), f'Réponse vide : {path}')
        if path.endswith('.js'):
            require(b'<html' not in body.lower(), 'Service worker remplacé par du HTML')
    cors_runtime(origin)
    request(origin, '/api/auth/session', (401,))
    request(origin, '/api/actuator/health', (200,401,403,404))  # surface protégée selon Gateway


def approve(root):
    from recette_pwa import local_daemon
    from preprod_operation import atomic_json
    require(machine(root).get('WAVY_INSTALL_HOSTNAME') == socket.gethostname().split('.')[0], 'Validation à effectuer sur la VM RECETTE configurée')
    local_daemon()
    runtime(root)
    require(sys.stdin.isatty(), 'Validation humaine interactive requise')
    answer = input('Confirmez-vous votre validation fonctionnelle RECETTE pour promouvoir cette release en PREPROD ? Saisir oui : ')
    require(answer == 'oui', 'Validation non enregistrée')
    directory = root/'deployments'; directory.mkdir(exist_ok=True)
    atomic_json(directory/'recette-validation.private.json', {
        'approved': True, 'reviewer': getpass.getuser(),
        'validatedAt': datetime.now(timezone.utc).isoformat(),
        'images': release(root,'recette')[2], 'environment': 'recette',
        'origin': machine(root)['WAVY_PWA_PUBLIC_ORIGIN']})


def main():
    action = sys.argv[1] if len(sys.argv) >= 2 else ''
    if action == 'diagnose':
        from recette_diagnostic import diagnose
        report = diagnose(ROOT)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if report['errors'] else 0
    elif action == 'migrations':
        for c in ('socle-api','tiers-api','contrats-api','factures-api','tresorerie-api'):
            logs = subprocess.check_output(['docker','logs','--since',sys.argv[2],f'wavy-{c}-recette'], stderr=subprocess.STDOUT, text=True)
            require(not re.search(r'checksum mismatch|Validate failed|migration failed|FlywayValidateException|FlywayMigrateException', logs, re.I), f'Migration en échec : {c}')
    elif action == 'recette': check_recette(ROOT)
    elif action == 'preflight': preflight(ROOT)
    elif action == 'storage': check_storage(ROOT)
    elif action == 'runtime': runtime(ROOT)
    elif action == 'approve':
        with recette_operation(ROOT, True):
            approve(ROOT)
    elif action == 'promotion': promotion(ROOT)
    else: raise ValueError('Action attendue : recette|preflight|storage|migrations|runtime|approve|promotion')
    print('GO technique : '+action+' (aucune validation fonctionnelle déduite)')


if __name__ == '__main__':
    try: sys.exit(main())
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        # Les sorties Compose/Docker ne sont jamais imprimées : secrets possibles.
        print('NO-GO livraison : '+(str(error) if isinstance(error, ValueError) else type(error).__name__), file=sys.stderr)
        sys.exit(1)
