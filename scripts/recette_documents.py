#!/usr/bin/env python3
"""Validation du lot RECETTE existant DB + justificatifs ; aucun accès Docker/VM."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile

DATABASES = ('socle','tiers','contrats','factures','tresorerie')
FILES = {db+'.dump' for db in DATABASES} | {'justificatifs.tar'}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def private(path, directory=False):
    path = Path(path)
    mode = 0o700 if directory else 0o600
    if path.is_symlink() or not (path.is_dir() if directory else path.is_file()) or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o777 != mode:
        raise ValueError('Lot RECETTE absent, symbolique ou non privé')


def validate_document_path(name, directory, size=0):
    path=PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or str(path)!=name:
        raise ValueError('Chemin justificatif interdit')
    if directory:
        if name!='.' and (len(path.parts)>3 or not all(re.fullmatch(r'[1-9][0-9]*',p) for p in path.parts)):
            raise ValueError('Hiérarchie tenant/société/note invalide')
    elif len(path.parts)!=4 or not all(re.fullmatch(r'[1-9][0-9]*',p) for p in path.parts[:3]) or not re.fullmatch(r'[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}',path.name) or not 0 < size <= 50*1024*1024:
        raise ValueError('Identifiant ou taille du justificatif invalide')


def validate_archive(filename, uid, gid):
    seen = set(); hashes = {}
    with tarfile.open(filename,'r:') as archive:
        for entry in archive:
            name = entry.name
            while name.startswith('./'): name = name[2:]
            name = name.rstrip('/') or '.'
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or name in seen or str(path)!=name:
                raise ValueError('Chemin justificatif interdit ou dupliqué')
            if not (entry.isdir() or entry.isfile()) or entry.uid != uid or entry.gid != gid or entry.mode != (0o700 if entry.isdir() else 0o600):
                raise ValueError('Type, propriétaire ou permissions du justificatif refusés')
            validate_document_path(name,entry.isdir(),entry.size)
            if entry.isfile():
                hashes[name] = hashlib.file_digest(archive.extractfile(entry),'sha256').hexdigest()
            seen.add(name)
    if '.' not in seen:
        raise ValueError('Racine privée absente')
    for name in seen - {'.'}:
        if str(PurePosixPath(name).parent) not in seen:
            raise ValueError('Dossier parent manquant')
    return hashes


def seal(folder, volume, uid, gid):
    folder = Path(folder); private(folder,True)
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*', volume) or uid == 0 or gid < 0:
        raise ValueError('Provenance documentaire invalide')
    for name in FILES: private(folder/name)
    validate_archive(folder/'justificatifs.tar',uid,gid)
    meta = {'environment':'recette','format':1,'storageVolume':volume,'uid':uid,'gid':gid,
            'files':{name:sha(folder/name) for name in sorted(FILES)}}
    path = folder/'recette-pwa.json'
    with path.open('x') as stream: json.dump(meta,stream,indent=2); stream.write('\n')
    path.chmod(0o600)
    return sha(path)


def verify(folder):
    folder = Path(folder); private(folder,True); private(folder/'recette-pwa.json')
    if folder.name.startswith('.incomplete-'):
        raise ValueError('Lot incomplet : reprise des services ou finalisation non confirmée')
    meta = json.loads((folder/'recette-pwa.json').read_text())
    if meta.get('environment')!='recette' or meta.get('format')!=1 or set(meta.get('files',{}))!=FILES or not isinstance(meta.get('uid'),int) or meta['uid']<=0 or not isinstance(meta.get('gid'),int) or meta['gid']<0:
        raise ValueError('Provenance ou composition du lot incorrecte')
    for name,digest in meta['files'].items():
        private(folder/name)
        if not re.fullmatch(r'[0-9a-f]{64}',digest) or sha(folder/name)!=digest:
            raise ValueError('Intégrité du lot RECETTE refusée')
    hashes = validate_archive(folder/'justificatifs.tar',meta['uid'],meta['gid'])
    return {'verified':True,'environment':'recette','manifestSha256':sha(folder/'recette-pwa.json'),
            'documentCount':len(hashes),'restorationVerified':False}


if __name__ == '__main__':
    try:
        if sys.argv[1]=='seal' and len(sys.argv)==6:
            print(seal(sys.argv[2],sys.argv[3],int(sys.argv[4]),int(sys.argv[5])))
        elif sys.argv[1]=='verify' and len(sys.argv)==3:
            print(json.dumps(verify(sys.argv[2])))
        else: raise ValueError('Usage : recette_documents.py verify <lot> | seal <lot> <volume> <uid> <gid>')
    except (ValueError,OSError,KeyError,tarfile.TarError) as error:
        print('Sauvegarde RECETTE refusée : '+str(error),file=sys.stderr);sys.exit(1)
