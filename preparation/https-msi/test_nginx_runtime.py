#!/usr/bin/env python3
"""Test Nginx jetable SANS réseau, port publié, volume existant ou base."""
import importlib.util
import tempfile
import pathlib,subprocess,json,uuid
P=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('candidate',P/'wavy_deploy.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def main():
    with tempfile.TemporaryDirectory(prefix='wavy-https-nginx-') as tmp:
        p=pathlib.Path(tmp)/'candidate';m.render('recettelocal',p,'172.21.0.0/16');text=(p/'shell.conf.template').read_text()
        for upstream in ('API','SOCLE_FRONT','TIERS_FRONT','CONTRATS_FRONT','FACTURES_FRONT','TRESORERIE_FRONT'):text=text.replace('${'+upstream+'_UPSTREAM}','http://127.0.0.1:8088/')
        (p/'nginx-test.conf').write_text(text)
        name='wavy-https-nginx-test-'+uuid.uuid4().hex[:8];ref='ghcr.io/fabffo/wavy-erp-shell@sha256:0182ea7a16a1c0d665e98df0b2bc4e318d96534ea11b4c9de0aee825f9ad8022'
        m.run(['docker','image','inspect',ref])
        # IPv4 loopback only inside a networkless disposable parser/runtime test.
        cmd=['docker','run','-d','--name',name,'--pull','never','--network','none','--entrypoint','nginx','--mount','type=bind,source='+str(p)+'/nginx-test.conf,target=/etc/nginx/conf.d/default.conf,readonly','--mount','type=bind,source='+str(p)+',target=/etc/nginx/wavy-https,readonly',ref,'-g','daemon off;']
        rows=[]
        try:
         subprocess.run(cmd,check=True,capture_output=True)
         cases=[('GET','/pwa/',None,404),('GET','/pwa',None,404),('GET','/api/pwa/',None,404),('POST','/api/auth/session',None,403),('POST','/api/auth/session','https://untrusted.invalid',403),('POST','/api/auth/session','https://recettelocal.wavyservices.fr',502),('POST','/api/notes-frais','https://recettelocal.wavyservices.fr',403),('POST','/api/notes-frais;bad','https://recettelocal.wavyservices.fr',403),('POST','/api/notes-frais%253bextra','https://recettelocal.wavyservices.fr',403)]
         for method in ('POST','PUT','PATCH','DELETE','OPTIONS','TRACE'):
          cases.append((method,'/api/notes-frais/123/justificatif','https://recettelocal.wavyservices.fr',405 if method=='TRACE' else 403))
         for method,path,origin,expected in cases:
          req=f'{method} {path} HTTP/1.1\r\nHost: recettelocal.wavyservices.fr\r\nConnection: close\r\nContent-Length: 0\r\n'+('Origin: '+origin+'\r\n' if origin else '')+'\r\n'
          # BusyBox nc via stdin; never any cookie or real user payload.
          r=subprocess.run(['docker','exec','-i',name,'nc','-w','3','127.0.0.1','80'],input=req.encode(),capture_output=True)
          status=int(r.stdout.splitlines()[0].split()[1]);rows.append({'method':method,'path':path,'expected':expected,'observed':status});assert status==expected,(method,path,status)
        finally:
         subprocess.run(['docker','rm','-f',name],capture_output=True,check=True)
        print(json.dumps({'nginxRealRuntimeCases':len(rows),'passed':len(rows),'failed':0,'network':'none','databaseAccess':False,'containerRemoved':True}))

if __name__=='__main__':main()
