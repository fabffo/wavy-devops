#!/usr/bin/env python3
"""Moteur commun et preuve de sauvegarde : fixtures uniquement, sans daemon ni VM."""
import fcntl
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent


class Batch(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='wavy-batch-core-')
        self.root=Path(self.tmp.name)
        scripts=self.root/'scripts';scripts.mkdir()
        for name in ('delivery_batch.py','preprod_operation.py','release_images.py','recette_documents.py'):
            shutil.copyfile(ROOT/'scripts'/name,scripts/name)
        shutil.copytree(ROOT/'versions',self.root/'versions')
        (scripts/'delivery-preflight.sh').write_text('#!/bin/sh\nprintf "preflight\\n" >> "$FIXTURE_EVENTS"\n')
        (scripts/'delivery-apply.sh').write_text('''#!/bin/bash
set -euo pipefail
python3 "$PWD/scripts/delivery_batch.py" check recette
for name in socle-api tiers-api contrats-api factures-api tresorerie-api gateway socle-front tiers-front contrats-front factures-front tresorerie-front pwa erp-shell; do printf 'apply %s\n' "$name" >> "$FIXTURE_EVENTS"; done
''')
        (scripts/'backup-db.sh').write_text('''#!/bin/bash
set -euo pipefail
printf 'backup\n' >> "$FIXTURE_EVENTS"
python3 - <<'INNER'
import io,os,pathlib,tarfile,sys
os.umask(0o077)
root=pathlib.Path.cwd();sys.path.insert(0,str(root/'scripts'))
from recette_documents import seal
folder=root/'backups/2026-11-03_235959';folder.mkdir(parents=True,mode=0o700)
for db in ('socle','tiers','contrats','factures','tresorerie'):(folder/(db+'.dump')).write_bytes(b'FICTIONAL SQL ONLY')
with tarfile.open(folder/'justificatifs.tar','w') as archive:
 item=tarfile.TarInfo('.');item.type=tarfile.DIRTYPE;item.uid=100;item.gid=101;item.mode=0o700;archive.addfile(item)
seal(folder,'fixture-documents',100,101)
if os.environ.get('FIXTURE_CORRUPT'):(folder/'socle.dump').write_bytes(b'CORRUPTED FIXTURE')
INNER
''')
        binary=self.root/'bin';binary.mkdir()
        docker=binary/'docker';docker.write_text('''#!/bin/sh
case "$*" in *Config.Image*) echo fixture-old-reference;; *) echo fixture-old-image;; esac
''');docker.chmod(0o700)
        self.events=self.root/'events'
        self.env={k:v for k,v in os.environ.items() if not k.startswith(('WAVY_DELIVERY_SESSION','WAVY_RECETTE_LOCK'))}
        self.env.update(PATH=str(binary)+os.pathsep+self.env['PATH'],FIXTURE_EVENTS=str(self.events))

    def tearDown(self):self.tmp.cleanup()

    def run_batch(self, env=None):
        return subprocess.run([sys.executable,'-B',str(self.root/'scripts/delivery_batch.py'),'run','recette'],
                              cwd=self.root,env=env or self.env,capture_output=True,text=True,timeout=15)

    def test_recette_uses_same_engine_one_verified_coordinated_lot(self):
        result=self.run_batch()
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        events=self.events.read_text().splitlines()
        self.assertEqual(events[:2],['preflight','backup'])
        self.assertEqual(events.count('backup'),1)
        self.assertEqual(len([e for e in events if e.startswith('apply ')]),13)
        record=json.loads(next((self.root/'deployments').glob('*.private.json')).read_text())
        self.assertTrue(record['backupVerified'])
        self.assertEqual(record['phase'],'complete')
        self.assertEqual(len(record['completed']),13)

    def test_corrupt_backup_never_reaches_apply(self):
        result=self.run_batch(dict(self.env,FIXTURE_CORRUPT='1'))
        self.assertEqual(result.returncode,1)
        self.assertIn('etape=backup_integrity',result.stderr)
        self.assertEqual(self.events.read_text().splitlines(),['preflight','backup'])
        self.assertTrue((self.root/'backups/2026-11-03_235959').is_dir())
        record=json.loads(next((self.root/'deployments').glob('*.private.json')).read_text())
        self.assertTrue(Path(record['backup']).is_dir())
        self.assertFalse(record['backupVerified'])

    def test_a_successful_provider_without_a_lot_does_not_skip_backup(self):
        (self.root/'scripts/backup-db.sh').write_text('#!/bin/sh\nexit 0\n')
        result=self.run_batch()
        self.assertEqual(result.returncode,1)
        self.assertNotIn('apply ',self.events.read_text())

    def test_apply_cannot_be_called_without_a_live_sealed_context(self):
        for fd in (None,'99999'):
            env=dict(self.env)
            if fd is not None:env['WAVY_DELIVERY_SESSION_FD']=fd
            result=subprocess.run([sys.executable,'-B',str(self.root/'scripts/delivery_batch.py'),'check','recette'],env=env,capture_output=True)
            self.assertEqual(result.returncode,1)
        self.assertFalse(self.events.exists())

    def test_same_user_cannot_forge_an_engine_receipt_with_an_unrelated_process(self):
        sys.path.insert(0,str(self.root/'scripts'))
        from release_images import release
        fd=os.memfd_create('fixture-proof',os.MFD_ALLOW_SEALING)
        try:
            payload={'root':str(self.root),'environment':'recette','backupVerified':True,
                     'images':release(self.root,'recette')[2],'issuerPid':os.getpid(),'issuerFd':fd,'backup':str(self.root/'backups/fixture')}
            os.write(fd,json.dumps(payload).encode())
            for sealed in (False,True):
                if sealed:fcntl.fcntl(fd,fcntl.F_ADD_SEALS,fcntl.F_SEAL_SEAL|fcntl.F_SEAL_WRITE|fcntl.F_SEAL_SHRINK|fcntl.F_SEAL_GROW)
                result=subprocess.run([sys.executable,'-B',str(self.root/'scripts/delivery_batch.py'),'check','recette'],
                                      env=dict(self.env,WAVY_DELIVERY_SESSION_FD=str(fd)),pass_fds=(fd,),capture_output=True)
                self.assertEqual(result.returncode,1)
        finally:os.close(fd);sys.path.pop(0)
        self.assertFalse(self.events.exists())

    def test_interrupt_waits_for_provider_cleanup_and_never_applies(self):
        marker=self.root/'ready';cleaned=self.root/'resumed'
        (self.root/'scripts/backup-db.sh').write_text('''#!/bin/bash
trap 'sleep 0.2; printf resumed > "'''+str(cleaned)+'''"; exit 143' TERM
printf ready > "'''+str(marker)+'''"
while :; do sleep 1; done
''')
        process=subprocess.Popen([sys.executable,'-B',str(self.root/'scripts/delivery_batch.py'),'run','recette'],
                                 cwd=self.root,env=self.env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            deadline=time.monotonic()+5
            while not marker.exists() and time.monotonic()<deadline:time.sleep(0.05)
            self.assertTrue(marker.exists())
            process.send_signal(signal.SIGTERM)
            out,err=process.communicate(timeout=10)
            self.assertEqual(process.returncode,143,err)
            self.assertTrue(cleaned.exists())
            self.assertNotIn('apply ',self.events.read_text())
        finally:
            if process.poll() is None:process.kill();process.wait()


if __name__=='__main__':unittest.main()
