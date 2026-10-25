#!/usr/bin/env python3
"""Contre-exemples de revue : invariants bloquants, sans DB ni volume Docker.
Régressions obligatoires des quatre corrections ; aucun expectedFailure.
"""
from contextlib import contextmanager
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
import os
import multiprocessing
import signal
import subprocess
from pathlib import Path
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

P=Path(__file__).resolve().parent

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

fixture=load(P/'test-private-orchestrator.py','review_engine_fixture')
restore=load(P/'restore-private.py','review_restore')


class TemporalRequirements(unittest.TestCase):
    def setUp(self):
        self.f=fixture.Orchestration();self.f.setUp();self.addCleanup(self.f.doCleanups)

    def test_v3_preflight_and_closure_are_rechecked_after_long_baseline(self):
        f=self.f;m=fixture.m;clock=[fixture.LOGICAL_TIME.timestamp()]
        last={};ages=[]
        original_preflight=f.backend.preflight;original_close=f.backend.close
        original_backup=f.backend.backup;original_provision=f.backend.provision_storage
        def preflight(plan):last['preflight']=clock[0];return original_preflight(plan)
        def close():last['close']=clock[0];return original_close()
        def backup(baseline=False):
            result=original_backup(baseline)
            if baseline:clock[0]+=120
            return result
        def provision(fd):
            ages.extend((clock[0]-last['preflight'],clock[0]-last['close']))
            return original_provision(fd)  # consume V3 réel, pas un mock du reçu.
        with patch.object(m.time,'time',lambda:clock[0]),patch.object(m.public.storage_auth.time,'time',lambda:clock[0]),\
             patch.object(f.backend,'preflight',preflight),patch.object(f.backend,'close',close),\
             patch.object(f.backend,'backup',backup),patch.object(f.backend,'provision_storage',provision):
            f.prepare()
        self.assertTrue(ages)
        self.assertTrue(all(age<60 for age in ages),f'Contrôles déclarés frais mais âgés de {ages} secondes')

    def test_prerequisite_expiring_during_open_checks_never_opens(self):
        f=self.f;m=fixture.m;f.deploy()
        start=fixture.LOGICAL_TIME.timestamp();clock=[start]
        state=m.op.read_private(f.directory/'state.json')
        state['prerequisites']['checkedAt']=datetime.fromtimestamp(start-86390,timezone.utc).isoformat()
        m.op.atomic_json(f.directory/'state.json',state)
        proof=f.authorization();original_checks=f.backend.checks
        class ClockDateTime(datetime):
            @classmethod
            def now(cls,tz=None):return datetime.fromtimestamp(clock[0],timezone.utc)
        def checks():original_checks();clock[0]+=20
        with patch.object(m.public,'datetime',ClockDateTime),patch.object(f.backend,'checks',checks):
            try:f.call('open-test',proof)
            except ValueError:pass
        self.assertNotIn('test-window',f.backend.events,'Le test a ouvert après expiration du prérequis de release')


    def test_restore_proof_expiring_during_open_checks_never_opens(self):
        f=self.f;m=fixture.m;f.deploy()
        start=fixture.LOGICAL_TIME.timestamp();clock=[start]
        state=m.op.read_private(f.directory/'state.json')
        state['restore']['checkedAt']=datetime.fromtimestamp(start-86390,timezone.utc).isoformat()
        m.op.atomic_json(f.directory/'state.json',state)
        proof=f.authorization();original_checks=f.backend.checks
        class ClockDateTime(datetime):
            @classmethod
            def now(cls,tz=None):return datetime.fromtimestamp(clock[0],timezone.utc)
        def checks():original_checks();clock[0]+=20
        with patch.object(m.public,'datetime',ClockDateTime),patch.object(f.backend,'checks',checks):
            with self.assertRaises(ValueError):f.call('open-test',proof)
        self.assertNotIn('test-window',f.backend.events)


