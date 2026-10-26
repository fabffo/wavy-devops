#!/usr/bin/env python3
"""Utilise uniquement POST/adapt (parseur) ; jamais load/config en écriture/reload."""
import hashlib
import json
from pathlib import Path
import subprocess

P=Path(__file__).resolve().parent

def read(args, data=None):
    result=subprocess.run(['curl.exe','--silent','--show-error','--fail-with-body',
                           '--max-time','10',*args],input=data,capture_output=True,timeout=15)
    if result.returncode:raise ValueError('Adaptation Caddy refusée ; aucun changement actif')
    return result.stdout

def main():
    before=read(['http://127.0.0.1:2019/config/'])
    results=[]
    for name in ('Caddyfile.candidate','Caddyfile.local-only.candidate'):
        candidate=(P/name).read_bytes()
        adapted=json.loads(read(['--header','Content-Type: text/caddyfile','--data-binary','@-',
                                 'http://127.0.0.1:2019/adapt'],candidate))
        if 'error' in adapted:raise ValueError('Caddyfile refusé')
        results.append({'candidate':name,'adapted':True,'candidateSha256':hashlib.sha256(candidate).hexdigest(),
                        'warnings':len(adapted.get('warnings',[]))})
    after=read(['http://127.0.0.1:2019/config/'])
    if before!=after:raise ValueError('Configuration active modifiée pendant la vérification')
    print(json.dumps({'results':results,'activeConfigUnchanged':True,'activated':False},indent=2))

if __name__=='__main__':main()
