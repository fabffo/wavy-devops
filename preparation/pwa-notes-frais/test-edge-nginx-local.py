#!/usr/bin/env python3
"""Requêtes Nginx sur fixtures locales en conteneurs sans réseau/ports/volumes applicatifs."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

C=Path(__file__).resolve().parent
PROTECTED=['/pwa','/pwa/','/pwa/ngsw-worker.js','/pwa/ngsw.json','/pwa/main.js',
           '/pwa/assets/icon.png','/pwa//ngsw-worker.js','/pwa%2Fngsw-worker.js',
           '/pwa-integration.json','/api/pwa','/api/pwa/session']
INTERNAL=['/__wavy_pwa_gate','/__wavy_notes_write_gate','/__wavy_pwa_closed']
COMMON=['/','/api/auth/session','/api/tiers/health','/modules/factures/',
        '/api/notes-frais','/api/notes-frais/1/justificatif/contenu','/main.js']


class EdgeNginx(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        endpoint=subprocess.check_output(['docker','context','inspect','--format','{{.Endpoints.docker.Host}}'],text=True).strip()
        if os.environ.get('DOCKER_HOST') or os.environ.get('DOCKER_CONTEXT') or not endpoint.startswith('unix://'):
            raise RuntimeError('Daemon local Unix requis')
        cls.image=json.loads((C/'release-plan.json').read_text())['images']['erp-shell']['reference']

    def fixture(self,mode):
        gate='' if mode=='offline' else '''server { listen 24444;
location /check { return %s; }
location /notes-write { return %s; }
}''' % (204 if mode=='open' else 403,403 if mode=='readonly' else 204)
        conf='''events {}\nhttp {
%s
server { listen 24443; location / { return 200 'fixture ERP'; } }
server { listen 8080;
%s
location / { proxy_pass http://127.0.0.1:24443; }
}
}''' % (gate,(C/'edge-pwa-gate.conf').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'nginx.conf';path.write_text(conf)
            cases=[('GET',p) for p in PROTECTED+COMMON+INTERNAL]+[('POST','/api/tiers/fixture'),('POST','/api/notes-frais'),('POST','/api/notes-frais/1')]
            script='nginx -t >/dev/null 2>&1 && nginx\ntrap "nginx -s quit >/dev/null 2>&1" EXIT\n'
            for method,p in cases:
                flags='--post-data=x' if method=='POST' else ''
                script+='wget -S -O /tmp/body '+flags+' '+shlex.quote('http://127.0.0.1:8080'+p)+' 2>/tmp/headers || true\n'
                script+="code=$(awk '/^  HTTP/{code=$2} END{print code}' /tmp/headers)\n"
                script+='printf "%s %s %s\\n" '+shlex.quote(method)+' '+shlex.quote(p)+' "$code"\n'
            args=['docker','run','--rm','--pull','never','--network','none','--read-only',
                  '--tmpfs','/tmp','--tmpfs','/var/cache/nginx','--tmpfs','/var/run',
                  '--mount',f'type=bind,source={path},target=/etc/nginx/nginx.conf,readonly',
                  '--entrypoint','/bin/sh',self.image,'-eu','-c',script]
            result=subprocess.run(args,capture_output=True,text=True,check=True)
        parsed={tuple(line.split()[:2]):line.split()[2] for line in result.stdout.splitlines()}
        for path in INTERNAL:self.assertEqual(parsed[('GET',path)],'404',path)
        return parsed

    def test_closed_edge_blocks_assets_worker_endpoints_but_preserves_common_erp(self):
        result=self.fixture('closed')
        for p in PROTECTED:self.assertEqual(result[('GET',p)],'404',p)
        for p in COMMON:self.assertEqual(result[('GET',p)],'200',p)
        for p in ('/api/tiers/fixture','/api/notes-frais','/api/notes-frais/1'):
            self.assertEqual(result[('POST',p)],'200',p)

    def test_open_lease_allows_fixture_pwa(self):
        result=self.fixture('open')
        for p in PROTECTED+COMMON:self.assertEqual(result[('GET',p)],'200',p)

    def test_gate_service_down_is_fail_closed_without_shell_stop(self):
        result=self.fixture('offline')
        for p in PROTECTED:self.assertEqual(result[('GET',p)],'404',p)
        for p in COMMON:self.assertEqual(result[('GET',p)],'200',p)
        self.assertEqual(result[('POST','/api/tiers/fixture')],'200')
        self.assertNotEqual(result[('POST','/api/notes-frais')],'200')

    def test_rollback_readonly_only_blocks_notes_writes(self):
        result=self.fixture('readonly')
        for p in COMMON:self.assertEqual(result[('GET',p)],'200',p)
        self.assertEqual(result[('POST','/api/tiers/fixture')],'200')
        self.assertEqual(result[('POST','/api/notes-frais')],'403')
        self.assertEqual(result[('POST','/api/notes-frais/1')],'403')


if __name__=='__main__':unittest.main()
