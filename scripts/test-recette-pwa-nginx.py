#!/usr/bin/env python3
"""Nginx réel jetable, réseau none, aucun port ou volume métier ; backend synthétique."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
sys.dont_write_bytecode = True
from release_images import release
ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT/'docker/recette-pwa'
ORIGIN = 'https://recette.wavyservices.fr'


class NginxRoutes(unittest.TestCase):
    def test_routes_visibility_write_policy_and_backend_denials(self):
        _, _, images = release(ROOT, 'recette')
        image = images['erp-shell']
        for visible, writes in ((False,False),(True,False),(True,True)):
            with self.subTest(visible=visible,writes=writes), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp)
                shell = (ASSETS/'shell.conf.template').read_text()
                shell += '''
server { listen 127.0.0.1:8088;
 location /api/ {
  if ($http_cookie = "") { return 401; }
  if ($http_cookie = "forbidden") { return 403; }
  if ($http_cookie = "other-tenant") { return 404; }
  return 200 "authorized-fixture";
 }
}
server { listen 127.0.0.1:8089; location / { return 200 "pwa:$request_uri"; } }
'''
                (folder/'shell.conf').write_text(shell)
                routes = (ASSETS/('routes-open.conf' if visible else 'routes-closed.conf')).read_text()
                routes = routes.replace('http://wavy-pwa-recette;', 'http://127.0.0.1:8089;')
                (folder/'routes.conf').write_text(routes)
                name = 'wavy-recette-pwa-test-'+uuid.uuid4().hex[:10]
                mounts = [(folder/'shell.conf','/etc/nginx/templates/default.conf.template'), (folder/'routes.conf','/etc/nginx/pwa-route.conf'),
                    (ASSETS/('notes-write.conf' if writes else 'notes-read.conf'),'/etc/nginx/wavy-pwa/notes.conf'),
                    (ASSETS/('integration-open.json' if visible else 'integration-closed.json'),'/usr/share/nginx/html/pwa-integration.json')]
                cmd = ['docker','run','-d','--name',name,'--pull','never','--network','none',
                       '-e','WAVY_PWA_PUBLIC_ORIGIN='+ORIGIN,
                       '-e','NGINX_ENVSUBST_FILTER=_UPSTREAM$|^WAVY_PWA_PUBLIC_ORIGIN$']
                for key in ('API','SOCLE_FRONT','TIERS_FRONT','CONTRATS_FRONT','FACTURES_FRONT','TRESORERIE_FRONT'):
                    cmd += ['-e',key+'_UPSTREAM=http://127.0.0.1:8088']
                for source,target in mounts:
                    cmd += ['--mount',f'type=bind,source={source},target={target},readonly']
                cmd += [image]
                try:
                    subprocess.run(cmd,check=True,capture_output=True)
                    def request(method,path,cookie='',origin=''):
                        data = f'{method} {path} HTTP/1.1\r\nHost: recette.wavyservices.fr\r\nConnection: close\r\nContent-Length: 0\r\n'
                        if cookie:data += 'Cookie: '+cookie+'\r\n'
                        if origin:data += 'Origin: '+origin+'\r\n'
                        for attempt in range(30):
                            result = subprocess.run(['docker','exec','-i',name,'nc','-w','1','127.0.0.1','80'],input=data+'\r\n',capture_output=True,text=True)
                            if result.stdout.startswith('HTTP/'):break
                            time.sleep(.1)
                        self.assertTrue(result.stdout.startswith('HTTP/'),result.stderr)
                        return int(result.stdout.splitlines()[0].split()[1]),result.stdout
                    self.assertEqual(request('GET','/pwa')[0],308 if visible else 404)
                    status,body = request('GET','/pwa/notes-frais?x=1')
                    self.assertEqual(status,200 if visible else 404)
                    if visible:self.assertIn('pwa:/notes-frais?x=1',body)
                    status,body = request('GET','/pwa-integration.json')
                    self.assertEqual(status,200); self.assertIn('"enabled": '+str(visible).lower(),body)
                    for path in ('/pwa/connexion','/pwa/ngsw-worker.js','/pwa/manifest.webmanifest'):
                        self.assertEqual(request('GET',path)[0],200 if visible else 404)
                    self.assertEqual(request('GET','/api/notes-frais')[0],401)
                    self.assertEqual(request('GET','/api/notes-frais','forbidden')[0],403)
                    self.assertEqual(request('GET','/api/notes-frais/1/justificatif','other-tenant')[0],404)
                    self.assertEqual(request('GET','/api/notes-frais','valid')[0],200)
                    self.assertEqual(request('POST','/api/notes-frais','valid',ORIGIN)[0],200 if writes else 403)
                    for method in ('POST','PUT','PATCH','DELETE'):
                        self.assertEqual(request(method,'/api/notes-frais/1','valid','https://untrusted.invalid')[0],403)
                        self.assertEqual(request(method,'/api/notes-frais/1','valid')[0],403)
                    self.assertEqual(request('POST','/api/notes-frais;foo','valid',ORIGIN)[0],403)
                    self.assertEqual(request('POST','/api/notes-frais%253bfoo','valid',ORIGIN)[0],403)
                    self.assertEqual(request('GET','/api/pwa/session')[0],404)
                    checked = subprocess.run(['docker','exec',name,'nginx','-t'],capture_output=True)
                    self.assertEqual(checked.returncode,0,checked.stderr)
                finally:
                    subprocess.run(['docker','rm','-f',name],check=True,capture_output=True)


if __name__ == '__main__':unittest.main()
