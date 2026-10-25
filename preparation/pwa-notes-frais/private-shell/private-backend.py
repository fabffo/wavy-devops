#!/usr/bin/env python3
"""Backend privé : aucune action à l'import ; toutes mutations sous Operation."""
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import stat
import subprocess
import sys
import time

P=Path(__file__).resolve().parent
ROOT=P.parents[2]

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

shared=load(P.parent/'scripts/release_pwa_preprod.py','private_backend_shared')
config=load(P/'validate-private.py','private_backend_config')
gate=load(P/'session-gate.py','private_backend_gate')


class Backend(shared.DockerBackend):
    def __init__(self, env, directory, gate_dir, cookie_file=None, seconds=900):
        super().__init__(env,directory)
        self.root=ROOT;self.gate_dir=Path(gate_dir);self.cookie_file=cookie_file
        if type(seconds) is not int or not 1<=seconds<=900: raise ValueError('Durée 1..900 requise')
        self.seconds=seconds;self.child=None;self.cookie=None;self.stop_requested=False

    def host_guard(self):
        if self.env_path!=ROOT/'.env.preprod': raise ValueError('Dotenv machine canonique requis')
        if self.command(['hostname','-s']).strip()!=b'wavy-preprod': raise ValueError('Hôte interdit')
        if os.environ.get('DOCKER_HOST') or os.environ.get('DOCKER_CONTEXT'): raise ValueError('Override interdit')
        endpoint=self.command(['docker','context','inspect','--format','{{.Endpoints.docker.Host}}']).strip()
        if endpoint!=b'unix:///var/run/docker.sock': raise ValueError('Daemon local système requis')
        self.command(['docker','version'])

    def identity(self):
        source={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in P.iterdir()
                if p.is_file() and p.suffix in ('.py','.sh','.yml','.conf','.template','.json','.java')}
        return shared.fingerprint({'shared':super().identity(),'private':source,
                                   'gate':str(self.gate_dir)})

    def helper(self,action,*args):
        # V3 provision/stockage/wait inchangés ; aucun de ces chemins ne valide HTTPS.
        if action in ('provision-storage','storage','wait'):
            return super().helper(action,*args)
        env=dict(os.environ,PWA_RELEASE_ENV=str(self.env_path),
                 PWA_RELEASE_PLAN=str(self.directory/'runtime-plan.json'),
                 PWA_RELEASE_RUN=self.run_id,PWA_RELEASE_LOCK_FD=str(self.lock_fd),
                 WAVY_PREPROD_LOCK_FD=str(self.lock_fd),WAVY_PRIVATE_PWA_GATE_DIR=str(self.gate_dir),
                 PYTHONDONTWRITEBYTECODE='1')
        return self.command(['bash',str(P/'private-runtime.sh'),action,*args],env)

    def preflight(self,plan):
        self.select(plan)
        config.validate(self.env_path,self.gate_dir,True)
        self.helper('guard')

    def snapshot(self,plan):
        shell=self.container('erp-shell')
        bindings=shell.get('HostConfig',{}).get('PortBindings',{})
        if bindings!={'80/tcp':[{'HostIp':'127.0.0.1','HostPort':'24443'}]}:
            raise ValueError('Publication Shell actuelle différente du tunnel')
        allowed={'/etc/nginx/templates/default.conf.template':str(P/'shell.conf.template'),
                 '/etc/nginx/private-pwa':str(P),
                 '/run/wavy-private-pwa-gate':str(self.gate_dir)}
        for mount in shell.get('Mounts',[]):
            if mount.get('Type')!='bind' or mount.get('RW') or allowed.get(mount.get('Destination'))!=mount.get('Source'):
                raise ValueError('Montage Shell actuel hors variante revue')
        baseline=config.base.render(self.env_path)
        expected=baseline['services']['wavy-erp-shell-preprod']['environment']
        actual=dict(item.split('=',1) for item in shell['Config'].get('Env',[]) if '=' in item)
        if any(actual.get(key)!=value for key,value in expected.items()):
            raise ValueError('Environnement Shell actuel non reproductible')
        previous=super().snapshot(plan)
        previous['privateSnapshot']={'shellEnvironmentHash':shared.fingerprint(expected),
                                     'shellMountsHash':shared.fingerprint(shell.get('Mounts',[]))}
        return previous

    def compose(self,plan,release=True):
        cmd,env=config.base.compose_args(self.env_path,[])
        env['WAVY_PRIVATE_PWA_DIR']=str(P)
        env['WAVY_PRIVATE_PWA_GATE_DIR']=str(self.gate_dir)
        cmd+=['-f',str(P/'compose.private.yml')]
        if release:
            # Le snapshot peut contenir d'anciens digests. Overlay éphémère privé,
            # issu du plan validé, sans interpolation de shell ni image flottante.
            overlay={'services':{f'wavy-{c}-preprod':{'image':i['reference']}
                                 for c,i in plan['images'].items()}}
            path=self.directory/'images.override.json'
            shared.write_json(path,overlay)
            cmd+=['-f',str(P/'compose.release.private.yml'),'-f',str(path)]
        return cmd,env

    def barrier(self,previous):
        # Même image Shell que le snapshot, sans toucher aux 3 autres services.
        overlay=self.directory/'barrier.override.json'
        shared.write_json(overlay,{'services':{'wavy-erp-shell-preprod':{'image':previous['images']['erp-shell']['reference']}}})
        cmd,env=self.compose(previous,False)
        self.command(cmd+['-f',str(overlay),'up','-d','--no-deps','--no-build','--pull','never',
                          '--force-recreate','wavy-erp-shell-preprod'],env)
        self.healthy('erp-shell');self.observed('erp-shell',previous)
        self.checks()

    def deploy(self,component,plan,mode):
        if mode not in ('closed','rollback'): raise ValueError('Mode privé fermé requis')
        self.close_socket()
        shared.config.bundle.validate(plan)
        config.validate(self.env_path,self.gate_dir,True)
        cmd,env=self.compose(plan)
        self.command(cmd+['up','-d','--no-deps','--no-build','--pull','never','--force-recreate',
                          'wavy-'+component+'-preprod'],env)

    def close_socket(self,missing_ok=False):
        try:info=self.gate_dir.lstat()
        except FileNotFoundError:
            if not missing_ok:raise
            info=None
        if info is not None:
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid()
                    or stat.S_IMODE(info.st_mode)!=0o755): raise ValueError('Répertoire gate non sûr')
            path=self.gate_dir/'gate.sock'
            try:
                info=path.lstat()
                if not stat.S_ISSOCK(info.st_mode) or info.st_uid!=os.getuid():
                    raise ValueError('Socket substitué')
                path.unlink();shared.operation.sync_directory(self.gate_dir)
            except FileNotFoundError: pass
        if self.child is not None:
            self.child.terminate()
            try:self.child.wait(timeout=3)
            except subprocess.TimeoutExpired:self.child.kill();self.child.wait(timeout=3)
            self.child=None

    def close(self,readonly=True):
        # Fermeture indépendante de Docker : aucun stop/kill de PWA/Shell.
        shared.write_json(self.directory/'edge.json',{'run':self.run_id,'mode':'closed',
                          'closureBlocked':True,'notesReadonly':True})
        self.close_socket()
        self.route('closed')
        shared.write_json(self.directory/'edge.json',{'run':self.run_id,'mode':'closed',
                          'closureBlocked':False,'notesReadonly':True})

    def route(self,mode):
        if mode!='closed':raise ValueError('Probe fermé uniquement')
        self.helper('closed')

    def checks(self):self.helper('checks')

    def backup(self,baseline=False):
        before=set((ROOT/'backups/preprod').glob('????????T??????Z-*'))
        self.helper('backup-baseline' if baseline else 'backup')
        created=set((ROOT/'backups/preprod').glob('????????T??????Z-*'))-before
        if len(created)!=1:raise ValueError('Sauvegarde non identifiable')
        folder=created.pop()
        result={'directory':str(folder.relative_to(ROOT)),
                'manifestSha256':hashlib.sha256((folder/'manifest.json').read_bytes()).hexdigest()}
        self.verify_backup(result);return result

    def verify_backup(self,backup):
        folder=ROOT/backup['directory']
        if (folder.resolve()!=folder or folder.parent!=ROOT/'backups/preprod' or
                hashlib.sha256((folder/'manifest.json').read_bytes()).hexdigest()!=backup['manifestSha256']):
            raise ValueError('Lot substitué')
        self.helper('verify-backup',str(folder))

    def restore(self,backup):
        self.verify_backup(backup)
        self.helper('restore-isolated',str(ROOT/backup['directory']))
        proof=shared.private_json(self.directory/'restore-proof.json')
        self.verify_schema(proof)
        return proof

    def isolated_cleanup_guard(self):
        attempt=self.directory/'restore-attempt.json'
        if attempt.exists() and shared.private_json(attempt).get('phase')!='cleaned':
            raise ValueError('Copies isolées non nettoyées ; réservation conservée')
        report=self.directory/'schema-validation.json'
        if report.exists() and shared.private_json(report).get('cleanup') is not True:
            raise ValueError('Validateurs non nettoyés ; réservation conservée')

    def verify_schema(self,proof):
        report_path=self.directory/'schema-validation.json'
        report=shared.private_json(report_path)
        attempt=shared.private_json(self.directory/'restore-attempt.json')
        if (attempt.get('phase')!='cleaned' or attempt.get('run')!=self.run_id
                or attempt.get('backup')!=proof.get('backup')
                or attempt.get('project')!=report.get('project')
                or proof.get('project')!=report.get('project')):
            raise ValueError('Preuve isolée hors tentative nettoyée')
        schema=load(P/'isolated-validator.py','backend_schema_validator')
        if (schema.digest(report_path)!=proof.get('schemaValidation',{}).get('reportSha256')
                or report.get('status')!='passed' or report.get('cleanup') is not True
                or report.get('run')!=self.run_id or report.get('backup')!=proof.get('backup')
                or report.get('planHash')!=proof.get('planHash')
                or report.get('runnerSourceSha256')!=schema.digest(P/'IsolatedSchemaValidator.java')
                or report.get('images')!=proof.get('schemaValidation',{}).get('images')):
            raise ValueError('Rapport isolé absent, différent ou refusé')

    def test_window(self,proof):
        if self.stop_requested: raise InterruptedError('Fenêtre annulée avant ouverture')
        if self.cookie_file is None:raise ValueError('Fichier de session requis')
        deadline=proof['notAfter']
        if time.time()>=deadline:raise ValueError('Preuves expirées avant démarrage du gate')
        self.cookie=gate.private_file(self.cookie_file).strip()
        if gate.session_hash(self.cookie) is None:raise ValueError('Cookie invalide')
        self.close_socket()
        # La session n'est ni dans argv/env, ni dans l'état/journal.
        reader,writer=os.pipe()
        parent=os.getpid()
        def parent_death():
            libc=ctypes.CDLL(None,use_errno=True)
            if libc.prctl(1,signal.SIGTERM,0,0,0)!=0 or os.getppid()!=parent:os._exit(126)
        try:
            os.write(writer,self.cookie.encode());os.close(writer);writer=None
            self.child=subprocess.Popen([sys.executable,'-B',str(P/'session-gate.py'),
                '--socket-dir',str(self.gate_dir),'--session-fd',str(reader),'--parent-pid',str(parent),
                '--seconds',str(self.seconds),'--not-after',str(deadline)],pass_fds=(reader,),preexec_fn=parent_death,
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        finally:
            os.close(reader)
            if writer is not None:os.close(writer)
        start=time.monotonic()
        try:
            for attempt in range(50):
                if self.child.poll() is not None:raise ValueError('Gate non démarré')
                if (self.gate_dir/'gate.sock').exists():break
                time.sleep(.1)
            else:raise ValueError('Socket gate absent')
            # Probe HTTP avec secret via stdin curl, jamais argv/env/log.
            if self.stop_requested: return
            self.session_probe()
            next_probe=time.monotonic()+2
            while time.monotonic()-start<self.seconds and time.time()<deadline and not self.stop_requested:
                if self.child.poll() is not None:raise ValueError('Gate arrêté pendant test')
                if time.monotonic()>=next_probe:
                    self.session_probe();next_probe=time.monotonic()+2
                time.sleep(.2)
        finally:
            self.close_socket()
            self.cookie=None

    def session_probe(self):
        for path in ('/pwa/','/pwa/manifest.webmanifest','/pwa/ngsw.json'):
            result=subprocess.run(['curl','--silent','--show-error','--max-time','10',
                                   '--header','@-','http://127.0.0.1:24443'+path,
                                   '--output','/dev/null','--write-out','%{http_code}'],
                                  input=('Cookie: '+self.cookie+'\n').encode(),
                                  capture_output=True,timeout=15)
            if result.returncode or result.stdout!=b'200':raise ValueError('PWA indisponible dans la fenêtre')
