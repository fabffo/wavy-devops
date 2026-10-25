#!/usr/bin/env python3
"""Restauration d'exercice seulement, copies jetables sans réseau/port ; jamais PREPROD."""
import argparse
import ctypes
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import secrets
import shutil
import signal
import socket
import stat
import subprocess
import tarfile
import tempfile
import time

P=Path(__file__).resolve().parent
ROOT=P.parents[2]
DATABASES=('socle','tiers','contrats','factures','tresorerie')
_DEADLINE=None


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

op=load(ROOT/'scripts/preprod_operation.py','isolated_operation')
base=load(ROOT/'scripts/preprod_config.py','isolated_base')
archive=load(P.parent/'scripts/preprod_document_archive.py','isolated_archive')
manifest=load(ROOT/'scripts/preprod_backup_manifest.py','isolated_manifest')
validator=load(P/'isolated-validator.py','isolated_schema_validator')


def command(args, **kwargs):
    remaining=90 if _DEADLINE is None else _DEADLINE-time.monotonic()
    if remaining<=0:raise TimeoutError('Budget restauration épuisé')
    result=subprocess.run(args,capture_output=True,timeout=min(900,remaining),**kwargs)
    if result.returncode:raise ValueError('Exercice isolé refusé')
    return result.stdout


def validate_rendered(data,project,secret_dir=None):
    if set(data['services'])!=set(DATABASES)|{'documents'}:raise ValueError('Services isolés incorrects')
    for service in data['services'].values():
        if (service.get('network_mode')!='none' or service.get('ports') or service.get('container_name')
                or not service.get('read_only') or service.get('privileged')):raise ValueError('Isolation refusée')
        if service.get('devices') or service.get('volumes_from') or service.get('cap_add') or service.get('build'):
            raise ValueError('Option d’isolation refusée')
        if service.get('image')!='postgres:16-alpine@sha256:93d55776e04376e19adb2733e3ccebb4392ee7dd86d8ff238503b30fe719c84f':
            raise ValueError('Image d’exercice non épinglée')
        for mount in service.get('volumes',[]):
            if mount['type']=='volume' and mount['source'] not in data['volumes']:raise ValueError('Volume externe')
            if mount['type']=='bind' and (not mount.get('read_only') or
                    (secret_dir is not None and Path(mount['source']).parent!=secret_dir)):
                raise ValueError('Bind isolé refusé')
    for volume in data['volumes'].values():
        if volume.get('external') or volume.get('driver_opts') or volume.get('driver','local')!='local' or not volume['name'].startswith(project+'_') or 'preprod' in volume['name']:
            raise ValueError('Volume non isolé')


def document_hashes(filename):
    archive.validate(str(filename))
    hashes={};roots={}
    with tarfile.open(filename) as source:
        for entry in source:
            name=entry.name.rstrip('/')
            if entry.isdir() and name in ('contrats','notes-frais'):roots[name]=entry
            if entry.isfile():hashes[name]=hashlib.file_digest(source.extractfile(entry),'sha256').hexdigest()
    if set(roots)!= {'contrats','notes-frais'}:raise ValueError('Deux racines obligatoires')
    note=roots['notes-frais']
    if (note.uid,note.gid,note.mode)!=(100,101,0o700):raise ValueError('Notes permissions refusées')
    return hashes


def runtime_guard(envfile,fd):
    # Operation peut rouvrir un FD absent : exiger l'héritage réel AVANT son entrée.
    locked=os.fstat(fd)
    canonical=os.stat(ROOT/'deployments/preprod.lock',follow_symlinks=False)
    if not stat.S_ISREG(canonical.st_mode) or not os.path.samestat(locked,canonical):
        raise ValueError('FD global hérité requis')
    if (Path(envfile)!=ROOT/'.env.preprod' or Path(envfile).is_symlink()
            or socket.gethostname().split('.')[0]!='wavy-preprod'
            or os.environ.get('DOCKER_HOST') or os.environ.get('DOCKER_CONTEXT')):
        raise ValueError('Hôte/configuration locale canonique requis')
    endpoint=command(['docker','context','inspect','--format','{{.Endpoints.docker.Host}}']).strip()
    if endpoint!=b'unix:///var/run/docker.sock':raise ValueError('Daemon local système requis')