@contextmanager
def restore_fixture(invalid_fd=False,down_fails=False,down_error=None):
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp);directory=root/'deployments/pwa-release';directory.mkdir(parents=True,mode=0o700)
        folder=root/'backups/preprod/fixture';folder.mkdir(parents=True)
        (folder/'manifest.json').write_text('{}')
        backup={'directory':str(folder.relative_to(root)),
                'manifestSha256':hashlib.sha256((folder/'manifest.json').read_bytes()).hexdigest()}
        run='a'*32
        plan={'privateProfile':'private-tunnel-v1'}
        digest=hashlib.sha256(json.dumps(plan,sort_keys=True).encode()).hexdigest()
        restore.op.atomic_json(directory/'runtime-plan.json',plan)
        restore.op.atomic_json(root/'deployments/preprod-reservation.json',{'run':run,'planHash':digest})
        restore.op.atomic_json(directory/'state.json',{'profile':'private-tunnel-v1','phase':'awaiting-restore',
                               'run':run,'planHash':digest,'backup':backup,'pending':'isolated-restore'})
        docker=[]
        def command(args,**kwargs):
            if args[0]=='openssl':
                output=Path(args[args.index('-out')+1])
                if output.name=='documents.tar':
                    with tarfile.open(output,'w') as archive:
                        for name in ('contrats','notes-frais'):
                            item=tarfile.TarInfo(name);item.type=tarfile.DIRTYPE
                            item.uid=100;item.gid=101;item.mode=0o700;archive.addfile(item)
                else:output.write_bytes(b'fixture-not-a-real-database')
                return b''
            if args[0]!='docker':raise AssertionError('Commande inattendue')
            if args[1:3]==['context','inspect']:return b'unix:///var/run/docker.sock'
            docker.append(args)
            if args[-3:]==['config','--format','json']:
                services={name:{'network_mode':'none','read_only':True,'image':
                    'postgres:16-alpine@sha256:93d55776e04376e19adb2733e3ccebb4392ee7dd86d8ff238503b30fe719c84f'}
                    for name in (*restore.DATABASES,'documents')}
                return json.dumps({'services':services,'volumes':{}}).encode()
            if 'up' in args:raise RuntimeError('fixture-up-failure')
            if 'down' in args:
                if down_error is not None:raise down_error
                if down_fails:raise RuntimeError('fixture-down-failure')
                return b''
            raise AssertionError('Docker réel interdit dans cette reproduction')
        with restore.op.Operation(root,owner=run) as owner:
            # Le cas FD invalide doit être refusé, même si aucun autre détenteur ne bloque.
            if invalid_fd:
                import fcntl
                fcntl.flock(owner.fd,fcntl.LOCK_UN)
            env={'PWA_RELEASE_RUN':run,'PWA_RELEASE_LOCK_FD':str(999999 if invalid_fd else owner.fd),
                 'WAVY_PRIVATE_PWA_GATE_DIR':str(root/'gate')}
            if invalid_fd:env['DOCKER_HOST']='tcp://forbidden.invalid:2375'
            with patch.object(restore,'ROOT',root),patch.object(restore.base,'dotenv',return_value={
                 'WAVY_BACKUP_ENCRYPTION_PASSPHRASE':'fixture-only-crypto-material'}),\
                 patch.object(restore.base,'render',return_value={'services':{'wavy-factures-api-preprod':{'environment':{}}}}),\
                 patch.object(restore.manifest,'run'),patch.object(restore,'command',command),\
                 patch.object(restore.socket,'gethostname',return_value='wavy-preprod'),\
                 patch.object(restore,'load',return_value=SimpleNamespace(validate=lambda *args:None)),\
                 patch.dict(os.environ,env,clear=True):
                yield root,directory,folder,docker


def interrupted_staging(directory,reply):
    with restore.recovery_staging(Path(directory)) as (tmp,recovery):
        config=tmp/'restore.env';config.write_text('fixture');config.chmod(0o600)
        restore.op.atomic_json(Path(directory)/'restore-attempt.json',{'phase':'creating','envFile':str(config)})
        recovery['required']=True
        reply.send(str(config));reply.close()
        multiprocessing.Event().wait()


