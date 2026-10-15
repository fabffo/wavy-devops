#!/usr/bin/env python3
"""Validation Nginx avec une image DÉJÀ locale, sans pull, réseau ou serveur démarré."""
import os,re,subprocess,tempfile,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if os.environ.get('DOCKER_HOST') or not subprocess.check_output(['docker','context','inspect','--format','{{.Endpoints.docker.Host}}']).decode().strip().startswith('unix://'):
    raise SystemExit('Daemon Docker local Unix requis')
image=sys.argv[1] if len(sys.argv)>1 else 'ghcr.io/fabffo/wavy-erp-shell:0.1.0-521c2f8'
with tempfile.TemporaryDirectory(prefix='wavy-nginx-pwa-') as tmp:
    conf=Path(tmp)/'nginx.conf'
    raw=(ROOT.parent/'wavy-erp-shell/nginx.conf').read_text()
    raw=re.sub(r'\$\{[A-Z_]+_UPSTREAM\}','http://127.0.0.1:8088/',raw)
    conf.write_text('events {}\nhttp {\n'+raw+'\n}\n')
    for snippet in [ROOT.parent/'wavy-erp-shell/nginx-pwa-disabled.conf',Path(__file__).with_name('nginx-pwa-enabled.conf')]:
        subprocess.run(['docker','run','--rm','--pull','never','--network','none','--read-only','--tmpfs','/var/cache/nginx','--tmpfs','/var/run','--add-host','wavy-pwa-preprod:127.0.0.1','--mount',f'type=bind,source={conf},target=/etc/nginx/nginx.conf,readonly','--mount',f'type=bind,source={snippet.resolve()},target=/etc/nginx/pwa-route.conf,readonly','--entrypoint','nginx',image,'-t'],check=True)
print('Nginx : configuration fermée et candidate conformes')