@contextmanager
def recovery_staging(directory):
    # Pas de finaliseur TemporaryDirectory : le staging survit aux échecs de down.
    tmp=Path(tempfile.mkdtemp(prefix='restore-private-',dir=directory))
    recovery={'required':False}
    try:yield tmp,recovery
    finally:
        if not recovery['required']:
            shutil.rmtree(tmp)
            attempt_path=Path(directory)/'restore-attempt.json'
            if attempt_path.exists():
                attempt=op.read_private(attempt_path)
                if attempt.get('phase')=='docker-cleaned' and attempt.get('envFile')==str(tmp/'restore.env'):
                    attempt['phase']='cleaned';op.atomic_json(attempt_path,attempt)


def recover_previous(directory,run,backup):
    """Only called INSIDE the inherited owner lock after run/plan/phase checks."""
    path=directory/'restore-attempt.json'
    if not path.exists():return
    attempt=op.read_private(path)
    if attempt.get('phase')=='cleaned':return
    project=attempt.get('project','')
    if (attempt.get('run')!=run or attempt.get('backup')!=backup
            or not re.fullmatch('wavy-pwa-restore-'+re.escape(run)+r'-[a-f0-9]{8}',project)):
        raise ValueError('Reprise isolée hors propriétaire/lot')
    config=Path(attempt.get('envFile',''))
    if (config.name!='restore.env' or config.parent.parent!=directory
            or not config.parent.name.startswith('restore-private-')
            or config.is_symlink() or config.parent.is_symlink()):
        raise ValueError('Chemin de reprise isolée refusé')
    if attempt.get('phase')=='docker-cleaned':
        if config.parent.exists():
            info=config.parent.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:
                raise ValueError('Staging reprise non sûr')
            shutil.rmtree(config.parent)
        attempt['phase']='cleaned';op.atomic_json(path,attempt);return
    for target,mode in ((config,0o600),(config.parent,0o700)):
        info=target.lstat()
        if (info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=mode
                or (target==config and not stat.S_ISREG(info.st_mode))
                or (target==config.parent and not stat.S_ISDIR(info.st_mode))):
            raise ValueError('Permissions de reprise isolée refusées')
    cmd=['docker','compose','--env-file',str(config),'-p',project,'-f',str(P/'restore-isolated.compose.yml')]
    clean={k:v for k,v in os.environ.items() if not k.startswith(('RESTORE_','COMPOSE_'))}
    rendered=json.loads(command(cmd+['config','--format','json'],env=clean))
    validate_rendered(rendered,project,config.parent)
    report_path=directory/'schema-validation.json'
    report=op.read_private(report_path) if report_path.exists() else None
    names=[] if report is None else report.get('containers',[])
    # A fully cleaned report from an earlier attempt is historical evidence,
    # not a registry of children belonging to the current failed attempt.
    if report is not None and report.get('project')!=project and report.get('cleanup') is True and report.get('containers',[])==[]:
        report=None;names=[]
    if report is not None and (report.get('run')!=run or report.get('backup')!=backup or report.get('project')!=project):
        raise ValueError('Rapport reprise hors propriétaire')
    attempt['phase']='recovering';op.atomic_json(path,attempt)
    for name in names:
        if not re.fullmatch(r'wavy-validator-(extract-)?[a-f0-9]{24}',name):
            raise ValueError('Nom validateur de reprise refusé')
        exists=command(['docker','ps','-aq','--filter','name=^/'+name+'$']).strip()
        if not exists:continue
        container=json.loads(command(['docker','inspect',name]))[0]
        if (container['Config'].get('Labels',{}).get('wavy.validator.project')!=project
                or container['Config']['Image'] not in {pair[0] for pair in validator.IMAGES.values()}
                or not container['HostConfig'].get('ReadonlyRootfs')
                or container['Name']!='/'+name):
            raise ValueError('Validateur de reprise étranger')
        command(['docker','rm','-f',name])
    command(cmd+['down','--volumes'],env=clean)
    if report is not None:
        report.update(status='failed-recovered',cleanup=True,containers=[])
        op.atomic_json(report_path,report)
    attempt['phase']='docker-cleaned';op.atomic_json(path,attempt)
    shutil.rmtree(config.parent)
    attempt['phase']='cleaned';op.atomic_json(path,attempt)


