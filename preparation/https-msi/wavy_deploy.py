#!/usr/bin/env python3
"""Préparation HTTPS MSI. Réutilise Compose et le moteur privé, sans voie de contournement."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
TARGETS = {
    'recettelocal': ('recettelocal.wavyservices.fr', 'recette', 24207),
    'recette': ('recette.wavyservices.fr', 'recette', 34443),
    'preprod': ('preprod.wavyservices.fr', 'preprod', 24443),
}
COMPONENTS = ('socle-api', 'tiers-api', 'contrats-api', 'factures-api', 'tresorerie-api',
              'gateway', 'socle-front', 'tiers-front', 'contrats-front', 'factures-front',
              'tresorerie-front', 'pwa', 'erp-shell')
MODULES = ('socle','tiers','contrats','factures','tresorerie','pwa')
# Runtime dependencies, not the over-inclusive optional routes of Compose Gateway.
LOCAL_DEPS = {
    'socle-api': ('socle-postgres','tiers-api'),
    'tiers-api': ('tiers-postgres','socle-api'),
    'contrats-api': ('contrats-postgres','socle-api','tiers-api'),
    'factures-api': ('factures-postgres','socle-api','tiers-api','contrats-api'),
    'tresorerie-api': ('tresorerie-postgres','factures-api','tiers-api','socle-api'),
    'gateway': ('socle-api',), 'erp-shell': ('gateway',),
    **{c+'-front': ('gateway',) for c in MODULES if c!='pwa'},
    'pwa': ('gateway','factures-api'),
    **{c+'-postgres': () for c in MODULES if c!='pwa'},
}


def local_closure(services):
    result=set(); pending=list(services)
    while pending:
        node=pending.pop()
        if node not in LOCAL_DEPS: raise ValueError('Service local inconnu : '+node)
        if node not in result: result.add(node);pending.extend(LOCAL_DEPS[node])
    return result


def local_services(modules):
    if not set(modules).issubset(MODULES): raise ValueError('Module local inconnu')
    roots=[]
    for module in modules:
        roots.extend(('pwa',) if module=='pwa' else (module+'-api',module+'-front'))
    if roots:roots.append('erp-shell')
    return local_closure(roots)


def local_stop_plan(selected, roots, running):
    remaining=set(roots)-set(selected)
    candidates=local_services(selected)
    keep=local_services(remaining)
    # Also protect live consumers started outside this module ledger.
    outside=set(running)-candidates
    keep |= local_closure(outside) if outside else set()
    return candidates-keep, candidates&keep


def lazy_module_routes(text, upstreams):
    for module in MODULES:
        if module=='pwa':continue
        token='${'+module.upper()+'_FRONT_UPSTREAM}'
        url=upstreams[module.upper()+'_FRONT_UPSTREAM'].rstrip('/')
        if url!='http://wavy-'+module+'-front-recette':raise ValueError('Upstream module local inattendu')
        old='location /modules/'+module+'/ { proxy_pass '+token+';'
        new=('location /modules/'+module+'/ { set $wavy_module_'+module+' '+url+'; '
             'rewrite ^/modules/'+module+'/(.*)$ /$1 break; proxy_pass $wavy_module_'+module+'$uri$is_args$args;')
        if old in text:text=text.replace(old,new)
        elif new not in text:raise ValueError('Route module non reconnue : '+module)
    return text


def read_values(path):
    values = {}
    for line in path.read_text().splitlines():
        if not line or line.startswith('#') or '=' not in line: continue
        key, value = line.split('=', 1)
        if key in values: raise ValueError('Clé répétée dans un inventaire')
        values[key] = value
    return values


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args):
    if os.environ.get('DOCKER_HOST') or os.environ.get('DOCKER_CONTEXT'):
        raise ValueError('Overrides Docker distants interdits')
    endpoint = subprocess.run(['docker', 'context', 'inspect', '--format', '{{.Endpoints.docker.Host}}'], capture_output=True, timeout=10)
    if endpoint.returncode or endpoint.stdout.decode().strip() != 'unix:///var/run/docker.sock':
        raise ValueError('Daemon Docker local Unix requis ; aucun accès VM')
    result = subprocess.run(args, capture_output=True, timeout=90)
    if result.returncode:
        raise ValueError('Commande refusée ; sortie masquée pour préserver les secrets')
    return result.stdout


def plan(target):
    host, base, port = TARGETS[target]
    # Une cohorte immuable commune : aucun tag résolu au cours d’une promotion.
    pins = read_values(ROOT / 'versions/recette.digests')
    reviewed = json.loads((ROOT / 'preparation/pwa-notes-frais/release-plan.json').read_text())['images']
    versions = read_values(ROOT / 'versions/recette.env')
    image_versions = {}
    images = {}
    for component in COMPONENTS:
        key = component.upper().replace('-', '_') + '_DIGEST'
        value = reviewed[component]['digest'] if component in reviewed else pins[key]
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', value):
            raise ValueError('Digest absent ou incorrect')
        images[component] = 'ghcr.io/fabffo/wavy-' + component + '@' + value
        image_versions[component] = reviewed[component]['version'] if component in reviewed else versions[component.upper().replace('-', '_') + '_VERSION']
    p = {'environment': target, 'origin': 'https://' + host, 'baseCompose': 'docker-compose.' + base + '.yml',
         'imageVersions': image_versions, 'project': 'wavy-' + base, 'windowsUpstream': '127.0.0.1:' + str(port), 'images': images,
         'pwaDefault': 'closed', 'notesWritesDefault': 'blocked', 'vmAccessAuthorized': False,
         'order': ['MSI development', 'recettelocal', 'recette', 'preprod'],
         'activeInputs': {str(p.relative_to(ROOT)): digest(p) for p in
             [ROOT / ('docker-compose.' + base + '.yml'), ROOT / 'versions/recette.digests', ROOT / 'versions/recette.env',
              ROOT / 'preparation/pwa-notes-frais/release-plan.json']}}
    p['planSha256'] = hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()
    return p


def gateway_settings(origin):
    # Propriétés exactes : évite l’ambiguïté du binding d’une map CORS en env vars.
    prefix = 'spring.cloud.gateway.server.webflux.'
    return {prefix + 'globalcors.cors-configurations.[/**].allowed-origins': origin,
            prefix + 'globalcors.cors-configurations.[/**].allowed-origin-patterns': '',
            prefix + 'globalcors.cors-configurations.[/**].allow-credentials': True,
            prefix + 'globalcors.add-to-simple-url-handler-mapping': True,
            # Headers uniques produits par le Shell. Ne pas les compléter avec http/interne.
            prefix + 'forwarded.enabled': False, prefix + 'x-forwarded.enabled': False,
            prefix + 'default-filters': ['DedupeResponseHeader=Access-Control-Allow-Origin Access-Control-Allow-Credentials, RETAIN_UNIQUE',
                                         'PreserveHostHeader']}


def proxy_regex(subnet):
    network = ipaddress.ip_network(subnet, strict=True)
    # Pas de confiance générale RFC1918 ou .* ; réseau Docker /24 ou /16 observé.
    rfc1918 = tuple(ipaddress.ip_network(cidr) for cidr in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))
    if network.version != 4 or network.prefixlen not in (16, 24) or not any(network.subnet_of(allowed) for allowed in rfc1918):
        raise ValueError('Sous-réseau Docker privé /16 ou /24 explicite requis')
    prefix = str(network.network_address).split('.')[:network.prefixlen // 8]
    return r'\.'.join(prefix + [r'(?:25[0-5]|2[0-4][0-9]|1?[0-9]{1,2})'] * (4 - len(prefix)))


def shell_config(host):
    # Reprend le Shell existant ; aucune route module ou /api supprimée.
    text = (ROOT / 'preparation/pwa-notes-frais/private-shell/shell.conf.template').read_text()
    text = text.replace('map $http_x_forwarded_proto $wavy_forwarded_proto { default $scheme; https https; }', '')
    text = text.replace('server_name _;', 'server_name ' + host + ';\n  if ($host != ' + host + ') { return 421; }')
    text = text.replace('include /etc/nginx/private-pwa/routes.conf;', 'include /etc/nginx/wavy-https/closed.conf;')
    headers = ('proxy_set_header Host ' + host + '; proxy_set_header X-Forwarded-Host ' + host +
               '; proxy_set_header X-Forwarded-Proto https; proxy_set_header X-Forwarded-Port 443; '
               'proxy_set_header X-Forwarded-For $http_x_forwarded_for; proxy_set_header Forwarded "";')
    text = text.replace('proxy_set_header Host $host; proxy_set_header X-Forwarded-Proto $wavy_forwarded_proto; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;', headers)
    # Protection indépendante du cookie/gate : toutes mutations API exigent l’Origin canonique.
    text = ('map "$request_method:$http_origin" $wavy_origin_denied { default 1;\n'
            ' ~^(GET|HEAD|OPTIONS): 0;\n ~^[A-Z]+:https://' + host.replace('.', r'\.') + '$ 0;\n}\n' + text)

    # Origin exigée dans chaque location API, sans modifier les contrôles métier.
    text = text.replace('location /api/ {', 'location /api/ { if ($wavy_origin_denied) { return 403; }')
    # Cookie-session discovery must return its real 401 to JavaScript, not open
    # Chrome's native HTTP Basic dialog. Other routes keep their Basic challenges.
    text = text.replace('  location /api/ {',
        '  location = /api/auth/session { if ($wavy_origin_denied) { return 403; } '
        'include /etc/nginx/wavy-https/api.conf; proxy_hide_header WWW-Authenticate; }\n'
        '  location /api/ {')
    return text


def permanent_local_shell(host):
    if host != 'recettelocal.wavyservices.fr':
        raise ValueError('Le profil permanent est réservé à RECETTE locale MSI')
    text=shell_config(host)
    text=text.replace('include /etc/nginx/wavy-https/closed.conf;', 'include /etc/nginx/wavy-https/local-pwa.conf;')
    text=text.replace('location = /pwa-integration.json { add_header Cache-Control "no-store" always; }', '')
    text=text.replace('server { listen 127.0.0.1:8087;', 'server { listen 127.0.0.1:8087; location = /__pwa_enabled { default_type application/json; return 200 \'{"enabled":true}\'; }')
    return text


def permanent_local_routes(host):
    if host != 'recettelocal.wavyservices.fr':
        raise ValueError('Profil local interdit pour ce domaine')
    # Authorization comes from the existing Notes API, including its roles/company checks.
    # No lease, global allow header, local fake identity or alternate authentication.
    return '''resolver 127.0.0.11 valid=5s ipv6=off;
set $local_pwa_origin http://wavy-pwa-recette;
location = /__local_pwa_authorized {
 internal; access_log off;
 proxy_pass $private_api_origin/api/notes-frais;
 proxy_pass_request_body off; proxy_set_header Content-Length "";
 proxy_set_header Cookie $http_cookie;
 proxy_set_header Host recettelocal.wavyservices.fr;
 proxy_set_header X-Forwarded-Host recettelocal.wavyservices.fr;
 proxy_set_header X-Forwarded-Proto https; proxy_set_header X-Forwarded-Port 443;
 proxy_set_header X-Forwarded-For $http_x_forwarded_for; proxy_set_header Forwarded "";
}
location = /pwa { auth_request /__local_pwa_authorized;
 error_page 401 403 500 502 503 504 = @local_pwa_closed;
 proxy_pass http://127.0.0.1:8087;
}
location ^~ /pwa/ { auth_request /__local_pwa_authorized;
 error_page 401 403 500 502 503 504 = @local_pwa_closed;
 rewrite ^/pwa/(.*)$ /$1 break; proxy_pass $local_pwa_origin$uri$is_args$args;
 proxy_set_header Host recettelocal.wavyservices.fr;
 proxy_set_header X-Forwarded-Proto https;
 proxy_cache off; add_header Cache-Control "no-store" always;
}
location @local_pwa_closed { add_header Cache-Control "no-store" always; return 404; }
# Availability only: ERP roles and backend authorization still control access.
location = /pwa-integration.json { default_type application/json;
 alias /etc/nginx/wavy-https/pwa-integration.json;
 open_file_cache off; add_header Cache-Control "no-store" always;
}
'''


CLOSED = '''resolver 127.0.0.11 valid=5s ipv6=off;
# Fermeture indépendante de la PWA, pas de marqueur livré.
location = /pwa { add_header Cache-Control "no-store" always; return 404; }
location ^~ /pwa/ { add_header Cache-Control "no-store" always; return 404; }
location = /api/pwa { return 404; }
location ^~ /api/pwa/ { return 404; }
location = /api/notes-frais { if ($request_method !~ ^(GET|HEAD)$) { return 403; } include /etc/nginx/wavy-https/api.conf; }
location ^~ /api/notes-frais/ { if ($request_method !~ ^(GET|HEAD)$) { return 403; } include /etc/nginx/wavy-https/api.conf; }
'''


def render(target, output, subnet):
    if target != 'recettelocal':
        raise ValueError('Overlay distant non autorisé avant qualification locale et adaptation contrôlée du profil HTTPS')
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError('Répertoire de sortie neuf requis ; aucun écrasement')
    trust = proxy_regex(subnet)
    p = plan(target)
    output.mkdir(mode=0o700, parents=False)
    host = TARGETS[target][0]
    (output / 'shell.conf.template').write_text(shell_config(host))
    (output / 'closed.conf').write_text(CLOSED)
    headers = ('proxy_pass ${API_UPSTREAM};\nproxy_set_header Host ' + host + ';\n'
               'proxy_set_header X-Forwarded-Host ' + host + ';\nproxy_set_header X-Forwarded-Proto https;\n'
               'proxy_set_header X-Forwarded-Port 443;\nproxy_set_header X-Forwarded-For $http_x_forwarded_for;\n'
               'proxy_set_header Forwarded "";\nadd_header Cache-Control "no-store" always;\n')
    # Ce fichier inclus ne passe pas dans envsubst : upstream variable Nginx défini au niveau serveur.
    (output / 'api.conf').write_text(headers.replace('${API_UPSTREAM}', '$private_api_origin'))
    lines = ['services:']
    for component, image in p['images'].items():
        service = 'wavy-' + component + '-recette'
        lines += ['  ' + service + ':', '    image: ' + image, '    ports: !override ' + ('["127.0.0.1:24207:80"]' if component == 'erp-shell' else '[]')]
        env = {}
        if component.endswith('-api'):
            env.update(WAVY_CORS_ALLOWED_ORIGIN_PATTERNS=p['origin'], SPRING_SQL_INIT_MODE='never')
        if component == 'socle-api':
            env.update(SERVER_SERVLET_SESSION_COOKIE_SECURE='true', SERVER_SERVLET_SESSION_COOKIE_HTTP_ONLY='true',
                       SERVER_SERVLET_SESSION_COOKIE_SAME_SITE='strict', WAVY_BOOTSTRAP_ENABLED='false',
                       SERVER_FORWARD_HEADERS_STRATEGY='native', SERVER_TOMCAT_REMOTEIP_INTERNAL_PROXIES=trust,
                       SERVER_TOMCAT_REMOTEIP_PROTOCOL_HEADER='X-Forwarded-Proto',
                       SERVER_TOMCAT_REMOTEIP_HOST_HEADER='X-Forwarded-Host', SERVER_TOMCAT_REMOTEIP_PORT_HEADER='X-Forwarded-Port')
        if component == 'factures-api':
            env['WAVY_AI_ACHAT_AUTO_CREATION_ENABLED'] = 'false'
        if component == 'gateway':
            env['SPRING_APPLICATION_JSON'] = json.dumps(gateway_settings(p['origin']), separators=(',', ':'))
        if env:
            lines.append('    environment:')
            lines += ['      ' + key + ': ' + json.dumps(value) for key, value in env.items()]
        if component.endswith('-front'):
            lines += ['    healthcheck:', '      test: ' + json.dumps(['CMD','wget','-q','-O','/dev/null','http://127.0.0.1/']), '      interval: 3s', '      timeout: 2s', '      retries: 5', '      start_period: 2s']
        if component == 'erp-shell':
            lines += ['    healthcheck:', '      test: ' + json.dumps(['CMD','wget','-q','-O','/dev/null','--header=Host: '+host,'http://127.0.0.1/']), '      interval: 3s', '      timeout: 2s', '      retries: 5', '      start_period: 2s']
            lines += ['    volumes:', '      - type: bind', '        source: ' + str(output / 'shell.conf.template'),
                      '        target: /etc/nginx/templates/default.conf.template', '        read_only: true', '        bind: {create_host_path: false}',
                      '      - type: bind', '        source: ' + str(output), '        target: /etc/nginx/wavy-https',
                      '        read_only: true', '        bind: {create_host_path: false}']
    (output / 'compose.https.yml').write_text('\n'.join(lines) + '\n')
    (output / 'plan.json').write_text(json.dumps(p, indent=2) + '\n')
    for file in output.iterdir():
        file.chmod(0o600 if file.name == 'plan.json' else 0o644)
    return {'directory': str(output), 'planSha256': p['planSha256'], 'mutationsExecuted': False,
            'status': 'CONFIGURATION_ONLY_NOT_DEPLOY_AUTHORIZATION'}


def check_images(target, components=None):
    p = plan(target)
    images={k:v for k,v in p['images'].items() if components is None or k in components}
    for component, reference in images.items():
        image = json.loads(run(['docker', 'image', 'inspect', reference]))[0]
        if reference not in image.get('RepoDigests', []) or (image['Os'], image['Architecture']) != ('linux', 'amd64'):
            raise ValueError('Image non épinglée ou plateforme incorrecte : ' + component)
        labels = image.get('Config', {}).get('Labels') or {}
        if labels.get('org.opencontainers.image.source') != 'https://github.com/fabffo/wavy-' + component:
            raise ValueError('Source OCI inattendue : ' + component)
        version, revision = p['imageVersions'][component].rsplit('-', 1)
        if labels.get('org.opencontainers.image.version') != version or not labels.get('org.opencontainers.image.revision', '').startswith(revision):
            raise ValueError('Version/révision OCI inattendue : ' + component)
    return {'imagesLocallyVerified': len(images), 'planSha256': p['planSha256'], 'pullOrBuild': False}


def probe_local_https():
    # Windows loopback explicite : aucune résolution DNS publique ni requête VM.
    host = TARGETS['recettelocal'][0]
    origin = 'https://' + host
    checks = [('GET', '/', None, 200), ('GET', '/api/auth/session', None, 401),
              ('GET', '/pwa/', None, 404), ('OPTIONS', '/api/auth/session', origin, 200),
              ('OPTIONS', '/api/auth/session', 'https://untrusted.invalid', 403)]
    observed = []
    for method, path, request_origin, expected in checks:
        cmd = ['curl.exe', '--silent', '--show-error', '--ssl-revoke-best-effort',
               '--max-time', '8', '--resolve', host + ':443:127.0.0.1',
               '--dump-header', '-', '--output', 'NUL', '--request', method]
        if request_origin: cmd += ['--header', 'Origin: ' + request_origin]
        if method == 'OPTIONS': cmd += ['--header', 'Access-Control-Request-Method: POST',
                                        '--header', 'Access-Control-Request-Headers: content-type']
        result = subprocess.run(cmd + [origin + path], capture_output=True, timeout=12)
        if result.returncode: raise ValueError('Sonde HTTPS refusée : vérifier confiance CA/connectivité, jamais utiliser -k')
        lines = result.stdout.decode(errors='replace').splitlines()
        headers = {}
        status = None
        for line in lines:
            if line.startswith('HTTP/'):
                status = int(line.split()[1]); headers = {}
            elif ':' in line:
                key, value = line.split(':', 1); headers[key.lower()] = value.strip()
        cors_ok = (headers.get('access-control-allow-origin') == origin and
                   headers.get('access-control-allow-credentials') == 'true') if method == 'OPTIONS' and request_origin == origin else True
        observed.append({'method': method, 'path': path, 'expected': expected,
                         'observed': status, 'passed': status == expected and cors_ok,
                         'corsHeaderCorrect': cors_ok})
    return {'scope': 'WINDOWS_LOOPBACK_LOCAL_ONLY_NO_CREDENTIALS', 'checks': observed,
            'passed': all(row['passed'] for row in observed), 'tlsChainValidation': True,
            'revocation': 'Windows best effort for offline internal CA, certificate chain still checked'}


def main():
    if len(sys.argv)>1 and sys.argv[1]=='--local-cli':
        return local_main(sys.argv[2:])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('environment', choices=TARGETS)
    parser.add_argument('action', nargs='?', default='plan', choices=['plan', 'check', 'render', 'probe', 'deploy', 'resume', 'rollback', 'auth-test', 'auth-recover', 'functional-test', 'functional-recover', 'browser-diagnostic', 'browser-recover', 'manual-open', 'manual-close'])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--docker-subnet')
    parser.add_argument('--run-dir', type=Path)
    parser.add_argument('--authorization', type=Path)
    parser.add_argument('--confirm-close', action='store_true')
    args = parser.parse_args()
    try:
        if args.action in ('auth-test', 'auth-recover', 'functional-test', 'functional-recover', 'browser-diagnostic', 'browser-recover', 'manual-open', 'manual-close'):
            if args.environment != 'recettelocal' or not args.run_dir or not args.authorization:
                raise ValueError('Phase auth réservée à MSI local avec dossier privé et autorisation explicites')
            if args.action=='manual-close' and not args.confirm_close:
                raise ValueError('Fermeture refusée sans --confirm-close : accord explicite de fin des tests requis')
            import importlib.util
            spec = importlib.util.spec_from_file_location('local_auth_runtime', HERE / 'local_auth.py')
            auth = importlib.util.module_from_spec(spec); sys.modules[spec.name]=auth; spec.loader.exec_module(auth)
            profile='manual' if args.action.startswith('manual-') else ('anonymous' if args.action.startswith('browser-') else args.action.startswith('functional-'))
            if args.action=='manual-close':
                fspec=importlib.util.spec_from_file_location('local_cycle_close',HERE/'local_functional.py')
                fm=importlib.util.module_from_spec(fspec);fspec.loader.exec_module(fm)
                cycle=fm.LocalCycle(auth)
                if cycle.directory==args.run_dir.absolute():
                    cycle.prepare_close()
                    if cycle.scope=='HTTPS_LOCAL_CYCLE_READONLY_NO_FIXTURES':
                        profile='cycle';auth.CYCLE_COMPONENTS=cycle.components;auth.CYCLE_DATABASES=tuple(cycle.session['baseline'])
            result = auth.execute(args.run_dir, args.authorization, recover=args.action.endswith('-recover') or args.action=='manual-close', functional=profile)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result['passed'] else 1
        if args.action in ('deploy', 'resume', 'rollback'):
            # Ni deploy.sh historique (tags actifs), ni runner direct, ni faux reçu PREPROD.
            raise ValueError('Mutation bloquée : qualification HTTPS locale, autorisation des données et intégration du profil externe aux gardes existants requises ; voir INSTALLATION.txt')
        if args.action == 'probe':
            if args.environment != 'recettelocal': raise ValueError('Sondes distantes interdites avant GO local et autorisation VM')
            result = probe_local_https()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result['passed'] else 1
        if args.action == 'render':
            if not args.output or not args.docker_subnet:
                raise ValueError('--output et --docker-subnet explicites requis')
            result = render(args.environment, args.output, args.docker_subnet)
        else:
            result = check_images(args.environment) if args.action == 'check' else plan(args.environment)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, subprocess.SubprocessError, KeyError) as error:
        print(str(error) if isinstance(error, ValueError) else 'Préparation refusée, sortie sensible masquée', file=sys.stderr)
        return 1
    return 0


def local_main(argv):
    parser=argparse.ArgumentParser(prog='./wavy local',description='Cycle MSI HTTPS, images immuables, aucun rebuild/volume supprimé.')
    parser.add_argument('action',choices=['up','down','restart','status','logs','test','pwa-open','pwa-close'])
    parser.add_argument('modules',nargs='*',choices=(*MODULES,'all'))
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--layout',choices=['before','after'],help='test : captures et mesures responsive Chrome')
    parser.add_argument('--build-frontends',action='store_true',help='up/restart : reconstruire les fronts pour MSI uniquement')
    parser.add_argument('--chrome',action='store_true',help='test : parcours Chrome réel, sans écriture métier automatique')
    parser.add_argument('--databases',action='store_true',help='down : arrêter aussi les bases devenues inutilisées, sans supprimer les volumes')
    parser.add_argument('--tail',type=int,default=100)
    args=parser.parse_args(argv)
    if args.action in ('pwa-open','pwa-close') and args.modules:parser.error('pwa-open/pwa-close ne prennent pas de module')
    if args.databases and args.action!='down':parser.error('--databases est réservé à down')
    if not 0<=args.tail<=10000:parser.error('--tail doit être compris entre0 et10000')
    if 'all' in args.modules and len(args.modules)!=1:parser.error('all doit être utilisé seul')
    selected=list(MODULES) if not args.modules or args.modules==['all'] else list(dict.fromkeys(args.modules))
    try:
        import importlib.util
        spec=importlib.util.spec_from_file_location('local_cycle_auth',HERE/'local_auth.py')
        a=importlib.util.module_from_spec(spec);sys.modules[spec.name]=a;spec.loader.exec_module(a)
        fspec=importlib.util.spec_from_file_location('local_cycle_runtime',HERE/'local_functional.py')
        f=importlib.util.module_from_spec(fspec);fspec.loader.exec_module(f)
        if args.layout and args.action!='test':parser.error('--layout est réservé à test')
        if args.chrome and args.action!='test':parser.error('--chrome est réservé à test')
        cycle=f.PermanentLocalCycle(a)
        if args.build_frontends and args.action not in ('up','restart'):parser.error('--build-frontends est réservé à up/restart')
        if args.build_frontends and not args.dry_run:cycle.build_frontends()
        result=cycle.command(args.action,selected,dry_run=args.dry_run,databases=args.databases,tail=args.tail)
        if (args.chrome or args.layout) and result.get('passed') and not args.dry_run:result['chrome']=cycle.browser_test(layout=args.layout)
        if result is not None:print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if result is None or result.get('passed',True) else 1
    except (ValueError,OSError,subprocess.SubprocessError,KeyError) as error:
        print(str(error) if isinstance(error,ValueError) else 'Cycle local refusé ; diagnostics sensibles masqués',file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
