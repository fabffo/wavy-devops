#!/usr/bin/env python3
"""Inventaire, whitespace et scan heuristique local sans afficher de secret.
Ne remplace pas gitleaks/trufflehog, ni une analyse de l'historique Git.
"""
import hashlib
from pathlib import Path
import re
import subprocess

P=Path(__file__).resolve().parent
ROOT=P.parents[2]
patterns={
    'private-key': r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'github-token': r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b',
    'aws-access-key': r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
    'openai-token': r'\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b',
    'credential-url': r'https?://[^\s/:@]+:[^\s/@]+@',
    'literal-credential': r'''(?i)(?:password|passwd|secret|api_key|access_token)\s*[:=]\s*["'][^"'\s]{16,}["']''',
}
files=sorted(p for p in P.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
issues=[]
for path in files:
    raw=path.read_bytes()
    content=raw.decode('utf-8')
    for label,pattern in patterns.items():
        if re.search(pattern,content): issues.append((str(path.relative_to(ROOT)),label))
    for i,line in enumerate(content.splitlines(),1):
        if line.rstrip()!=line: issues.append((str(path.relative_to(ROOT)),f'whitespace:{i}'))
    print(hashlib.sha256(raw).hexdigest(),path.relative_to(ROOT))
# Scanner aussi les lignes ajoutées aux deux inventaires/docs suivis, sans
# retraiter les exemples historiques ni imprimer les valeurs détectées.
for tracked in ('preparation/pwa-notes-frais/README.md','preparation/pwa-notes-frais/FILES.txt'):
    diff=subprocess.check_output(['git','diff','HEAD','--',tracked],cwd=ROOT,text=True)
    added='\n'.join(line[1:] for line in diff.splitlines() if line.startswith('+') and not line.startswith('+++'))
    for label,pattern in patterns.items():
        if re.search(pattern,added): issues.append((tracked,label))
print(f'Scan heuristique : {len(files)} fichiers texte, {len(issues)} détection(s).')
for path,label in issues: print(path,label)
subprocess.run(['git','diff','--check'],cwd=ROOT,check=True)
subprocess.run(['git','diff','--cached','--check'],cwd=ROOT,check=True)
protected=['docker-compose.preprod.yml','docker-compose.recette.yml','versions',
           'preparation/pwa-notes-frais/scripts','preparation/pwa-notes-frais/compose.override.yml',
           'preparation/pwa-notes-frais/compose.activation.yml']
for args in (['git','diff','--exit-code','HEAD','--',*protected],):
    subprocess.run(args,cwd=ROOT,check=True)
if issues: raise SystemExit(1)
