#!/usr/bin/env python3
"""Extension candidate stricte du validateur actif ; aucune activation implicite."""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
CANDIDATE = Path(__file__).resolve().parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base = load(ROOT / 'scripts/preprod_config.py', 'active_config')
bundle = load(CANDIDATE / 'validate-bundle.py', 'bundle')
check = base.check


def read_plan(path):
    data = json.loads(Path(path).read_text())
    bundle.validate(data)
    return data


def file_guard(path):
    check(path.is_absolute() and not path.is_symlink() and path.resolve() == path,
          'Chemin bind non canonique')
    check(path.parent.stat().st_uid in (0, os.getuid()), 'Propriétaire bind invalide')
    check(path.is_file() and path.stat().st_uid in (0, os.getuid()) and stat.S_IMODE(path.stat().st_mode) == 0o644,
          'Bind : fichier régulier 0644 requis')
    check(not any(p.is_symlink() or (p.stat().st_mode & 0o022 and not p.stat().st_mode & stat.S_ISVTX) for p in path.parents),
          'Répertoire bind modifiable ou symbolique')


def compose_args(env_path, args, plan, mode='closed'):
    check(mode in ('closed', 'open'), 'Mode inconnu')
    cmd, clean = base.compose_args(env_path, [])
    clean = {k: v for k, v in clean.items()
             if not k.startswith('PWA_RELEASE_') and k != 'WAVY_PWA_CANDIDATE_DIR'}
    clean['WAVY_PWA_CANDIDATE_DIR'] = str(CANDIDATE)
    for component, image in plan['images'].items():
        clean['PWA_RELEASE_' + component.upper().replace('-', '_') + '_IMAGE'] = image['reference']
    cmd += ['-f', str(CANDIDATE / 'compose.override.yml')]
    if mode == 'open':
        cmd += ['-f', str(CANDIDATE / 'compose.activation.yml')]
    return cmd + args, clean


def render(env_path, plan, mode='closed'):
    cmd, clean = compose_args(env_path, ['config', '--format', 'json'], plan, mode)
    result = subprocess.run(cmd, env=clean, capture_output=True)
    check(result.returncode == 0, 'Rendu Compose candidat refusé')
    return json.loads(result.stdout)


def validate_rendered(config, baseline, plan, mode='closed'):
    """N'autorise que les différences décrites ; le reste doit égaler le rendu actif."""
    check(mode in ('closed', 'open'), 'Mode incohérent')
    bundle.validate(plan)
    normalized = copy.deepcopy(config)
    services = normalized['services']
    check(set(services) == set(baseline['services']), 'Lot de services incomplet ou supplémentaire')
    for component, image in plan['images'].items():
        name = 'wavy-' + component + '-preprod'
        check(services[name]['image'] == image['reference'], 'Image candidate non épinglée')
        services[name]['image'] = baseline['services'][name]['image']
    api = services['wavy-factures-api-preprod']
    expected_mount = {'type': 'volume', 'source': 'documents-preprod',
                      'target': '/app/justificatifs', 'volume': {'nocopy': True, 'subpath': 'notes-frais'}}
    check(api.get('volumes') == [expected_mount], 'Montage documentaire non autorisé')
    api.pop('volumes')
    for key, value in {'WAVY_FACTURES_STOCKAGE_JUSTIFICATIFS': '/app/justificatifs',
                       'WAVY_FACTURES_JUSTIFICATIF_MAX_BYTES': '10485760',
                       'WAVY_FACTURES_MULTIPART_MAX_FILE_SIZE': '10MB',
                       'WAVY_FACTURES_MULTIPART_MAX_REQUEST_SIZE': '11MB'}.items():
        check(api['environment'].get(key) == value, 'Politique documentaire incohérente')
        api['environment'].pop(key)
    shell = services['wavy-erp-shell-preprod']
    suffix = 'enabled' if mode == 'open' else 'disabled'
    expected = []
    for source, target in [(f'nginx-pwa-{suffix}.conf', '/etc/nginx/pwa-route.conf'),
                           (f'pwa-integration.{suffix}.json', '/usr/share/nginx/html/pwa-integration.json')]:
        path = CANDIDATE / source
        file_guard(path)
        if source.endswith('.json'):
            check(json.loads(path.read_text()) == {'enabled': mode == 'open', 'justificatifMaxBytes': 10485760},
                  'Commutateur PWA incohérent')
        elif mode == 'closed':
            content = '\n'.join(line for line in path.read_text().splitlines() if not line.startswith('#'))
            check(content.strip() == 'location = /pwa { return 404; }\nlocation /pwa/ { return 404; }',
                  'Fermeture Nginx incohérente')
        expected.append({'type': 'bind', 'source': str(path), 'target': target,
                         'read_only': True, 'bind': {}})
    check(shell.get('volumes') == expected, 'Bind non autorisé')
    shell.pop('volumes')
    for component in ('factures-api', 'factures-front', 'pwa'):
        name = 'wavy-' + component + '-preprod'
        check(shell['depends_on'].get(name) == {'condition': 'service_healthy', 'required': True},
              'Dépendance candidate incohérente')
    shell['depends_on'] = baseline['services']['wavy-erp-shell-preprod']['depends_on']
    check(normalized == baseline, 'Différence hors périmètre candidat')
    return normalized


def validate(env_path, plan, mode='closed'):
    baseline = base.render(env_path)
    config = render(env_path, plan, mode)
    normalized = validate_rendered(config, baseline, plan, mode)
    original = base.render
    try:
        base.render = lambda path: normalized
        base.validate(env_path)  # Tous les garde-fous actifs restent obligatoires.
    finally:
        base.render = original
    env = base.dotenv(env_path)
    check(env.get('WAVY_ACCESS_MODE') == 'https' and env.get('WAVY_COOKIE_SECURE') == 'true',
          'HTTPS et cookie Secure obligatoires pour la PWA')
    check(env.get('WAVY_PUBLIC_HTTP_PORT', '24443') == '24443',
          'Le modèle edge candidat exige le port loopback ERP 24443')
    return config


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['validate', 'compose'])
    parser.add_argument('env', type=Path)
    parser.add_argument('--plan', type=Path, default=CANDIDATE / 'release-plan.json')
    parser.add_argument('--mode', choices=['closed', 'open'], default='closed')
    args, remaining = parser.parse_known_args()
    try:
        if args.action == 'compose':
            allowed = remaining in (['config', '--quiet'], ['config', '--format', 'json'])
            check(allowed, 'Commande Compose hors périmètre')
            check(args.mode != 'open' or remaining[0] == 'config',
                  'Activation exclusivement via orchestrateur validé')
        plan = read_plan(args.plan)
        validate(args.env, plan, args.mode)
        if args.action == 'compose':
            cmd, clean = compose_args(args.env, remaining, plan, args.mode)
            os.execvpe(cmd[0], cmd, clean)
    except Exception:
        parser.exit(1, 'Configuration candidate refusée (détails masqués).\n')
