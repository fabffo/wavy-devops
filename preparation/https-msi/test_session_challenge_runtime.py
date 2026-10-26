#!/usr/bin/env python3
"""Nginx response contract against a synthetic 401 backend; no network/DB/ports."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('candidate',HERE/'wavy_deploy.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
HOST='recettelocal.wavyservices.fr';ORIGIN='https://'+HOST

def main():
 with tempfile.TemporaryDirectory(prefix='wavy-session-challenge-') as root:
  out=Path(root)/'candidate';m.render('recettelocal',out,'172.21.0.0/16')
  text=(out/'shell.conf.template').read_text()
  text=m.lazy_module_routes(text,{c.upper()+'_FRONT_UPSTREAM':'http://wavy-'+c+'-front-recette' for c in m.MODULES if c!='pwa'})
  # Four upstreams deliberately remain unresolvable: Nginx must still start.
  text=text.replace('set $wavy_module_socle http://wavy-socle-front-recette;', 'set $wavy_module_socle http://127.0.0.1:8088;')
  for upstream in ('API','SOCLE_FRONT','TIERS_FRONT','CONTRATS_FRONT','FACTURES_FRONT','TRESORERIE_FRONT'):
   text=text.replace('${'+upstream+'_UPSTREAM}','http://127.0.0.1:8088')
  text+='''
server { listen 127.0.0.1:8088;
 location /asset.js { return 200 "$request_uri"; }
 location / {
  if ($request_method = OPTIONS) {
   add_header Access-Control-Allow-Origin "https://recettelocal.wavyservices.fr" always;
   add_header Access-Control-Allow-Credentials true always;
   return 200;
  }
  add_header WWW-Authenticate 'Basic realm="synthetic-test"' always;
  return 401;
 }
}
'''
  (out/'nginx-test.conf').write_text(text)
  name='wavy-session-challenge-'+uuid.uuid4().hex[:8];reference=m.plan('recettelocal')['images']['erp-shell']
  rows=[]
  try:
   m.run(['docker','run','-d','--name',name,'--pull','never','--network','none','--entrypoint','nginx',
    '--mount','type=bind,source='+str(out/'nginx-test.conf')+',target=/etc/nginx/conf.d/default.conf,readonly',
    '--mount','type=bind,source='+str(out)+',target=/etc/nginx/wavy-https,readonly',reference,'-g','daemon off;'])
   cases=[('GET','/modules/socle/asset.js?v=42',None,200,False),('GET','/api/auth/session',None,401,False),('POST','/api/auth/session',ORIGIN,401,False),
    ('POST','/api/auth/session',None,403,False),('POST','/api/auth/session','https://untrusted.invalid',403,False),
    ('GET','/api/profil',None,401,True),('GET','/api/auth/session/societe',None,401,True),
    ('OPTIONS','/api/auth/session',ORIGIN,200,False)]
   for method,path,origin,expected,challenge in cases:
    request=f'{method} {path} HTTP/1.1\r\nHost: {HOST}\r\nConnection: close\r\nContent-Length: 0\r\n'+('Origin: '+origin+'\r\n' if origin else '')+'\r\n'
    # Wait only for the disposable parser process to listen, never a Wavy service.
    for attempt in range(20):
     result=subprocess.run(['docker','exec','-i',name,'nc','-w','2','127.0.0.1','80'],input=request.encode(),capture_output=True)
     if result.stdout.startswith(b'HTTP/'):break
     time.sleep(.1)
    status=int(result.stdout.splitlines()[0].split()[1]);headers=result.stdout.lower()
    observed=b'www-authenticate: basic' in headers
    passed=status==expected and observed==challenge
    if path.startswith('/modules/'):passed=passed and b'/asset.js?v=42' in result.stdout
    if method=='OPTIONS':passed=passed and ('access-control-allow-origin: '+ORIGIN).encode() in headers and b'access-control-allow-credentials: true' in headers
    rows.append({'method':method,'path':path,'status':status,'basicChallenge':observed,'passed':passed})
    if not passed:raise AssertionError(rows[-1])
  finally:
   subprocess.run(['docker','rm','-f',name],capture_output=True,check=True)
  print(json.dumps({'scope':'SYNTHETIC_BACKEND_NGINX_CONTRACT_NOT_REAL_AUTHENTICATION','passed':len(rows),'failed':0,'cases':rows,'network':'none','databaseAccess':False,'containerRemoved':True},indent=2))

if __name__=='__main__':main()