def restore(envfile,folder):
    global _DEADLINE
    _DEADLINE=time.monotonic()+840
    directory=ROOT/'deployments/pwa-release'
    run=os.environ['PWA_RELEASE_RUN'];fd=int(os.environ['PWA_RELEASE_LOCK_FD'])
    runtime_guard(envfile,fd)
    with op.Operation(ROOT,owner=run,inherited=fd):
        state=op.read_private(directory/'state.json')
        reserved=op.read_private(ROOT/'deployments/preprod-reservation.json')
        plan=op.read_private(directory/'runtime-plan.json')
        digest=hashlib.sha256(json.dumps(plan,sort_keys=True).encode()).hexdigest()
        if (state.get('profile')!='private-tunnel-v1' or plan.get('privateProfile')!='private-tunnel-v1'
                or state['phase']!='awaiting-restore' or state.get('pending')!='isolated-restore'
                or state['run']!=reserved['run'] or state['run']!=run
                or state['planHash']!=reserved['planHash'] or state['planHash']!=digest):
            raise ValueError('Exercice hors état propriétaire')
        folder=Path(folder)
        if folder.resolve()!=folder or folder.parent!=ROOT/'backups/preprod':raise ValueError('Lot hors racine')
        backup={'directory':str(folder.relative_to(ROOT)),
                'manifestSha256':hashlib.sha256((folder/'manifest.json').read_bytes()).hexdigest()}
        if state['backup']!=backup:raise ValueError('Lot différent de la réservation')
        private_config=load(P/'validate-private.py','restore_private_config')
        private_config.validate(envfile,Path(os.environ['WAVY_PRIVATE_PWA_GATE_DIR']),True)
        validator.configuration_guard(base.render(envfile)['services']['wavy-factures-api-preprod']['environment'])
        recover_previous(directory,run,backup)
        # Stale proof can never authorize a new failed attempt.
        (directory/'restore-proof.json').unlink(missing_ok=True)
        env=base.dotenv(envfile)
        # Copies privées, aucun accès aux credentials de base actifs dans les services d'exercice.
        with recovery_staging(directory) as (tmp,recovery):
            password=env['WAVY_BACKUP_ENCRYPTION_PASSPHRASE']
            old=os.environ.get('WAVY_BACKUP_PASSPHRASE')
            os.environ['WAVY_BACKUP_PASSPHRASE']=password
            try:manifest.run('verify',folder)
            finally:
                if old is None:os.environ.pop('WAVY_BACKUP_PASSPHRASE',None)
                else:os.environ['WAVY_BACKUP_PASSPHRASE']=old
            passfile=tmp/'backup.passphrase';passfile.write_text(password+'\n');passfile.chmod(0o600)
            for name in [db+'.dump' for db in DATABASES]+['documents.tar']:
                destination=tmp/name
                command(['openssl','enc','-d','-aes-256-cbc','-pbkdf2','-pass','file:'+str(passfile),
                         '-in',str(folder/(name+'.enc')),'-out',str(destination)])
                destination.chmod(0o600)
            hashes=document_hashes(tmp/'documents.tar')
            values={'RESTORE_SECRET_DIR':str(tmp)}
            for db in DATABASES:
                values['RESTORE_'+db.upper()+'_DB']=db
                values['RESTORE_'+db.upper()+'_USER']='restore_operator'
                path=tmp/(db+'.password');path.write_text(secrets.token_hex(32))
                # Le parent hôte est 0700 ; le fichier bind est lisible au postgres du conteneur.
                path.chmod(0o644)
            config=tmp/'restore.env';config.write_text('\n'.join(k+'='+v for k,v in values.items()));config.chmod(0o600)
            project='wavy-pwa-restore-'+run+'-'+secrets.token_hex(4)
            cmd=['docker','compose','--env-file',str(config),'-p',project,'-f',str(P/'restore-isolated.compose.yml')]
            clean={k:v for k,v in os.environ.items() if not k.startswith(('RESTORE_','COMPOSE_'))}
            data=json.loads(command(cmd+['config','--format','json'],env=clean))
            validate_rendered(data,project,tmp)
            op.atomic_json(directory/'restore-attempt.json',{'run':run,'project':project,'backup':backup,'phase':'creating','envFile':str(config)})
            recovery['required']=True
            try:
                command(cmd+['up','-d','--no-build','--pull','never'],env=clean)
                for db in DATABASES:
                    ready=False
                    for attempt in range(60):
                        if time.monotonic()>=_DEADLINE-30:raise TimeoutError('Budget readiness épuisé')
                        result=subprocess.run(cmd+['exec','-T',db,'pg_isready','-U','restore_operator','-d',db],env=clean,capture_output=True,timeout=10)
                        if result.returncode==0:ready=True;break
                        time.sleep(1)
                    if not ready:raise ValueError('Postgres isolé indisponible')
                    with (tmp/(db+'.dump')).open('rb') as stream:
                        command(cmd+['exec','-T',db,'pg_restore','--list'],env=clean,stdin=stream)
                    with (tmp/(db+'.dump')).open('rb') as stream:
                        command(cmd+['exec','-T',db,'pg_restore','-U','restore_operator','-d',db,
                                     '--no-owner','--no-acl','--single-transaction','--exit-on-error'],env=clean,stdin=stream)
                    # Une restauration vide/tronquée ne constitue pas une preuve DB.
                    query="SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
                    count=command(cmd+['exec','-T',db,'psql','-U','restore_operator','-d',db,'-At','-c',query],env=clean)
                    if int(count)<1:raise ValueError('Aucune table restaurée')
                with (tmp/'documents.tar').open('rb') as stream:
                    command(cmd+['exec','-T','documents','tar','-xpf','-','-C','/documents'],env=clean,stdin=stream)
                mode=command(cmd+['exec','-T','documents','stat','-c','%u:%g:%a','/documents/notes-frais'],env=clean).strip()
                if mode!=b'100:101:700':raise ValueError('Permissions copiées incorrectes')
                # Re-archiver la copie et comparer chaque original, sans l'exposer hors espace privé.
                copy=tmp/'copy.tar'
                copy.write_bytes(command(cmd+['exec','-T','documents','tar','-cpf','-','-C','/documents','contrats','notes-frais'],env=clean))
                if document_hashes(copy)!=hashes:raise ValueError('Copies documentaires différentes')
                validation=validator.validate_copies(cmd,project,tmp,directory/'schema-validation.json',
                    {'run':run,'planHash':state['planHash'],'backup':backup},
                    timeout_seconds=min(240,_DEADLINE-time.monotonic()-30))
                proof={'profile':'private-tunnel-v1','run':run,'planHash':state['planHash'],
                       'origin':'http://localhost:24443','checkedAt':time.strftime('%Y-%m-%dT%H:%M:%S+00:00',time.gmtime()),
                       'reviewer':'isolated-restore-runner','backup':backup,'project':project,
                       'schemaValidation':{'reportSha256':validator.digest(directory/'schema-validation.json'),
                                           'images':validation['images'],'cleanup':validation['cleanup']},
                       'documentSetHash':hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest(),
                       'checks':{k:True for k in ('five-databases','contracts-and-notes','hmac','catalogues',
                                                 'document-hashes','notes-permissions',*validator.CHECKS)}}
            finally:
                _DEADLINE=time.monotonic()+30
                # Jamais prune : seul le projet unique dont la config a été contrôlée.
                validation_path=directory/'schema-validation.json'
                if validation_path.exists():
                    current=op.read_private(validation_path)
                    if current.get('run')==run and current.get('cleanup') is not True:
                        raise ValueError('Validateur encore présent ; reprise isolée requise avant down')
                command(cmd+['down','--volumes'],env=clean)
                op.atomic_json(directory/'restore-attempt.json',{'run':run,'project':project,'backup':backup,'phase':'docker-cleaned','envFile':str(config)})
                recovery['required']=False
        # Publier uniquement APRÈS down ET suppression du staging, même après erreur.
        op.atomic_json(directory/'restore-proof.json',proof)
        op.atomic_json(directory/'restore-attempt.json',{'run':run,'project':project,'backup':backup,'phase':'cleaned'})

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-on-approved-host',action='store_true')
    parser.add_argument('--env',required=True,type=Path);parser.add_argument('--backup',required=True,type=Path)
    args=parser.parse_args()
    if not args.execute_on_approved_host:parser.exit(2,'Runner inactif sans autorisation explicite.\n')
    def interrupted(signum,frame):raise InterruptedError('Restauration interrompue')
    signal.signal(signal.SIGTERM,interrupted)
    parent=os.getppid()
    if ctypes.CDLL(None,use_errno=True).prctl(1,signal.SIGTERM,0,0,0)!=0 or os.getppid()!=parent:
        parser.exit(2,'Surveillance du parent indisponible.\n')
    try:restore(args.env,args.backup)
    except BaseException:raise SystemExit('Restauration isolée refusée ; voir état privé, aucune preuve publiée.')
