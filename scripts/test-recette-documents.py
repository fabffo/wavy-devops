#!/usr/bin/env python3
"""Lots et backup standard avec Docker simulé ; fixtures privées uniquement."""
import io
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
import sys
sys.dont_write_bytecode=True
import recette_documents as docs
ROOT=Path(__file__).resolve().parent.parent
DOCUMENT='1/2/3/12345678-1234-1234-1234-123456789abc'


def archive(path, mutation=None):
    with tarfile.open(path,'w') as target:
        for name in ('.','1','1/2','1/2/3',DOCUMENT):
            entry=tarfile.TarInfo(name); entry.uid=100; entry.gid=101
            entry.type=tarfile.DIRTYPE if name!=DOCUMENT else tarfile.REGTYPE
            entry.mode=0o700 if entry.isdir() else 0o600
            payload=b'private-fixture-document'
            if entry.isfile():entry.size=len(payload)
            if mutation: mutation(entry)
            target.addfile(entry,io.BytesIO(payload) if entry.isfile() else None)
    path.chmod(0o600)


class Documents(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.root.chmod(0o700)
        for db in docs.DATABASES:
            p=self.root/(db+'.dump');p.write_bytes(b'fixture-'+db.encode());p.chmod(0o600)
        archive(self.root/'justificatifs.tar')

    def test_complete_lot_integrity_and_no_false_restore_claim(self):
        docs.seal(self.root,'fixture-store',100,101)
        result=docs.verify(self.root)
        self.assertEqual(result['documentCount'],1);self.assertFalse(result['restorationVerified'])

    def test_missing_or_altered_database_is_refused(self):
        docs.seal(self.root,'fixture-store',100,101)
        (self.root/'tiers.dump').write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError,'Intégrité'):docs.verify(self.root)
        (self.root/'tiers.dump').unlink()
        with self.assertRaises(ValueError):docs.verify(self.root)

    def test_archive_owners_permissions_traversal_and_links_rejected(self):
        changes=[lambda e:setattr(e,'uid',0),lambda e:setattr(e,'mode',0o777),
                 lambda e:setattr(e,'name','../../escape'),lambda e:setattr(e,'type',tarfile.SYMTYPE)]
        for change in changes:
            with self.subTest(change=change):
                archive(self.root/'justificatifs.tar',change)
                with self.assertRaises(ValueError):docs.validate_archive(self.root/'justificatifs.tar',100,101)

    def test_symlink_and_public_backup_permissions_refused(self):
        (self.root/'factures.dump').chmod(0o644)
        with self.assertRaises(ValueError):docs.seal(self.root,'fixture-store',100,101)
        (self.root/'factures.dump').unlink();(self.root/'factures.dump').symlink_to(self.root/'tiers.dump')
        with self.assertRaises(ValueError):docs.seal(self.root,'fixture-store',100,101)

    def test_foreign_environment_and_unsafe_file_set_refused(self):
        docs.seal(self.root,'fixture-store',100,101)
        p=self.root/'recette-pwa.json';m=json.loads(p.read_text());m['environment']='preprod';p.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError,'Provenance'):docs.verify(self.root)


FAKE_DOCKER=r'''#!/usr/bin/python3
import json,os,sys
from pathlib import Path
args=sys.argv[1:]
with open(os.environ['FIXTURE_LOG'],'a') as out:out.write(json.dumps(args)+'\n')
if args[0]=='inspect':
 if '-f' in args:
  field=args[args.index('-f')+1]
  print('true' if 'Running' in field else ('137' if os.environ.get('FIXTURE_FAIL')=='forced' else '0') if 'ExitCode' in field else 'sha256:fixture')
 else:
  print(json.dumps([{'Config':{'Env':['WAVY_FACTURES_STOCKAGE_JUSTIFICATIFS=/app/justificatifs']},'Mounts':[{'Destination':'/app/justificatifs','Type':'volume','Name':'fixture-store'}]}]))
elif args[0]=='exec':
 if 'pg_dump' in args:sys.stdout.buffer.write(b'fixture-dump')
 elif 'pg_restore' in args:sys.stdin.buffer.read()
 elif 'id -u' in args[-1] and 'storage-ok' not in args[-1]:print('100 101')
 elif 'private-storage-ok' in args[-1]:print('private-storage-ok')
elif args[0]=='run':
 if os.environ.get('FIXTURE_FAIL')=='documents':sys.exit(1)
 sys.stdout.buffer.write(Path(os.environ['FIXTURE_ARCHIVE']).read_bytes())
elif args[0]=='start' and os.environ.get('FIXTURE_FAIL')=='start':sys.exit(1)
elif args[0] in ('info','compose','volume','stop','start'):pass
else:sys.exit(90)
'''


