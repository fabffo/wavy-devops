#!/usr/bin/env python3
"""Transaction Bash réelle + crypto sur fixtures ; Docker/volumes entièrement simulés."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

P=Path(__file__).resolve().parent
ROOT=P.parents[2]
spec=importlib.util.spec_from_file_location('backup_manifest',ROOT/'scripts/preprod_backup_manifest.py')
manifest=importlib.util.module_from_spec(spec);spec.loader.exec_module(manifest)


class Backup(unittest.TestCase):
    def fixture(self,baseline):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=Path(tmp.name)
        archive=root/'documents.tar'
        with tarfile.open(archive,'w') as out:
            for name in (('contrats',) if baseline else ('contrats','notes-frais')):
                entry=tarfile.TarInfo(name);entry.type=tarfile.DIRTYPE;entry.uid=100;entry.gid=101;entry.mode=0o700
                out.addfile(entry)
        script=r'''
set -euo pipefail
preprod_value() {
  case "$1" in
    WAVY_BACKUP_ENCRYPTION_PASSPHRASE) printf '%s' 'fictional-crypto-test-key-0000000000000000';;
    WAVY_BACKUP_RETENTION_DAYS) echo 7;;
  esac
}
preprod_host_guard() { :; }
candidate_validate() { :; }
preprod_document_volume_guard() { :; }
preprod_backup_operation_lock() { :; }
preprod_container_guard() { :; }
require_command() { command -v "$1" >/dev/null; }
preprod_quiesce() { QUIESCED_SERVICES=(); }
preprod_resume() { :; }
preprod_wait() { :; }
db_container() { printf '%s' "$1"; }
db_user() { echo fixture; }
db_name() { printf '%s' "$1"; }
preprod_document_tool() { cat "$FIXTURE_ARCHIVE"; }
docker() { printf '%s' 'fixture-dump'; }
info() { :; }
success() { :; }
die() { exit 1; }
source "$FIXTURE_BACKUP"
'''
        env={**os.environ,'ROOT_DIR':str(root),'SCRIPT_DIR':str(ROOT/'scripts'),
             'FIXTURE_ARCHIVE':str(archive),'FIXTURE_BACKUP':str(P/'backup-private.sh')}
        env.pop('PWA_RELEASE_LOCK_FD',None)
        if baseline:env['WAVY_PRIVATE_BASELINE']='1'
        else:env.pop('WAVY_PRIVATE_BASELINE',None)
        result=subprocess.run(['bash','-c',script],env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        lots=list((root/'backups/preprod').glob('????????T??????Z-*'))
        self.assertEqual(len(lots),1)
        return lots[0]
    def verify(self,folder):
        old=os.environ.get('WAVY_BACKUP_PASSPHRASE')
        os.environ['WAVY_BACKUP_PASSPHRASE']='fictional-crypto-test-key-0000000000000000'
        try:manifest.run('verify',folder)
        finally:
            if old is None:os.environ.pop('WAVY_BACKUP_PASSPHRASE',None)
            else:os.environ['WAVY_BACKUP_PASSPHRASE']=old
    def test_baseline_contracts_only_signs_five_dumps_and_documents(self):
        folder=self.fixture(True);self.verify(folder)
        self.assertEqual(len(list(folder.glob('*.enc'))),6)
    def test_complete_backup_and_ciphertext_tamper(self):
        folder=self.fixture(False);self.verify(folder)
        (folder/'documents.tar.enc').write_bytes(b'altered')
        with self.assertRaises(ValueError):self.verify(folder)

if __name__=='__main__':unittest.main()
