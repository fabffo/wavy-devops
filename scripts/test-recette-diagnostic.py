#!/usr/bin/env python3
"""Diagnostic consolidé : vrai rendu Compose et Git, runtime simulé, aucune donnée active."""
import copy
import fcntl
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.dont_write_bytecode=True
import delivery_check as delivery
import recette_diagnostic as diagnostic
from release_images import recette_compose, release

ROOT=Path(__file__).resolve().parent.parent


class Diagnostic(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        shutil.copytree(ROOT/'versions',self.root/'versions')
        shutil.copytree(ROOT/'docker/recette-pwa',self.root/'docker/recette-pwa')
        shutil.copy(ROOT/'docker-compose.recette.yml',self.root)
        text=(ROOT/'.env.recette.example').read_text().replace('motdepasse_recette','fixture-secret')
        for key,value in {'WAVY_PWA_ENABLED':'true','WAVY_NOTES_WRITES_ENABLED':'true',
                          'WAVY_FACTURES_JUSTIFICATIFS_VOLUME':'fixture-documents',
                          'WAVY_INSTALL_HOSTNAME':socket.gethostname().split('.')[0],
                          'WAVY_TIERS_SERVICE_USERNAME':'fixture-service',
                          'WAVY_TIERS_SERVICE_PASSWORD':'fixture-service-secret'}.items():
            text='\n'.join(key+'='+value if line.startswith(key+'=') else line for line in text.splitlines())+'\n'
        self.machine=self.root/'.env.recette';self.machine.write_text(text);self.machine.chmod(0o600)
        config=recette_compose(self.root,['config','--format','json'],capture=True)
        self.objects={}
        for name,svc in config['services'].items():
            mounts=[{'Type':'volume','Name':config['volumes'][m['source']]['name'],
                     'Destination':m['target'],'RW':True} for m in svc.get('volumes',[]) if m['type']=='volume']
            self.objects[svc['container_name']]={'Name':'/'+svc['container_name'],'Image':'sha256:fixture',
                'State':{'Running':True,'Health':{'Status':'healthy'}},'Mounts':mounts,
                'Config':{'Image':svc['image'],'Env':[k+'='+str(v) for k,v in svc.get('environment',{}).items()],
                          'Labels':{'com.docker.compose.project':'wavy-recette'}}}
        self.git('init','-q');self.git('add','versions','docker','docker-compose.recette.yml')
        self.git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture')
        self.calls=[];self.failures=set();self.volumes='fixture-documents';self.http_failures=set()
        self.patches=[patch.object(diagnostic,'command',side_effect=self.command),
                      patch.object(diagnostic,'storage_permissions'),
                      patch.object(delivery,'request',side_effect=self.request),
                      patch.object(delivery,'cors_runtime',side_effect=self.cors),
                      patch.dict(os.environ,{'DOCKER_HOST':'','DOCKER_CONTEXT':''}),
                      patch.object(Path,'home',return_value=self.root/'operator-home')]
        for item in self.patches:item.start();self.addCleanup(item.stop)

    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.root),*args],stderr=subprocess.STDOUT)

    def command(self,args):
        self.calls.append(args)
        if args[0]=='git':return self.git(*args[3:]).decode().rstrip('\n')
        if any(part in self.failures for part in args):raise ValueError('Lecture simulée indisponible : '+args[1])
        if args[:3]==['docker','context','inspect']:return 'unix:///var/run/docker.sock'
        if args[:2]==['docker','inspect']:
            if args[-1] not in self.objects:raise ValueError('Conteneur absent : '+args[-1])
            return json.dumps([self.objects[args[-1]]])
        if args[:3]==['docker','volume','ls']:return self.volumes
        if args[:3]==['docker','volume','inspect']:return json.dumps([{'Driver':'local','Options':{}}])
        if args[:2]==['docker','info']:return str(self.root) if 'DockerRootDir' in args[-1] else 'fixture-version'
        if args[:2]==['docker','exec']:
            if 'find /app/justificatifs' in args[-1]:
                return 'D\t1\nD\t1/2\nD\t1/2/3\nF\t12\t1/2/3/12345678-1234-1234-1234-123456789abc'
            return '1'
        if args[:3]==['docker','image','inspect']:raise ValueError('Cache fixture absent')
        if args[:3]==['docker','manifest','inspect']:return '{}'
        if args[:3]==['docker','compose','version']:return '2.27.0'
        if args==['docker','compose','up','--help']:return '--wait --wait-timeout --no-build'
        raise AssertionError('Commande inattendue : '+str(args))

    def request(self,origin,path,codes=(200,)):
        if path in self.http_failures:raise ValueError('Échec HTTPS simulé : '+path)
        return b'fixture'

    def cors(self,origin):
        if 'cors' in self.http_failures:raise ValueError('Échec CORS simulé')

    def change(self,key,value):
        text=self.machine.read_text()
        self.machine.write_text('\n'.join(key+'='+value if line.startswith(key+'=') else line for line in text.splitlines())+'\n')

    def run_diagnostic(self,live=True):
        snapshots={str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file() and '.git' not in p.parts}
        result=diagnostic.diagnose(self.root,live=live)
        self.assertEqual(snapshots,{str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file() and '.git' not in p.parts})
        self.assertFalse((self.root/'deployments').exists())
        return result

    def test_historical_socle_local_is_accepted_without_profile_change(self):
        result=self.run_diagnostic()
        self.assertEqual(result['errors'],0,result['checks'])
        self.assertEqual(result['components']['socle-api']['profile'],'local')
        self.assertTrue(any(r['code']=='profile.socle-api' and r['status']=='warning' for r in result['checks']))
        self.assertEqual(len(result['components']),13)
        self.assertEqual(sum(c[:3]==['docker','manifest','inspect'] for c in self.calls),13)

    def test_profile_transition_is_reported_without_rewriting_dotenv(self):
        self.change('WAVY_SOCLE_SPRING_PROFILES_ACTIVE','recette')
        result=self.run_diagnostic()
        self.assertTrue(any(r['code']=='profile.transition' and 'local → recette' in r['message'] for r in result['checks']))

    def test_profile_recette_already_active_is_preserved_and_reverse_transition_refused(self):
        obj=self.objects['wavy-socle-api-recette']
        obj['Config']['Env']=[x.replace('SPRING_PROFILES_ACTIVE=local','SPRING_PROFILES_ACTIVE=recette') for x in obj['Config']['Env']]
        self.change('WAVY_SOCLE_SPRING_PROFILES_ACTIVE','recette')
        self.assertEqual(self.run_diagnostic()['errors'],0)
        self.machine.write_text('\n'.join(line for line in self.machine.read_text().splitlines() if not line.startswith('WAVY_SOCLE_SPRING_PROFILES_ACTIVE='))+'\n')
        result=self.run_diagnostic()
        self.assertTrue(any(r['code']=='profile.transition' and 'recette → local' in r['message'] for r in result['checks']))

    def test_shell_network_change_is_reported_as_unverified_proxy_topology(self):
        self.objects['wavy-erp-shell-recette']['HostConfig']={'PortBindings':{'80/tcp':[{'HostIp':'0.0.0.0'}]}}
        result=self.run_diagnostic()
        self.assertTrue(any(r['code']=='network.proxy' and r['status']=='pending' for r in result['checks']))

    def test_all_configuration_errors_are_reported_in_one_pass(self):
        for key,value in {'WAVY_SOCLE_DB_PASSWORD':'','WAVY_TIERS_SERVICE_USERNAME':'',
                          'WAVY_GATEWAY_SPRING_PROFILES_ACTIVE':'local',
                          'WAVY_TIERS_SPRING_PROFILES_ACTIVE':'dev',
                          'WAVY_NOTES_WRITES_ENABLED':'invalid',
                          'WAVY_INSTALL_WAIT_SECONDS':'bad',
                          'WAVY_FACTURES_JUSTIFICATIFS_VOLUME':'bad/volume'}.items():self.change(key,value)
        with self.machine.open('a') as stream:stream.write('WAVY_PWA_ENABLED=true\n')
        result=self.run_diagnostic(live=False)
        codes={row['code'] for row in result['checks'] if row['status']=='error'}
        self.assertTrue({'dotenv.duplicate','profile.gateway','profile.tiers-api','credentials.socle',
                         'credentials.tiers','WAVY_NOTES_WRITES_ENABLED','wait','storage.name'} <= codes,codes)
        self.assertGreaterEqual(result['errors'],8)

    def test_all_runtime_errors_and_13_registry_checks_are_attempted(self):
        self.objects.pop('wavy-tiers-api-recette');self.objects.pop('wavy-pwa-recette')
        self.objects['wavy-contrats-api-recette']['State']['Running']=False
        self.failures={'pg_restore'};self.http_failures={'/','cors'}
        images=release(self.root,'recette')[2]
        self.failures.update((images['gateway'],images['factures-api']))
        result=self.run_diagnostic()
        codes={r['code'] for r in result['checks'] if r['status']=='error'}
        self.assertTrue({'container.wavy-tiers-api-recette','container.wavy-pwa-recette',
                         'container.running','backup.socle.pg_restore','backup.tresorerie.pg_restore',
                         'https.tls','https.cors','registry.gateway','registry.factures-api'} <= codes,codes)
        self.assertEqual(sum(c[:3]==['docker','manifest','inspect'] for c in self.calls),13)

    def test_future_volume_creation_is_not_an_error_or_a_mutation(self):
        factures=self.objects['wavy-factures-api-recette']
        factures['Config']['Env']=[x for x in factures['Config']['Env'] if not x.startswith('WAVY_FACTURES_STOCKAGE_JUSTIFICATIFS=')]
        factures['Mounts']=[];self.volumes=''
        self.change('WAVY_RECETTE_PROVISION_JUSTIFICATIFS','true')
        result=self.run_diagnostic()
        self.assertEqual(result['errors'],0,result['checks'])
        self.assertTrue(any(r['code']=='storage.create' and r['status']=='planned' for r in result['checks']))
        forbidden={'run','pull','create','stop','start','up','rm','restart','chown','chmod'}
        self.assertFalse(any(set(args[1:3]) & forbidden for args in self.calls if args[-1]!='--help'))

    def test_existing_mounts_and_database_identity_cannot_change(self):
        self.objects['socle-db-recette']['Mounts'][0]['Name']='other-must-preserve'
        self.objects['wavy-factures-api-recette']['Mounts'][0]['RW']=False
        self.objects['tiers-db-recette']['Config']['Env'].append('POSTGRES_PASSWORD=fixture-old-secret')
        result=self.run_diagnostic()
        self.assertGreaterEqual(sum(r['code']=='mounts' and r['status']=='error' for r in result['checks']),2)
        self.assertTrue(any(r['code']=='database.identity' and r['status']=='error' for r in result['checks']))
        self.assertNotIn('fixture-old-secret',json.dumps(result))
        self.assertNotIn('fixture-service-secret',json.dumps(result))

    def test_history_dirty_is_allowed_active_manifest_dirty_is_not(self):
        path=self.root/'versions/history/recette/gateway.tsv'
        with path.open('a') as stream:stream.write('0.1.0-abcdef0\tsha256:'+'a'*64+'\tfixture\t2026-10-28\n')
        self.assertFalse(any(r['code']=='git.dirty' for r in self.run_diagnostic()['checks']))
        path=self.root/'versions/recette.env'
        with path.open('a') as stream:stream.write('\n# fixture unpublished\n')
        self.assertTrue(any(r['code']=='git.dirty' for r in self.run_diagnostic()['checks']))

    def test_remote_docker_override_never_contacts_that_daemon(self):
        with patch.dict(os.environ,{'DOCKER_HOST':'ssh://fixture.invalid'}):
            result=self.run_diagnostic()
        self.assertTrue(any(r['code']=='docker.context' and r['status']=='error' for r in result['checks']))
        self.assertFalse(any(args[0]=='docker' for args in self.calls))

    def test_missing_digests_for_multiple_components_are_all_reported(self):
        path=self.root/'versions/recette.digests'
        path.write_text('\n'.join(line for line in path.read_text().splitlines() if not line.startswith(('GATEWAY_DIGEST=','PWA_DIGEST=')))+'\n')
        result=self.run_diagnostic(live=False)
        codes={r['code'] for r in result['checks'] if r['status']=='error'}
        self.assertTrue({'release.gateway','release.pwa'} <= codes)

    def test_storage_probe_reports_multiple_faults_without_chmod(self):
        from recette_pwa import STORAGE_PROBE
        store=self.root/'probe-store';store.mkdir(mode=0o755);store.chmod(0o755)
        document=store/'fixture';document.write_bytes(b'fixture');document.chmod(0o644)
        before=(store.stat().st_mode,document.stat().st_mode,document.read_bytes())
        result=subprocess.run(['sh','-c',STORAGE_PROBE.replace('root=/app/justificatifs','root='+str(store))],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('storage-error:root-owner-mode',result.stdout)
        self.assertIn('storage-error:file-mode',result.stdout)
        self.assertEqual(before,(store.stat().st_mode,document.stat().st_mode,document.read_bytes()))

    def test_initial_attachment_refuses_dangling_link_and_nonempty_directory(self):
        from recette_pwa import EMPTY_STORAGE_PROBE
        store=self.root/'initial-store'
        script=EMPTY_STORAGE_PROBE.replace('/app/justificatifs',str(store))
        store.symlink_to(self.root/'absent-target')
        self.assertNotEqual(subprocess.run(['sh','-ec',script],capture_output=True).returncode,0)
        self.assertTrue(store.is_symlink());store.unlink()
        store.mkdir();document=store/'fixture';document.write_bytes(b'fixture')
        self.assertNotEqual(subprocess.run(['sh','-ec',script],capture_output=True).returncode,0)
        self.assertEqual(document.read_bytes(),b'fixture')

    def test_valid_cache_does_not_require_registry_access(self):
        original=self.command
        def cached(args):
            if args[:3]==['docker','image','inspect']:
                self.calls.append(args)
                repo,digest=args[-1].split('@')
                return json.dumps([{'RepoDigests':[repo.rsplit(':',1)[0]+'@'+digest]}])
            return original(args)
        with patch.object(diagnostic,'command',side_effect=cached):
            result=self.run_diagnostic()
        self.assertEqual(result['errors'],0,result['checks'])
        self.assertFalse(any(args[:3]==['docker','manifest','inspect'] for args in self.calls))

    def test_document_layout_failures_are_found_before_any_backup(self):
        original=self.command
        def invalid_layout(args):
            if args[:2]==['docker','exec'] and 'find /app/justificatifs' in args[-1]:
                self.calls.append(args)
                return 'D\tinvalid-company\nF\t0\t1/2/3/invalid-uuid'
            return original(args)
        with patch.object(diagnostic,'command',side_effect=invalid_layout):
            result=self.run_diagnostic()
        self.assertEqual(sum(r['code']=='backup.layout' and r['status']=='error' for r in result['checks']),2)
        self.assertFalse(any('pg_dump' in args and '--version' not in args for args in self.calls))
        self.assertNotIn('invalid-company',json.dumps(result))

    def test_actual_metadata_shell_probe_accepts_private_fixture_without_change(self):
        store=self.root/'layout-fixture'; directory=store/'1/2/3';directory.mkdir(parents=True)
        document=directory/'12345678-1234-1234-1234-123456789abc';document.write_bytes(b'fixture')
        def probe(args):
            self.assertEqual(args[:4],['docker','exec','wavy-factures-api-recette','sh'])
            return subprocess.check_output(['sh','-ec',args[-1].replace('/app/justificatifs',str(store))],text=True).rstrip('\n')
        report=diagnostic.Report()
        with patch.object(diagnostic,'command',side_effect=probe):diagnostic.document_layout(report)
        self.assertEqual(report.rows,[])
        self.assertEqual(document.read_bytes(),b'fixture')

    def test_missing_compose_flags_and_tar_are_reported_before_backup(self):
        original=self.command
        def missing_capabilities(args):
            if args==['docker','compose','up','--help']:return '--wait --no-build'
            if args[-1]=='command -v tar >/dev/null':raise ValueError('tar indisponible')
            return original(args)
        with patch.object(diagnostic,'command',side_effect=missing_capabilities):result=self.run_diagnostic()
        self.assertTrue(any(r['code']=='docker.compose.capabilities' and '--wait-timeout' in r['message'] for r in result['checks']))
        self.assertTrue(any(r['code']=='backup.tar' and r['status']=='error' for r in result['checks']))

    def test_quoted_settings_match_shell_and_preserve_internal_secret_quotes(self):
        self.change('WAVY_INSTALL_HOSTNAME',"'"+socket.gethostname().split('.')[0]+"'")
        self.change('COMPOSE_PROJECT_NAME',"'wavy-recette'")
        self.change('WAVY_TIERS_SERVICE_PASSWORD','"fixture\'secret"')
        result=self.run_diagnostic(live=False)
        self.assertFalse(any(r['code'] in ('host','dotenv') and r['status']=='error' for r in result['checks']))
        shell='source "$1"; ROOT_DIR="$2"; env_value recette WAVY_INSTALL_HOSTNAME ""'
        output=subprocess.check_output(['bash','-c',shell,'_',str(ROOT/'scripts/_common.sh'),str(self.root)],text=True)
        self.assertEqual(output.strip(),socket.gethostname().split('.')[0])


if __name__=='__main__':unittest.main()
