#!/usr/bin/env python3
"""Commandes réelles dans une copie temporaire, Docker simulé : aucun accès VM/daemon."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('guards',ROOT/'scripts/preprod_operation.py')
guards=importlib.util.module_from_spec(spec);spec.loader.exec_module(guards)


class Guards(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);shutil.copytree(ROOT/'scripts',self.root/'scripts',ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copy2(ROOT/'wavy',self.root/'wavy')
        self.bin=self.root/'bin';self.bin.mkdir();self.log=self.root/'docker.jsonl'
        docker=self.bin/'docker'
        docker.write_text('#!'+sys.executable+'''\nimport json,os,sys
with open(os.environ['MOCK_LOG'],'a') as f:f.write(json.dumps(sys.argv[1:])+'\\n')
if sys.argv[1:3]==['context','inspect']:print('unix:///var/run/docker.sock')
''');docker.chmod(0o755)
        self.env={**os.environ,'PATH':str(self.bin)+':/usr/bin:/bin','MOCK_LOG':str(self.log),'WAVY_ENV':'preprod'}
        for key in ('WAVY_PREPROD_LOCK_FD','WAVY_PREPROD_WRAPPED_ENTRY','PWA_RELEASE_RUN'):
            self.env.pop(key,None)

    def matrix(self):
        return [ ['scripts/stop-all.sh'], ['scripts/deploy.sh','preprod','factures-api'],
                 ['scripts/release-preprod.sh','DEPLOY','factures-api'],
                 ['scripts/rollback.sh','preprod','factures-api','0.1.0-abcdef0','--yes'],
                 ['scripts/backup-preprod.sh'], ['scripts/backup-db.sh'], ['scripts/restore-db.sh'], ['scripts/restore-preprod.sh','missing','--with-documents'],
                 ['scripts/initialize-preprod.sh','--empty-installation'],['scripts/validate-preprod-runtime.sh'],
                 ['wavy','stop','preprod'],['wavy','restart','preprod','factures-api'],
                 ['wavy','backup','preprod'],['wavy','restore','preprod','missing','--with-documents'],
                 ['wavy','start','preprod'],['wavy','restart','preprod','all'] ]

    def assert_classics_denied(self):
        for cmd in self.matrix():
            with self.subTest(cmd=cmd):
                result=subprocess.run(['bash',str(self.root/cmd[0]),*cmd[1:]],env=self.env,input='n\n',
                                      capture_output=True,text=True,timeout=10)
                self.assertNotEqual(result.returncode,0)
        for options in (['up','-d'],['stop'],['start'],['restart'],['down'],['exec','fake','true'],['pull'],
                        ['config','--output',str(self.root/'rendered.json')]):
            result=subprocess.run([sys.executable,str(self.root/'scripts/preprod_config.py'),'compose',str(self.root/'unused.env'),*options],
                                  env=self.env,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0,options)
        self.assertFalse((self.root/'rendered.json').exists())
        mutations=[]
        if self.log.exists():
            for line in self.log.read_text().splitlines():
                args=json.loads(line)
                if any(word in args for word in ('up','stop','start','restart','kill','pull','rm','down','create','exec')):mutations.append(args)
        self.assertEqual(mutations,[])

    def test_all_classic_mutations_denied_under_concurrent_release_lock(self):
        with guards.Operation(self.root):self.assert_classics_denied()

    def test_reservation_survives_process_end_and_blocks_classics(self):
        with guards.Operation(self.root) as op:op.reserve('a'*32,'hash','fixture-time')
        self.assert_classics_denied()
        self.assertTrue((self.root/'deployments/preprod-reservation.json').is_file())
        with self.assertRaises(ValueError):
            with guards.Operation(self.root):pass
        with guards.Operation(self.root,owner='a'*32) as op:op.release('a'*32)
        with guards.Operation(self.root):pass

    def test_candidate_compose_cli_cannot_bypass_lock_even_closed(self):
        candidate=ROOT/'preparation/pwa-notes-frais/scripts/preprod_config.py'
        with guards.Operation(self.root):
            result=subprocess.run([sys.executable,str(candidate),'compose',str(self.root/'unused.env'),
                'up','-d','--no-deps','--no-build','--force-recreate','--pull','never','wavy-erp-shell-preprod'],
                env=self.env,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertFalse(self.log.exists())

    def test_matching_owner_required_even_with_inherited_lock(self):
        with guards.Operation(self.root) as parent:
            parent.reserve('a'*32,'hash','now')
            for owner in (None,'b'*32):
                with self.assertRaises(ValueError):
                    with guards.Operation(self.root,owner=owner,inherited=parent.fd):pass
            with guards.Operation(self.root,owner='a'*32,inherited=parent.fd):pass
        # Ni fin du processus ni disponibilité du flock ne retirent le fichier durable.
        self.assertTrue((self.root/'deployments/preprod-reservation.json').exists())


if __name__=='__main__':unittest.main()
