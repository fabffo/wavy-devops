#!/usr/bin/env python3
"""Garde-fous testés avec Docker simulé et cinq fichiers factices hors dépôt."""
import json
import fcntl
import tarfile
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
DIGEST = 'sha256:'+'a'*64


class Guards(unittest.TestCase):
    def verify(self, *, digest=DIGEST, revision='6570deb', version='0.1.0', source='https://github.com/fabffo/wavy-socle-api', missing=False):
        labels = {'org.opencontainers.image.revision': revision, 'org.opencontainers.image.version': version, 'org.opencontainers.image.source': source}
        shell = '''
source "$1/scripts/_preprod.sh"
docker() {
  if [[ "$1 $2" == 'manifest inspect' ]]; then [[ "$MOCK_MISSING" == false ]]; return; fi
  if [[ "$1" == pull ]]; then return 0; fi
  if [[ "$1 $2" == 'image inspect' ]]; then
    if [[ "$*" == *RepoDigests* ]]; then printf 'ghcr.io/fabffo/wavy-socle-api@%s\\n' "$MOCK_DIGEST";
    else printf '%s\\n' "$MOCK_LABELS"; fi
    return
  fi
  return 97
}
preprod_verify_image socle-api 0.1.0-6570deb "$2"
'''
        env = dict(os.environ, MOCK_DIGEST=digest, MOCK_LABELS=json.dumps(labels), MOCK_MISSING=str(missing).lower())
        return subprocess.run(['bash', '-c', shell, '_', str(ROOT), DIGEST], env=env, capture_output=True).returncode

    def test_oci_valid(self):
        self.assertEqual(self.verify(), 0)

    def test_reject_digest(self):
        self.assertNotEqual(self.verify(digest='sha256:'+'b'*64), 0)

    def test_reject_oci_labels(self):
        for override in ({'revision':'deadbee'}, {'version':'0.2.0'}, {'source':'https://github.com/other/repo'}):
            self.assertNotEqual(self.verify(**override), 0)

    def test_reject_missing_remote(self):
        self.assertNotEqual(self.verify(missing=True), 0)

    def test_msi_rejected_before_docker(self):
        result = subprocess.run(['bash', '-c', 'source "$1/scripts/_preprod.sh"; hostname() { echo MSI; }; docker() { echo FORBIDDEN_DOCKER >&2; return 97; }; preprod_host_guard', '_', str(ROOT)], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(b'FORBIDDEN_DOCKER', result.stderr)

    def test_history_convention(self):
        for path in (ROOT/'versions/history/preprod').glob('*.tsv'):
            self.assertEqual(path.read_text().splitlines()[0], 'version\tdigest\tcommit\tdate_validation')
            for row in path.read_text().splitlines()[1:]:
                self.assertEqual(len(row.split('\t')), 4)
                self.assertRegex(row.split('\t')[1], r'^sha256:[a-f0-9]{64}$')

    def test_document_archive_paths_and_owners(self):
        with tempfile.TemporaryDirectory(prefix='wavy-document-fixture-') as tmp:
            archive = Path(tmp)/'fixture.tar'
            cases = [('contrats', 100, tarfile.DIRTYPE, True),
                     ('../escape', 100, tarfile.DIRTYPE, False),
                     ('/contrats', 100, tarfile.DIRTYPE, False),
                     ('contrats', 0, tarfile.DIRTYPE, False),
                     ('contrats', 100, tarfile.SYMTYPE, False)]
            for name, uid, kind, accepted in cases:
                with tarfile.open(archive, 'w') as out:
                    item = tarfile.TarInfo(name)
                    item.uid, item.gid, item.type, item.mode = uid, 101, kind, 0o700
                    out.addfile(item)
                result = subprocess.run(['python3', str(ROOT/'scripts/preprod_document_archive.py'), str(archive)], capture_output=True)
                self.assertEqual(result.returncode == 0, accepted)

    def test_quiesce_failure_resumes_only_attempted_services(self):
        # Test ciblé des commandes futures, sans invoquer le moindre daemon.
        with tempfile.TemporaryDirectory(prefix='wavy-quiesce-fixture-') as tmp:
            log = str(Path(tmp)/'commands')
            shell = r'''
source "$1/scripts/_preprod.sh"
source "$1/scripts/_preprod-documents.sh"
preprod_container_guard() { :; }
docker() {
  printf '%s\n' "$*" >> "$MOCK_LOG"
  if [[ "$1" == stop && "$*" == *socle* ]]; then return 1; fi
  if [[ "$1" == inspect ]]; then echo 0; fi
}
trap preprod_resume EXIT
preprod_quiesce
'''
            result = subprocess.run(['bash','-c',shell,'_',str(ROOT)], env=dict(os.environ,MOCK_LOG=log),capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            calls = Path(log).read_text()
            self.assertIn('start wavy-gateway-preprod', calls)
            self.assertIn('start wavy-socle-api-preprod', calls)
            self.assertNotIn('start wavy-tiers-api-preprod', calls)

    def test_backup_global_lock_and_inherited_descriptor(self):
        # Seulement flock sur un fichier temporaire, aucun backup exécuté.
        with tempfile.TemporaryDirectory(prefix='wavy-operation-lock-') as tmp:
            root = Path(tmp)
            (root/'deployments').mkdir()
            lock = root/'deployments/preprod.lock'
            child = root/'child.sh'
            child.write_text('source "$1/scripts/_preprod.sh"\nROOT_DIR="$2"\npreprod_backup_operation_lock\n')
            command = ['bash', str(child), str(ROOT), tmp]
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
            with lock.open('w') as held:
                fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            parent = '''
exec 9>"$2/deployments/preprod.lock"
flock -n 9 || exit 90
bash "$2/child.sh" "$1" "$2" || exit 91
# Le verrou du parent doit rester actif après la sortie de l’enfant.
flock -n "$2/deployments/preprod.lock" true && exit 92
exit 0
'''
            result = subprocess.run(['bash', '-c', parent, '_', str(ROOT), tmp], capture_output=True)
            self.assertEqual(result.returncode, 0)

    def test_authenticated_manifest(self):
        with tempfile.TemporaryDirectory(prefix='wavy-fake-backup-test-') as tmp:
            path = Path(tmp)
            for db in ('socle','tiers','contrats','factures','tresorerie'):
                (path/(db+'.dump.enc')).write_bytes(b'FICTIONAL TEST DATA, NOT A DATABASE')
            (path/'documents.tar.enc').write_bytes(b'FICTIONAL DOCUMENT ARCHIVE')
            env = dict(os.environ, WAVY_BACKUP_PASSPHRASE='fictional-test-passphrase-0000000000000000')
            def run(action, custom_env=env):
                return subprocess.run(['python3', str(ROOT/'scripts/preprod_backup_manifest.py'), action, tmp], env=custom_env, capture_output=True).returncode
            self.assertEqual(run('sign'), 0)
            self.assertEqual(run('verify'), 0)
            (path/'documents.tar.enc').write_bytes(b'TAMPERED DOCUMENTS')
            self.assertNotEqual(run('verify'), 0)
            self.assertEqual(run('sign'), 0)
            self.assertNotEqual(run('verify', dict(env, WAVY_BACKUP_PASSPHRASE='incorrect-fictional-passphrase')), 0)
            (path/'socle.dump.enc').write_bytes(b'TAMPERED')
            self.assertNotEqual(run('verify'), 0)
            self.assertEqual(run('sign'), 0)
            meta = json.loads((path/'manifest.json').read_text())
            meta['environment'] = 'recette'
            (path/'manifest.json').write_text(json.dumps(meta))
            self.assertNotEqual(run('verify'), 0)


if __name__ == '__main__':
    unittest.main()
