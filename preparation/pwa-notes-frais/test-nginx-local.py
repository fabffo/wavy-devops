#!/usr/bin/env python3
"""nginx -t sur l'image Shell locale exacte, sans pull/réseau/serveur."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

C = Path(__file__).resolve().parent
if os.environ.get('DOCKER_HOST') or not subprocess.check_output(
        ['docker', 'context', 'inspect', '--format', '{{.Endpoints.docker.Host}}'],
        text=True).strip().startswith('unix://'):
    raise SystemExit('Daemon Docker local Unix requis')
image = json.loads((C / 'release-plan.json').read_text())['images']['erp-shell']['reference']
base = ['docker', 'run', '--rm', '--pull', 'never', '--network', 'none', '--read-only']
raw = subprocess.check_output(base + ['--entrypoint', 'cat', image,
                                     '/etc/nginx/templates/default.conf.template'], text=True)
raw = re.sub(r'\$\{[A-Z_]+_UPSTREAM\}', 'http://127.0.0.1:8088/', raw)
with tempfile.TemporaryDirectory(prefix='wavy-nginx-pwa-') as tmp:
    tmp = Path(tmp)
    conf = tmp / 'nginx.conf'
    conf.write_text('events {}\nhttp {\n' + raw + '\n}\n')
    for name in ('nginx-pwa-disabled.conf', 'nginx-pwa-enabled.conf'):
        subprocess.run(base + ['--tmpfs', '/var/cache/nginx', '--tmpfs', '/var/run',
            '--add-host', 'wavy-pwa-preprod:127.0.0.1',
            '--mount', f'type=bind,source={conf},target=/etc/nginx/nginx.conf,readonly',
            '--mount', f'type=bind,source={C / name},target=/etc/nginx/pwa-route.conf,readonly',
            '--entrypoint', 'nginx', image, '-t'], check=True)
    # Certificat éphémère fictif, uniquement pour le parseur TLS ; jamais conservé.
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                    '-keyout', str(tmp / 'privkey.pem'), '-out', str(tmp / 'fullchain.pem'),
                    '-days', '1', '-subj', '/CN=example.invalid'], check=True, capture_output=True)
    for name in ('edge-https.conf.template', 'edge-rollback-readonly.conf.template'):
        raw = (C / name).read_text().replace('${WAVY_PUBLIC_SERVER_NAME}', 'example.invalid')
        conf.write_text('events {}\nhttp {\n' + raw + '\n}\n')
        subprocess.run(base + ['--tmpfs', '/var/cache/nginx', '--tmpfs', '/var/run',
            '--mount', f'type=bind,source={conf},target=/etc/nginx/nginx.conf,readonly',
            '--mount', f'type=bind,source={tmp},target=/run/tls,readonly',
            '--mount', f'type=bind,source={C / "edge-pwa-gate.conf"},target=/etc/nginx/wavy/edge-pwa-gate.conf,readonly',
            '--entrypoint', 'nginx', image, '-t'], check=True)
print('Nginx : route fermée, candidate, edge HTTPS et rollback conformes en syntaxe uniquement')