class StandardBackup(unittest.TestCase):
    def run_backup(self, failure='', competing=False):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=Path(tmp.name)
        (root/'scripts').mkdir();(root/'bin').mkdir()
        for name in ('backup-db.sh','_common.sh','_recette-documents.sh','release_images.py','recette_pwa.py','recette_documents.py'):
            shutil.copy(ROOT/'scripts'/name,root/'scripts'/name)
        (root/'.env.recette').write_text('WAVY_FACTURES_JUSTIFICATIFS_VOLUME=fixture-store\n')
        archive(root/'fixture.tar')
        exe=root/'bin/docker';exe.write_text(FAKE_DOCKER);exe.chmod(0o700)
        log=root/'calls'
        env=dict(os.environ,PATH=str(root/'bin')+':'+os.environ['PATH'],WAVY_ENV='recette',FIXTURE_LOG=str(log),FIXTURE_ARCHIVE=str(root/'fixture.tar'),FIXTURE_FAIL=failure)
        lock=None
        if competing:
            (root/'deployments').mkdir()
            lock=(root/'deployments/recette.lock').open('w')
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try: result=subprocess.run(['bash',str(root/'scripts/backup-db.sh')],env=env,capture_output=True,text=True)
        finally:
            if lock: lock.close()
        calls=[json.loads(line) for line in log.read_text().splitlines()]
        return root,result,calls

    def test_standard_backup_stops_writers_then_captures_databases_documents_and_resumes(self):
        root,result,calls=self.run_backup()
        self.assertEqual(result.returncode,0,result.stderr)
        stopped=[i for i,c in enumerate(calls) if c[0]=='stop']
        dumps=[i for i,c in enumerate(calls) if 'pg_dump' in c]
        archived=next(i for i,c in enumerate(calls) if c[0]=='run')
        started=[i for i,c in enumerate(calls) if c[0]=='start']
        self.assertEqual(len(stopped),6);self.assertEqual(len(dumps),5);self.assertEqual(len(started),6)
        self.assertLess(max(stopped),min(dumps));self.assertLess(max(dumps),archived);self.assertLess(archived,min(started))
        folders=[p for p in (root/'backups').iterdir() if p.is_dir()]
        self.assertEqual(len(folders),1);self.assertTrue(docs.verify(folders[0])['verified'])
        self.assertTrue(all('readonly' in c[c.index('--mount')+1] and '--network' in c and c[c.index('--network')+1]=='none' for c in calls if c[0]=='run'))

    def test_document_failure_preserves_incomplete_lot_and_resumes_original_services(self):
        root,result,calls=self.run_backup('documents')
        self.assertNotEqual(result.returncode,0)
        folders=[p for p in (root/'backups').iterdir() if p.is_dir()]
        self.assertEqual(len(folders),1);self.assertTrue(folders[0].name.startswith('.incomplete-'))
        self.assertFalse((folders[0]/'recette-pwa.json').exists())
        self.assertEqual(sum(c[0]=='start' for c in calls),6)

    def test_other_recette_operation_prevents_backup_before_any_stop_or_dump(self):
        root,result,calls=self.run_backup(competing=True)
        self.assertNotEqual(result.returncode,0);self.assertIn('déjà en cours',result.stderr)
        self.assertFalse(any(c[0]=='stop' or 'pg_dump' in c for c in calls))

    def test_forced_stop_refuses_backup_and_resumes_only_stopped_services(self):
        root,result,calls=self.run_backup('forced')
        self.assertNotEqual(result.returncode,0)
        self.assertFalse(any('pg_dump' in c for c in calls))
        self.assertEqual(sum(c[0]=='start' for c in calls),1)
        self.assertIn('Arrêt forcé',result.stderr)

    def test_resume_failure_is_not_a_complete_backup(self):
        root,result,calls=self.run_backup('start')
        self.assertNotEqual(result.returncode,0)
        stage=next(p for p in (root/'backups').iterdir() if p.is_dir())
        self.assertTrue((stage/'recette-pwa.json').exists())
        with self.assertRaisesRegex(ValueError,'Lot incomplet'):docs.verify(stage)
        self.assertIn('Services RECETTE à reprendre',result.stderr)

    def test_sql_only_restore_is_explicitly_blocked_for_document_lots(self):
        text=(ROOT/'scripts/restore-db.sh').read_text()
        self.assertLess(text.index('Lot DB + justificatifs RECETTE'),text.index('pg_restore'))
        self.assertIn('justificatifs.tar',text)


if __name__=='__main__':unittest.main()
