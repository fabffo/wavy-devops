#!/usr/bin/env python3
"""Fixtures locales Nginx exact Shell, aucun pull/build/port publié/volume métier."""
import json
import importlib.util
import threading
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

P = Path(__file__).resolve().parent
C = P.parent

class Private(unittest.TestCase):
    def test_shell_routes_and_closure_without_reload(self):
        self.run_fixture()

    def test_pwa_unavailable_preserves_erp_and_can_close(self):
        self.run_fixture(offline=True)

    def test_gate_unavailable_is_closed_and_preserves_erp(self):
        self.run_fixture(gate_offline=True)

    def run_fixture(self, offline=False, gate_offline=False, invalid_marker=None, extra_closed_checks=""):
        endpoint = subprocess.check_output(['docker','context','inspect','--format','{{.Endpoints.docker.Host}}'],text=True).strip()
        self.assertFalse(os.environ.get('DOCKER_HOST') or os.environ.get('DOCKER_CONTEXT'))
        self.assertTrue(endpoint.startswith('unix://'))
        image = json.loads((C/'release-plan.json').read_text())['images']['erp-shell']['reference']
        shell = re.sub(r'\$\{[A-Z_]+_UPSTREAM\}', 'http://127.0.0.1:8081', (P/'shell.conf.template').read_text())
        routes = (P/'routes.conf').read_text().replace('http://wavy-pwa-preprod','http://127.0.0.1:8082')
        if offline: routes = routes.replace('127.0.0.1:8082', '127.0.0.1:1')
        if gate_offline: routes = routes.replace('gate.sock', 'absent.sock')
        conf = 'events {}\nhttp {\n'+shell+'''
server { listen 8081; location / { return 200 "ERP:$request_uri:$http_cookie"; } }
server { listen 8082; location / { return 200 "PWA:$request_uri"; } }
}'''
        # Root ERP uses try_files; fixtures for every module and common API use real locations.
        script = '''mkdir -p /run/wavy-private-pwa
nginx -t
nginx
trap 'nginx -s quit' EXIT
check() {
  code="$1"; method="$2"; path="$3"; content="$4"
  actual=$(curl --silent --show-error --path-as-is --max-time 5 -X "$method" -H 'Cookie: WAVY_SESSION=fixture' -D /tmp/headers -o /tmp/body -w '%{http_code}' "http://127.0.0.1$path")
  [ "$actual" = "$code" ] || { cat /tmp/headers; exit 1; }
  if [ -n "$content" ]; then grep -F "$content" /tmp/body; fi
}
'''
        for state in ('closed','open','closed-again'):
            script += ('touch /fixture/authorized\n' if state=='open' else 'rm -f /fixture/authorized /run/wavy-private-pwa/open\n')
            if state == 'closed' and invalid_marker:
                script += invalid_marker + '\n'
            if state == 'closed': script += extra_closed_checks
            script += f"check {'308' if state=='open' and not gate_offline else '404'} GET /pwa ''\n"
            for path in ('/pwa/','/pwa/main.js?v=1','/pwa/main.js','/pwa/manifest.webmanifest','/pwa/ngsw-worker.js','/pwa/ngsw.json','/pwa/notes-frais','/pwa%2Fmain.js','/api/pwa/session'):
                code = ('404' if offline and not path.startswith('/api/') else '200') if state=='open' and not gate_offline else '404'
                body = ('PWA:/'+path.split('/pwa/',1)[1] if path.startswith('/pwa/') else '') if state=='open' and not offline and not gate_offline else ''
                script += f"check {code} GET '{path}' '{body}'\n"
            for path in ('/api/auth/session','/api/tiers/health','/api/notes-frais/1/justificatif/contenu',*[f'/modules/{m}/' for m in ('socle','tiers','contrats','factures','tresorerie')]):
                script += f"check 200 GET '{path}' 'WAVY_SESSION=fixture'\n"
            script += "check 200 GET / 'ERP ROOT'\ncheck 200 POST /api/tiers/fixture 'ERP:'\n"
            endpoints = ('/api/notes-frais', '/api/notes-frais/1',
                         '/api/notes-frais/1/justificatif', '/api/notes-frais/transformer-facture-achat',
                         *('/api/notes-frais/1/'+action for action in
                           ('valider','refuser','soumettre','recalculer','annuler','transformer-factures-achats')))
            for path in endpoints:
                for method in ('POST','PUT','PATCH','DELETE','OPTIONS'):
                    script += f"check {'200' if state=='open' and not gate_offline else '403'} {method} '{path}' ''\n"
        with tempfile.TemporaryDirectory() as tmp:
            t=Path(tmp); t.chmod(0o755)
            (t/'nginx.conf').write_text(conf);(t/'routes.conf').write_text(routes)
            spec=importlib.util.spec_from_file_location('session_gate',P/'session-gate.py')
            gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)
            lease=gate.Lease()
            class FixtureHandler(gate.handler(lease)):
                def do_GET(handler):
                    if (t/'authorized').exists():
                        if lease.grant is None: lease.authorize('WAVY_SESSION=fixture',900)
                    else: lease.close()
                    super().do_GET()
            server=gate.Server(str(t/'gate.sock'),FixtureHandler)
            (t/'gate.sock').chmod(0o666)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            (t/'index.html').write_text('ERP ROOT')
            args=['docker','run','--rm','--pull','never','--network','none','--read-only']
            for dest in ('/tmp','/var/cache/nginx','/var/run','/run/wavy-private-pwa'):
                args += ['--tmpfs',dest]
            for src,dest in [('nginx.conf','/etc/nginx/nginx.conf'),('routes.conf','/etc/nginx/private-pwa/routes.conf'),('index.html','/usr/share/nginx/html/index.html')]:
                args += ['--mount',f'type=bind,source={t/src},target={dest},readonly']
            args += ['--mount',f'type=bind,source={t},target=/run/wavy-private-pwa-gate,readonly', '--mount',f'type=bind,source={t},target=/fixture']
            result=subprocess.run(args+['--entrypoint','/bin/sh',image,'-eu','-c',script],capture_output=True,text=True)
            server.shutdown();server.server_close();thread.join()
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_erp_template_preserved(self):
        original=Path('/home/ffo/projets/wavy-erp-shell/nginx.conf')
        if not original.exists(): self.skipTest('source Shell absent')
        old=[line for line in original.read_text().splitlines() if 'location ' in line]
        new=[line for line in (P/'shell.conf.template').read_text().splitlines() if 'location ' in line and '8087' not in line]
        self.assertEqual(new,old)
        self.assertFalse((P/'control/open').exists())

if __name__=='__main__': unittest.main()
