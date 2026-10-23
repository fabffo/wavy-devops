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
    def test_historical_patch_remains_readable_and_not_executed(self):
        patch=(C/'integration-scripts.patch').read_text()
        self.assertIn('--- a/scripts/backup-preprod.sh',patch)
        runtime=(C/'scripts/release_pwa_preprod.py').read_text()
        self.assertNotIn('integration-scripts.patch',runtime)
        # Le validateur actif accepte maintenant les deux racines, y compris le format Contrats seul.
        active=load(ROOT/'scripts/preprod_document_archive.py')
        with tempfile.TemporaryDirectory() as tmp:
            archive=Path(tmp)/'fixture.tar';self.archive(archive);active.validate(str(archive))
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
        plan=json.loads((C/'release-plan.json').read_text())
        with tempfile.TemporaryDirectory() as temp:
            envfile=Path(temp)/'fiction.env';envfile.write_text(tests.fixture());envfile.chmod(0o600)
            cmd,env=config.compose_args(envfile,['config','--format','json'])
            baseline=json.loads(subprocess.run(cmd,env=env,capture_output=True,check=True).stdout)['services']
            for real_refs in (False,True):
                envfile.write_text(tests.fixture()+'WAVY_PWA_CANDIDATE_DIR='+str(C)+'\n')
                for key in ('FACTURES_API','PWA','FACTURES_FRONT','ERP_SHELL'):
                    component=key.lower().replace('_','-')
                    ref=plan['images'][component]['reference'] if real_refs else f'ghcr.io/fabffo/wavy-{component}@sha256:'+('a'*64)
                    with envfile.open('a') as f:f.write(f'PWA_RELEASE_{key}_IMAGE={ref}\n')
                cmd,env=config.compose_args(envfile,['-f',str(C/'compose.override.yml'),'config','--format','json'])
                rendered=subprocess.run(cmd,env=env,capture_output=True,check=True);services=json.loads(rendered.stdout)['services']
                for key in ('factures-api','pwa','factures-front','erp-shell'):
                    ref=services['wavy-'+key+'-preprod']['image']
                    self.assertRegex(ref,r'@sha256:[a-f0-9]{64}$')
                    if real_refs:self.assertEqual(ref,plan['images'][key]['reference'])
                changed={'wavy-'+key+'-preprod' for key in plan['components']}
                self.assertEqual({k:v for k,v in baseline.items() if k not in changed},
                                 {k:v for k,v in services.items() if k not in changed})
                mount=services['wavy-factures-api-preprod']['volumes'][0]
                self.assertEqual(mount['volume']['subpath'],'notes-frais')
                self.assertFalse(mount.get('read_only',False))
                self.assertEqual(services['wavy-factures-api-preprod']['environment']['WAVY_FACTURES_STOCKAGE_JUSTIFICATIFS'],'/app/justificatifs')
                shell=services['wavy-erp-shell-preprod']
                for component in ('factures-api','factures-front','pwa'):
                    self.assertEqual(shell['depends_on']['wavy-'+component+'-preprod']['condition'],'service_healthy')
                mounts={m['target']:m for m in shell['volumes'] if m['type']=='bind'}
                self.assertEqual(Path(mounts['/etc/nginx/pwa-route.conf']['source']).name,'nginx-pwa-disabled.conf')
                self.assertFalse(json.loads(Path(mounts['/usr/share/nginx/html/pwa-integration.json']['source']).read_text())['enabled'])
                self.assertTrue(all(Path(m['source']).is_file() and m['read_only'] for m in mounts.values()))
    def test_feature_disabled_without_candidate(self):
        self.assertFalse(json.loads((ROOT.parent/'wavy-erp-shell/public/pwa-integration.json').read_text())['enabled'])
        self.assertIn('return 404',(ROOT.parent/'wavy-erp-shell/nginx-pwa-disabled.conf').read_text())
    def test_bundle_refuses_missing_or_mutable_images(self):
        import copy
        tool=load(C/'validate-bundle.py')
        data=json.loads((C/'release-plan.json').read_text())
        self.assertTrue(tool.validate(data))
        mutations=[lambda d: d['images'].pop('pwa'),
                   lambda d: d['images']['pwa'].update(digest='sha256:short'),
                   lambda d: d['images']['pwa'].update(reference='ghcr.io/fabffo/wavy-pwa:latest'),
                   lambda d: d['images']['pwa']['ociLabels'].update({'org.opencontainers.image.revision':'abcdef0'}),
                   lambda d: d['images']['pwa']['ociLabels'].update({'org.opencontainers.image.source':'wrong'}),
                   lambda d: d['images']['pwa']['ociLabels'].update({'org.opencontainers.image.version':'9.9.9'}),
                   lambda d: d['images']['pwa'].update(platform='linux/arm64'),
                   lambda d: d.update(pwaEnabledByDefault=True),
                   lambda d: d.update(deploymentOrder=list(reversed(d['deploymentOrder'])))]
        for mutate in mutations:
            candidate=copy.deepcopy(data);mutate(candidate)
            with self.assertRaises(ValueError):tool.validate(candidate)

    def test_candidate_stays_closed(self):
        self.assertFalse(json.loads((C/'pwa-integration.disabled.json').read_text())['enabled'])
        self.assertIn('location = /pwa { return 404; }',(C/'nginx-pwa-disabled.conf').read_text())
        self.assertIn('location /pwa/ { return 404; }',(C/'nginx-pwa-disabled.conf').read_text())
        override=(C/'compose.override.yml').read_text()
        self.assertNotIn('/nginx-pwa-enabled.conf',override)
        self.assertNotIn('/pwa-integration.enabled.json',override)

if __name__=='__main__':unittest.main()
