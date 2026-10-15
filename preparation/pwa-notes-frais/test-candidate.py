#!/usr/bin/env python3
"""Tests locaux isolés du candidat, sans image pull, VM, déploiement ou base."""
import importlib.util,json,os,re,subprocess,tarfile,tempfile,unittest,io,shutil,hashlib,sys
sys.dont_write_bytecode=True
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];C=Path(__file__).resolve().parent

def load(path):
    spec=importlib.util.spec_from_file_location('candidate_'+path.stem,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
class Candidate(unittest.TestCase):
    def test_active_manifests_unchanged(self):
        protected=['versions','docker-compose.preprod.yml','docker-compose.recette.yml']
        subprocess.run(['git','diff','--exit-code','--',*protected],cwd=ROOT,check=True,capture_output=True)
    def test_patch_applies_only_in_isolated_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);(tmp/'scripts').mkdir()
            names=['preprod_document_archive.py','backup-preprod.sh','restore-preprod.sh','preprod_config.py']
            for name in names:shutil.copy(ROOT/'scripts'/name,tmp/'scripts'/name)
            subprocess.run(['patch','--batch','-p1','-i',str(C/'integration-scripts.patch')],cwd=tmp,check=True,capture_output=True)
            for name in names:self.assertEqual((tmp/'scripts'/name).read_bytes(),(C/'scripts'/name).read_bytes())
    def archive(self,path,root='notes-frais',kind=tarfile.REGTYPE):
        with tarfile.open(path,'w') as archive:
            for name in ['contrats',root]:
                e=tarfile.TarInfo(name);e.type=tarfile.DIRTYPE;e.uid=100;e.gid=101;e.mode=0o700;archive.addfile(e)
            e=tarfile.TarInfo(root+'/1/2/3/document');e.uid=100;e.gid=101;e.mode=0o600;e.type=kind;e.linkname='/etc/passwd';content=b'original-fixture';e.size=len(content) if kind==tarfile.REGTYPE else 0
            archive.addfile(e,io.BytesIO(content) if e.size else None)
    def test_encrypted_backup_restore_and_manifest(self):
        validator=load(C/'scripts/preprod_document_archive.py');manifest=load(ROOT/'scripts/preprod_backup_manifest.py')
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);tar=folder/'original.tar';self.archive(tar);validator.validate(str(tar))
            env=dict(os.environ,WAVY_BACKUP_PASSPHRASE='fictional-test-only-passphrase-000000000000000')
            encrypted=folder/'documents.tar.enc'
            subprocess.run(['openssl','enc','-aes-256-cbc','-salt','-pbkdf2','-pass','env:WAVY_BACKUP_PASSPHRASE','-in',str(tar),'-out',str(encrypted)],env=env,check=True,capture_output=True)
            for db in manifest.DATABASES:(folder/(db+'.dump.enc')).write_bytes(b'fictional-db-fixture-only')
            subprocess.run(['python3',str(ROOT/'scripts/preprod_backup_manifest.py'),'sign',str(folder)],env=env,check=True)
            subprocess.run(['python3',str(ROOT/'scripts/preprod_backup_manifest.py'),'verify',str(folder)],env=env,check=True)
            restored=folder/'restored.tar';subprocess.run(['openssl','enc','-d','-aes-256-cbc','-pbkdf2','-pass','env:WAVY_BACKUP_PASSPHRASE','-in',str(encrypted),'-out',str(restored)],env=env,check=True,capture_output=True)
            validator.validate(str(restored));out=folder/'restore';out.mkdir()
            with tarfile.open(restored) as archive:archive.extractall(out,filter='data')
            self.assertEqual((out/'notes-frais/1/2/3/document').read_bytes(),b'original-fixture')
            encrypted.write_bytes(b'corrupted');r=subprocess.run(['python3',str(ROOT/'scripts/preprod_backup_manifest.py'),'verify',str(folder)],env=env,capture_output=True);self.assertNotEqual(r.returncode,0)
    def test_reject_unsafe_archives(self):
        validator=load(C/'scripts/preprod_document_archive.py')
        with tempfile.TemporaryDirectory() as temp:
            for root,kind in [('../escape',tarfile.REGTYPE),('other',tarfile.REGTYPE),('notes-frais',tarfile.SYMTYPE)]:
                path=Path(temp)/'invalid.tar';self.archive(path,root,kind)
                with self.assertRaises(ValueError):validator.validate(str(path))
    def test_old_contract_archive_remains_restorable(self):
        validator=load(C/'scripts/preprod_document_archive.py')
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'old.tar'
            with tarfile.open(path,'w') as archive:
                e=tarfile.TarInfo('contrats');e.type=tarfile.DIRTYPE;e.uid=100;e.gid=101;archive.addfile(e)
            validator.validate(str(path))
    def test_compose_candidate_with_fictional_values(self):
        tests=load(ROOT/'scripts/test-preprod-config.py');config=tests.config
        with tempfile.TemporaryDirectory() as temp:
            envfile=Path(temp)/'fiction.env';envfile.write_text(tests.fixture());envfile.chmod(0o600)
            with envfile.open('a') as f:f.write('WAVY_PWA_CANDIDATE_DIR='+str(C)+'\n')
            for key in ('FACTURES_API','PWA','FACTURES_FRONT','ERP_SHELL'):
                with envfile.open('a') as f:f.write(f'PWA_RELEASE_{key}_IMAGE=ghcr.io/fabffo/wavy-{key.lower().replace("_","-")}@sha256:'+('a'*64)+'\n')
            cmd,env=config.compose_args(envfile,['-f',str(C/'compose.override.yml'),'config','--format','json'])
            rendered=subprocess.run(cmd,env=env,capture_output=True,check=True);services=json.loads(rendered.stdout)['services']
            for key in ('factures-api','pwa','factures-front','erp-shell'):self.assertRegex(services['wavy-'+key+'-preprod']['image'],r'@sha256:[a-f0-9]{64}$')
            mount=services['wavy-factures-api-preprod']['volumes'][0];self.assertEqual(mount['volume']['subpath'],'notes-frais')
            self.assertEqual(services['wavy-factures-api-preprod']['environment']['WAVY_FACTURES_STOCKAGE_JUSTIFICATIFS'],'/app/justificatifs')
            self.assertIn('wavy-pwa-preprod',services['wavy-erp-shell-preprod']['depends_on'])
            self.assertTrue(all(Path(m['source']).is_file() for m in services['wavy-erp-shell-preprod']['volumes'] if m['type']=='bind'))
    def test_feature_disabled_without_candidate(self):
        self.assertFalse(json.loads((ROOT.parent/'wavy-erp-shell/public/pwa-integration.json').read_text())['enabled'])
        self.assertIn('return 404',(ROOT.parent/'wavy-erp-shell/nginx-pwa-disabled.conf').read_text())
    def test_bundle_refuses_missing_or_mutable_images(self):
        tool=load(C/'validate-bundle.py')
        with self.assertRaises(ValueError):tool.validate(json.loads((C/'release-plan.json').read_text()))
        data=json.loads((C/'release-plan.json').read_text());data['images']={c:{'version':'0.1.0-abcdef0','digest':'sha256:'+'a'*64} for c in data['components']};tool.validate(data)
        data['images']['pwa']['digest']='sha256:short'
        with self.assertRaises(ValueError):tool.validate(data)
if __name__=='__main__':unittest.main()
