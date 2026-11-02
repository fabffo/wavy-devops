#!/usr/bin/env python3
"""Relevé Factures local en lecture seule ; aucune clé ni sortie Docker brute affichée."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from release_images import recette_compose, release

ROOT = Path(__file__).resolve().parent.parent
AI_KEYS = ('WAVY_AI_PROVIDER', 'WAVY_AI_MODEL', 'WAVY_AI_API_KEY',
           'WAVY_AI_TIMEOUT_SECONDS', 'WAVY_AI_MAX_FILE_SIZE_MB')


def docker_json(args):
    result = subprocess.run(['docker', *args], capture_output=True, text=True)
    if result.returncode:
        raise ValueError('Inspection Docker indisponible ; sortie brute masquée.')
    return json.loads(result.stdout)


def ai_summary(values):
    provider = values.get('WAVY_AI_PROVIDER', '') or ''
    model = values.get('WAVY_AI_MODEL', '') or ''
    # Même une clé collée accidentellement dans provider/model reste masquée.
    return {'provider': provider if provider in ('anthropic', 'ANTHROPIC', 'none', 'NONE', '') else 'autre (masqué)',
            'model': model if re.fullmatch(r'claude-[a-zA-Z0-9._-]{1,100}', model) else ('présent (masqué)' if model else 'absent'),
            'present': {key: bool(str(values.get(key) or '').strip()) for key in AI_KEYS},
            'springOverridePresent': {key: bool(values.get(key)) for key in
                ('SPRING_APPLICATION_JSON', 'JAVA_TOOL_OPTIONS', 'JDK_JAVA_OPTIONS', 'WAVY_AI_APIKEY')}}


def provider_statuses():
    result = subprocess.run(['docker', 'logs', '--tail', '400', '--since', '24h', 'wavy-factures-api-recette'],
                            capture_output=True, text=True)
    if result.returncode:
        return {'available': False, 'httpStatuses': []}
    # Ni corps fournisseur, nom de document, clé, ni ligne complète dans le relevé.
    statuses = re.findall(r'Erreur Anthropic extraction[^\n]*?statusHttp=(\d{3}|n/a)', result.stdout + result.stderr)
    return {'available': True, 'httpStatuses': statuses[-10:]}


def inspect_report(root):
    _, _, images = release(root, 'recette')
    config = recette_compose(root, ['config', '--format', 'json'], capture=True)
    # Compose config sérialise les dollars littéraux en $$ ; up les transmet en $ .
    wanted = {key: str(value or '').replace('$$', '$') for key, value in
              config['services']['wavy-factures-api-recette']['environment'].items()}
    report = {'readOnly': True, 'providerRequestExecuted': False, 'images': {}, 'aiRendered': ai_summary(wanted)}
    for component in ('factures-front', 'factures-api'):
        obj = docker_json(['inspect', f'wavy-{component}-recette'])[0]
        image = docker_json(['image', 'inspect', obj['Image']])[0]
        repo, digest = images[component].split('@')
        pinned = repo.rsplit(':', 1)[0] + '@' + digest
        expected_revision = repo.rsplit('-', 1)[1]
        labels = image.get('Config', {}).get('Labels', {})
        revision = labels.get('org.opencontainers.image.revision', '')
        version = labels.get('org.opencontainers.image.version', '')
        digest_pattern = r'ghcr\.io/fabffo/wavy-' + re.escape(component) + r'@sha256:[0-9a-f]{64}'
        override_target = '/app/app.jar' if component == 'factures-api' else '/usr/share/nginx/html'
        report['images'][component] = {
            'expected': images[component], 'running': bool(obj.get('State', {}).get('Running')),
            'expectedDigestInActiveImage': pinned in image.get('RepoDigests', []),
            'expectedRevisionInActiveImage': labels.get('org.opencontainers.image.revision') == expected_revision,
            'containerImageId': obj['Image'],
            'activeRepoDigests': [value for value in image.get('RepoDigests', [])
                                  if re.fullmatch(digest_pattern, value)],
            'activeRevision': revision if re.fullmatch(r'[0-9a-f]{7,40}', revision) else 'absente ou masquée',
            'activeVersion': version if re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version) else 'absente ou masquée',
            'artifactOverridePresent': any(m.get('Destination') == override_target for m in obj.get('Mounts', [])),
        }
        if component == 'factures-api':
            active = dict(item.split('=', 1) for item in obj.get('Config', {}).get('Env', []) if '=' in item)
            report['aiActive'] = ai_summary(active)
            report['aiMatchesRendered'] = {key: active.get(key, '') == str(wanted.get(key) or '') for key in AI_KEYS}
            report['springCommandOverridePresent'] = any('wavy.ai' in str(arg).lower() or 'wavy_ai' in str(arg).lower()
                for arg in (obj.get('Config', {}).get('Cmd') or []) + (obj.get('Config', {}).get('Entrypoint') or []))
    report['recentProviderErrors'] = provider_statuses()
    return report


def main():
    try:
        if os.environ.get('DOCKER_HOST') or os.environ.get('DOCKER_CONTEXT'):
            raise ValueError('Contexte distant interdit ; lancer sur la machine à diagnostiquer.')
        context = docker_json(['context', 'inspect'])[0]
        if context['Endpoints']['docker']['Host'] != 'unix:///var/run/docker.sock':
            raise ValueError('Socket Docker système local requis.')
        print(json.dumps(inspect_report(ROOT), indent=2, ensure_ascii=False))
        return 0
    except Exception:
        print(json.dumps({'readOnly': True, 'error': 'Relevé indisponible. Vérifier localement le contexte Docker, les conteneurs et la configuration RECETTE ; détails masqués.'}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    sys.exit(main())
