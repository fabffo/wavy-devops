#!/usr/bin/env python3
"""Validation PREPROD sans daemon, sans exécution du dotenv, sans sortie de secrets."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
COMPONENTS = ('socle-api tiers-api contrats-api factures-api tresorerie-api gateway '
              'socle-front tiers-front contrats-front factures-front tresorerie-front pwa erp-shell').split()


def check(condition, message):
    if not condition:
        raise ValueError(message)


def dotenv(path):
    check(path.is_file(), f'Fichier requis absent : {path.name}')
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        match = re.fullmatch(r'([A-Z][A-Z0-9_]*)=(.*)', line)
        check(match is not None, f'Syntaxe dotenv invalide : {path.name}')
        key, value = match.groups()
        check(key not in values, f'Variable dupliquée : {key}')
        # Deliberately restrict to literal values; shell and Compose must agree.
        if value.startswith("'") and value.endswith("'"):
            value = value[1:-1]
            check("'" not in value, f'Quote interne interdite : {key}')
        else:
            check(not any(c in value for c in "\"'$#\\"), f'Utiliser une valeur littérale entre quotes simples : {key}')
        check('CHANGE_ME' not in value, f'Placeholder à remplacer : {key}')
        values[key] = value
    return values


def inputs(env_path):
    e = dotenv(env_path)
    v = dotenv(ROOT / 'versions/preprod.env')
    d = dotenv(ROOT / 'versions/preprod.digests')
    check(not (e.keys() & (v.keys() | d.keys())), 'Versions/digests/registre interdits dans le dotenv machine')
    check(set(v) == {'WAVY_IMAGE_REGISTRY'} | {c.upper().replace('-', '_')+'_VERSION' for c in COMPONENTS}, 'Clés du manifeste versions inattendues')
    check(set(d) == {c.upper().replace('-', '_')+'_DIGEST' for c in COMPONENTS}, 'Clés du manifeste digests inattendues')
    check(v['WAVY_IMAGE_REGISTRY'] == 'ghcr.io/fabffo', 'Registre PREPROD inattendu')
    for c in COMPONENTS:
        key = c.upper().replace('-', '_')
        check(re.fullmatch(r'\d+\.\d+\.\d+-[0-9a-f]{7,40}', v[key+'_VERSION']), f'Version invalide : {c}')
        check(re.fullmatch(r'sha256:[0-9a-f]{64}', d[key+'_DIGEST']), f'Digest invalide : {c}')
    return e, v, d


def compose_args(env_path, args):
    # No inherited variable may override a manifest or the machine dotenv.
    raw = (ROOT / 'docker-compose.preprod.yml').read_text()
    keys = set(re.findall(r'\$\{([A-Z][A-Z0-9_]*)', raw))
    clean = {k: val for k, val in os.environ.items() if k not in keys and not k.startswith('COMPOSE_')}
    return (['docker', 'compose', '--env-file', str(env_path), '--env-file', str(ROOT / 'versions/preprod.env'),
             '-p', 'wavy-preprod', '-f', str(ROOT / 'docker-compose.preprod.yml')] + args, clean)


def render(env_path):
    cmd, clean = compose_args(env_path, ['config', '--quiet'])
    check(subprocess.run(cmd, env=clean, capture_output=True).returncode == 0, 'Compose config --quiet a échoué (sortie masquée pour protéger les secrets)')
    cmd, clean = compose_args(env_path, ['config', '--format', 'json'])
    result = subprocess.run(cmd, env=clean, capture_output=True)
    check(result.returncode == 0, 'Compose JSON a échoué')
    return json.loads(result.stdout)


def validate(env_path):
    e, v, d = inputs(env_path)
    check(env_path.stat().st_mode & 0o077 == 0, 'Le dotenv doit être privé : chmod 600')
    required = ['COMPOSE_PROJECT_NAME', 'WAVY_PUBLIC_URL', 'WAVY_CORS_ALLOWED_ORIGIN_PATTERNS',
                'WAVY_BOOTSTRAP_TENANT_CODE', 'WAVY_BOOTSTRAP_TENANT_NAME', 'WAVY_BOOTSTRAP_COMPANY_NAME',
                'WAVY_BOOTSTRAP_COMPANY_SIREN', 'WAVY_BOOTSTRAP_ADMIN_EMAIL', 'WAVY_BOOTSTRAP_ADMIN_PASSWORD',
                'WAVY_SESSION_SECRET', 'WAVY_BACKUP_ENCRYPTION_PASSPHRASE']
    required += ['WAVY_'+c+'_DB_PASSWORD' for c in ['SOCLE', 'TIERS', 'CONTRATS', 'FACTURES', 'TRESORERIE']]
    for key in required:
        check(bool(e.get(key)), f'Variable obligatoire absente : {key}')
    check(e['COMPOSE_PROJECT_NAME'] == 'wavy-preprod', 'Projet différent de wavy-preprod')
    check('WAVY_IMAGE_TAG' not in e and 'WAVY_PUBLIC_HTTPS_PORT' not in e, 'Ancienne variable PREPROD interdite')
    check(e.get('WAVY_BOOTSTRAP_ENABLED') in ('true', 'false'), 'Bootstrap : true ou false requis')
    check(re.fullmatch(r'\d{9}', e['WAVY_BOOTSTRAP_COMPANY_SIREN']), 'SIREN : 9 chiffres requis')
    check(re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', e['WAVY_BOOTSTRAP_ADMIN_EMAIL']), 'Email bootstrap invalide')
    for key, size in [('WAVY_BOOTSTRAP_ADMIN_PASSWORD', 12), ('WAVY_SESSION_SECRET', 32), ('WAVY_BACKUP_ENCRYPTION_PASSPHRASE', 32)]:
        check(len(e[key]) >= size, f'Longueur minimale {size} requise : {key}')
    passwords = [e['WAVY_'+c+'_DB_PASSWORD'] for c in ['SOCLE', 'TIERS', 'CONTRATS', 'FACTURES', 'TRESORERIE']]
    check(all(len(p) >= 12 for p in passwords) and len(set(passwords)) == 5, 'Les cinq mots de passe DB doivent être distincts et contenir au moins 12 caractères')
    check(re.fullmatch(r'[1-9][0-9]*', e.get('WAVY_BACKUP_RETENTION_DAYS', '')), 'Rétention invalide')
    port = e.get('WAVY_PUBLIC_HTTP_PORT', '24443')
    check(port.isdigit() and 1024 <= int(port) <= 65535, 'Port HTTP invalide')
    url = e['WAVY_PUBLIC_URL']
    u = urlsplit(url)
    check(u.hostname and not u.username and not u.password and not u.query and not u.fragment and u.path == '', 'URL publique : origine exacte sans chemin')
    mode = e.get('WAVY_ACCESS_MODE')
    check(mode in ('tunnel', 'https'), 'Mode accès : tunnel ou https')
    check(e.get('WAVY_COOKIE_SECURE') == ('false' if mode == 'tunnel' else 'true'), 'Cookie Secure incompatible avec le mode accès')
    if mode == 'tunnel':
        check(url == 'http://localhost:'+port, 'Tunnel : origine attendue http://localhost:<port HTTP>')
    else:
        check(u.scheme == 'https' and u.hostname not in ('localhost', '127.0.0.1') and not u.hostname.endswith('.example.com'), 'HTTPS : domaine réel dédié requis')
    check(e['WAVY_CORS_ALLOWED_ORIGIN_PATTERNS'] == url, 'CORS doit correspondre uniquement à WAVY_PUBLIC_URL')
    for left, right in [('WAVY_TIERS_SERVICE_USERNAME', 'WAVY_TIERS_SERVICE_PASSWORD')]:
        check(bool(e.get(left)) == bool(e.get(right)), 'Credentials interservices incomplets')
        check(not e.get(right) or len(e[right]) >= 12, 'Mot de passe interservice trop court')
    config = render(env_path)
    services = config['services']
    expected = {'wavy-'+c+'-preprod' for c in COMPONENTS} | {c+'-postgres' for c in ['socle','tiers','contrats','factures','tresorerie']}
    check(set(services) == expected and config['name'] == 'wavy-preprod', 'Services/projet inattendus')
    network = config.get('networks', {}).get('wavy-preprod', {})
    check(network.get('name') == 'wavy-preprod' and not network.get('external'), 'Réseau externe ou hors PREPROD')
    expected_volumes = {db+'-postgres-preprod-data' for db in ['socle','tiers','contrats','factures','tresorerie']} | {'documents-preprod'}
    check(set(config.get('volumes', {})) == expected_volumes, 'Volumes PREPROD inattendus')
    for key, volume in config['volumes'].items():
        check(volume.get('name') == 'wavy-preprod_'+key and not volume.get('external') and not volume.get('driver_opts'), 'Volume hors projet PREPROD')
    for db in ['socle','tiers','contrats','factures','tresorerie']:
        service = services[db+'-postgres']
        check(service['container_name'] == db+'-db-preprod', 'Nom de base hors PREPROD')
        check(service['image'] == 'postgres:16-alpine@sha256:93d55776e04376e19adb2733e3ccebb4392ee7dd86d8ff238503b30fe719c84f', 'Image PostgreSQL non approuvée')
        se = service['environment']
        prefix = 'WAVY_'+db.upper()+'_DB_'
        check(se['POSTGRES_PASSWORD'] == e[prefix+'PASSWORD'] and se['POSTGRES_DB'] == e[prefix+'NAME'] and se['POSTGRES_USER'] == e[prefix+('USERNAME' if db == 'socle' else 'USER')], 'Configuration DB différente du dotenv')
    published = []
    for name, service in services.items():
        check(not any(k in service for k in ('build','privileged','network_mode','extends','volumes_from')), f'Option non autorisée : {name}')
        check(service.get('networks') and set(service['networks']) == {'wavy-preprod'}, f'Réseau inattendu : {name}')
        check(bool(service.get('healthcheck', {}).get('test')) and not service['healthcheck'].get('disable'), f'Healthcheck absent : {name}')
        for volume in service.get('volumes', []):
            check(volume['type'] == 'volume' and volume['source'] in expected_volumes, f'Montage hors PREPROD : {name}')
        if service.get('ports'):
            published.append(name)
            check(len(service['ports']) == 1 and service['ports'][0]['host_ip'] == '127.0.0.1' and service['ports'][0]['target'] == 80 and str(service['ports'][0]['published']) == port, 'Publication autre que loopback HTTP ERP Shell')
    check(published == ['wavy-erp-shell-preprod'], 'ERP Shell doit être le seul port publié')
    for c in COMPONENTS:
        service = services['wavy-'+c+'-preprod']
        check(service['container_name'] == 'wavy-'+c+'-preprod', f'Conteneur inattendu : {c}')
        key = c.upper().replace('-', '_')
        check(service['image'] == v['WAVY_IMAGE_REGISTRY']+'/wavy-'+c+':'+v[key+'_VERSION'], f'Image différente du manifeste : {c}')
        if c.endswith('-api') or c == 'gateway':
            se = service['environment']
            if c.endswith('-api'):
                for key, value in {'SPRING_JPA_HIBERNATE_DDL_AUTO': 'validate', 'SPRING_SQL_INIT_MODE': 'never', 'SPRING_FLYWAY_ENABLED': 'true', 'SPRING_FLYWAY_VALIDATE_ON_MIGRATE': 'true', 'SPRING_FLYWAY_CLEAN_DISABLED': 'true'}.items():
                    check(se.get(key) == value, f'Garde-fou DB absent : {c}/{key}')
            check(se.get('SERVER_SERVLET_SESSION_COOKIE_SECURE') == e['WAVY_COOKIE_SECURE'] and se.get('SERVER_SERVLET_SESSION_COOKIE_HTTP_ONLY') == 'true' and se.get('SERVER_SERVLET_SESSION_COOKIE_SAME_SITE') == 'Strict', f'Cookies non conformes : {c}')
            check(se.get('SPRINGDOC_API_DOCS_ENABLED') == 'false' and se.get('SPRINGDOC_SWAGGER_UI_ENABLED') == 'false', f'OpenAPI exposé : {c}')
            check(se.get('SPRING_PROFILES_ACTIVE') == 'preprod,secure', f'Profils incorrects : {c}')
            check(service.get('read_only') and 'no-new-privileges:true' in service.get('security_opt', []), f'Durcissement absent : {c}')
            check(se.get('WAVY_CORS_ALLOWED_ORIGIN_PATTERNS') == url, f'CORS incohérent : {c}')
    owners = [name for name, svc in services.items() if any(m['source'] == 'documents-preprod' for m in svc.get('volumes', []))]
    check(owners == ['wavy-contrats-api-preprod'], 'Volume documentaire réservé à Contrats')
    mount = services['wavy-contrats-api-preprod']['volumes'][0]
    check(mount['target'] == '/app/data' and not mount.get('read_only'), 'Montage documentaire incorrect')
    check(services['wavy-contrats-api-preprod']['environment']['WAVY_CONTRATS_STOCKAGE_PIECES_JOINTES'] == '/app/data/contrats', 'Racine documentaire incorrecte')
    check(services['wavy-socle-api-preprod']['environment']['WAVY_BOOTSTRAP_ENABLED'] == e['WAVY_BOOTSTRAP_ENABLED'], 'Bootstrap non configurable')
    print('OK Configuration PREPROD : 13 versions/digests, profils, secrets, CORS, isolation, Compose.')


if __name__ == '__main__':
    try:
        action = sys.argv[1]
        env_path = Path(sys.argv[2]).resolve()
        if action == 'validate':
            validate(env_path)
        elif action == 'value':
            print(dotenv(env_path).get(sys.argv[3], ''))
        elif action == 'compose':
            cmd, clean = compose_args(env_path, sys.argv[3:])
            os.execvpe(cmd[0], cmd, clean)
        else:
            raise ValueError('Action inconnue')
    except (ValueError, KeyError, OSError, IndexError) as exc:
        print('ERREUR PREPROD : '+str(exc), file=sys.stderr)
        sys.exit(1)
