#!/usr/bin/env python3
"""Préflight privé READ ONLY. Aucune action de release/activation disponible."""
import argparse
import importlib.util
import json
import os
import stat
from pathlib import Path
import subprocess

P=Path(__file__).resolve().parent
ROOT=P.parents[2]
spec=importlib.util.spec_from_file_location('base',ROOT/'scripts/preprod_config.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)


def validate(envfile, gate_dir=None, release_candidate=False):
    gate_dir = Path(gate_dir or P/'socket').absolute()
    for path, mode in ((P/'control', 0o700), (gate_dir, 0o755)):
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != mode:
            raise ValueError('Permissions du répertoire privé/socket refusées')
    # Le validateur actif garde les contrôles cookies, CORS, images, DB et loopback.
    base.validate(envfile)
    baseline=base.render(envfile)
    cmd, clean=base.compose_args(envfile,[])
    clean['WAVY_PRIVATE_PWA_DIR']=str(P)
    clean['WAVY_PRIVATE_PWA_GATE_DIR']=str(gate_dir)
    overlays=['-f',str(P/'compose.private.yml')]
    if release_candidate: overlays += ['-f',str(P/'compose.release.private.yml')]
    result=subprocess.run(cmd+overlays+['config','--format','json'],env=clean,capture_output=True)
    if result.returncode: raise ValueError('Rendu privé refusé (sortie masquée)')
    candidate=json.loads(result.stdout)
    shell=candidate['services']['wavy-erp-shell-preprod']
    mounts=shell.pop('volumes',[])
    expected={str(P/'shell.conf.template'):'/etc/nginx/templates/default.conf.template',str(P):'/etc/nginx/private-pwa',str(gate_dir):'/run/wavy-private-pwa-gate'}
    if len(mounts)!=3: raise ValueError('Trois montages privés requis')
    for mount in mounts:
        source=mount.get('source')
        if (source not in expected or mount.get('target')!=expected.pop(source)
                or mount.get('type')!='bind' or mount.get('read_only') is not True
                or mount.get('bind',{}).get('create_host_path',False)):
            raise ValueError('Montage privé refusé')
        path=Path(source)
        if not path.exists() or path.is_symlink(): raise ValueError('Source absente ou lien symbolique')
    if release_candidate:
        plan=json.loads((ROOT/'preparation/pwa-notes-frais/release-plan.json').read_text())
        for component, item in plan['images'].items():
            service='wavy-'+component+'-preprod'
            if candidate['services'][service]['image'] != item['reference']:
                raise ValueError('Image privée différente du digest revu')
            candidate['services'][service]['image']=baseline['services'][service]['image']
        fact=candidate['services']['wavy-factures-api-preprod']
        volume=fact.pop('volumes',[])
        if len(volume)!=1 or volume[0].get('type')!='volume' or volume[0].get('source')!='documents-preprod' or volume[0].get('target')!='/app/justificatifs' or volume[0].get('volume')!={'nocopy':True,'subpath':'notes-frais'} or volume[0].get('read_only',False):
            raise ValueError('Montage justificatifs privé refusé')
        values={'WAVY_FACTURES_STOCKAGE_JUSTIFICATIFS':'/app/justificatifs',
                'WAVY_FACTURES_JUSTIFICATIF_MAX_BYTES':'10485760',
                'WAVY_FACTURES_MULTIPART_MAX_FILE_SIZE':'10MB',
                'WAVY_FACTURES_MULTIPART_MAX_REQUEST_SIZE':'11MB'}
        for key,value in values.items():
            if fact['environment'].pop(key,None)!=value: raise ValueError('Limite documentaire refusée')
    if candidate!=baseline: raise ValueError('Modification hors routage privé')
    if (P/'control/open').exists() or (P/'control/open').is_symlink(): raise ValueError('PWA déjà ouverte')
    # Refus même si le validateur actif sait aussi traiter une release HTTPS.
    values=base.dotenv(envfile)
    if (values.get('WAVY_ACCESS_MODE')!='tunnel' or values.get('WAVY_PUBLIC_HTTP_PORT','24443')!='24443'
            or values.get('WAVY_PUBLIC_URL')!='http://localhost:24443'):
        raise ValueError('Origine tunnel localhost:24443 requise')
    print('Routage privé fermé conforme. Préflight seul : aucune installation ni ouverture exécutée.')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-candidate',action='store_true')
    parser.add_argument('--gate-dir',type=Path)
    parser.add_argument('--env-file',required=True,type=Path)
    args=parser.parse_args()
    validate(args.env_file.resolve(),args.gate_dir,args.release_candidate)