class RestoreRequirements(unittest.TestCase):
    def test_invalid_inherited_fd_and_remote_daemon_refused_before_docker(self):
        with restore_fixture(invalid_fd=True) as (root,directory,folder,docker):
            try:restore.restore(root/'.env.preprod',folder)
            except (ValueError,OSError,RuntimeError):pass
            self.assertEqual(docker,[], 'CLI direct : Docker atteint malgré FD invalide et override distant')

    def test_cleanup_failure_preserves_recorded_environment_for_recovery(self):
        with restore_fixture(down_fails=True) as (root,directory,folder,docker):
            with self.assertRaises(RuntimeError):restore.restore(root/'.env.preprod',folder)
            attempt=restore.op.read_private(directory/'restore-attempt.json')
            self.assertEqual(attempt['phase'],'creating')
            self.assertTrue(Path(attempt['envFile']).is_file(),
                            'Le fichier env de reprise a été supprimé malgré échec down --volumes')

    def test_host_override_and_wrong_fd_inode_refused_independently(self):
        for name,value in (('DOCKER_HOST','tcp://forbidden.invalid:2375'),('DOCKER_CONTEXT','foreign')):
            with self.subTest(name=name),restore_fixture() as (root,directory,folder,docker),patch.dict(os.environ,{name:value}):
                with self.assertRaises(ValueError):restore.restore(root/'.env.preprod',folder)
                self.assertEqual(docker,[])
        with restore_fixture() as (root,directory,folder,docker),patch.object(restore.socket,'gethostname',return_value='not-preprod'):
            with self.assertRaises(ValueError):restore.restore(root/'.env.preprod',folder)
            self.assertEqual(docker,[])
        with restore_fixture() as (root,directory,folder,docker):
            wrong=os.open(root/'wrong.lock',os.O_RDWR|os.O_CREAT,0o600)
            try:
                with patch.dict(os.environ,{'PWA_RELEASE_LOCK_FD':str(wrong)}):
                    with self.assertRaises(ValueError):restore.restore(root/'.env.preprod',folder)
                self.assertEqual(docker,[])
            finally:os.close(wrong)

    def test_cleanup_timeout_preserves_recovery_and_never_publishes_proof(self):
        with restore_fixture(down_error=subprocess.TimeoutExpired('fixture',1)) as (root,directory,folder,docker):
            with self.assertRaises(subprocess.TimeoutExpired):restore.restore(root/'.env.preprod',folder)
            attempt=restore.op.read_private(directory/'restore-attempt.json')
            self.assertTrue(Path(attempt['envFile']).is_file())
            self.assertFalse((directory/'restore-proof.json').exists())

    def test_successful_cleanup_after_up_failure_removes_staging(self):
        with restore_fixture() as (root,directory,folder,docker):
            with self.assertRaisesRegex(RuntimeError,'fixture-up-failure'):restore.restore(root/'.env.preprod',folder)
            self.assertEqual(restore.op.read_private(directory/'restore-attempt.json')['phase'],'cleaned')
            self.assertEqual(list(directory.glob('restore-private-*')),[])
            self.assertFalse((directory/'restore-proof.json').exists())

    def test_sigterm_and_sigkill_preserve_recovery_configuration(self):
        ctx=multiprocessing.get_context('fork')
        for sig in (signal.SIGTERM,signal.SIGKILL):
            with self.subTest(signal=sig),tempfile.TemporaryDirectory() as temp:
                reader,writer=ctx.Pipe(False)
                process=ctx.Process(target=interrupted_staging,args=(temp,writer));process.start();writer.close()
                try:
                    self.assertTrue(reader.poll(10));config=Path(reader.recv())
                    os.kill(process.pid,sig);process.join(5)
                    self.assertFalse(process.is_alive())
                    self.assertTrue(config.is_file())
                    self.assertEqual(config.stat().st_mode & 0o777,0o600)
                    self.assertEqual(config.parent.stat().st_mode & 0o777,0o700)
                finally:
                    if process.is_alive():process.kill();process.join(5)
                    reader.close()

if __name__=='__main__':unittest.main()
