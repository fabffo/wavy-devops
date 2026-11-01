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
        self.assertTrue(any(r['code']=='network.proxy' and r['status']=='warning' for r in result['checks']))

    def test_all_configuration_errors_are_reported_in_one_pass(self):
        for key,value in {'WAVY_SOCLE_DB_PASSWORD':'','WAVY_TIERS_SERVICE_USERNAME':'',
                          'WAVY_GATEWAY_SPRING_PROFILES_ACTIVE':'local',
                          'WAVY_TIERS_SPRING_PROFILES_ACTIVE':'dev',
                          'WAVY_NOTES_WRITES_ENABLED':'invalid',
                          'WAVY_INSTALL_WAIT_SECONDS':'bad',
                          'WAVY_FACTURES_JUSTIFICATIFS_VOLUME':'bad/volume'}.items():self.change(key,value)
        with self.machine.open('a') as stream:stream.write('WAVY_PWA_ENABLED=false\n')
        result=self.run_diagnostic(live=False)
        codes={row['code'] for row in result['checks'] if row['status']=='error'}
        self.assertTrue({'dotenv.duplicate','profile.gateway','profile.tiers-api',
                         'credentials.tiers','WAVY_NOTES_WRITES_ENABLED','wait','storage.name'} <= codes,codes)
        self.assertGreaterEqual(result['errors'],7)
        self.assertTrue(any(r['code']=='credentials.socle' and r['category']=='AVERTISSEMENT' for r in result['checks']))

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
                         'registry.gateway','registry.factures-api'} <= codes,codes)
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

    def test_tiers_local_already_active_is_warning_and_profile_is_preserved(self):
        self.change('WAVY_TIERS_SPRING_PROFILES_ACTIVE','local')
        obj=self.objects['wavy-tiers-api-recette']
        obj['Config']['Env']=[x.replace('SPRING_PROFILES_ACTIVE=recette','SPRING_PROFILES_ACTIVE=local') for x in obj['Config']['Env']]
        result=self.run_diagnostic()
        self.assertEqual(result['errors'],0,result['checks'])
        self.assertTrue(any(r['code']=='profile.tiers-api' and r['category']=='AVERTISSEMENT' for r in result['checks']))
        self.assertEqual(delivery.check_recette(self.root)[0]['mode'],'technical')

    def test_five_omitted_database_passwords_use_matching_rendered_legacy_values(self):
        keys={'WAVY_'+db.upper()+'_DB_PASSWORD' for db in diagnostic.DATABASES}
        self.machine.write_text('\n'.join(line for line in self.machine.read_text().splitlines() if line.split('=',1)[0] not in keys)+'\n')
        for obj in self.objects.values():
            obj['Config']['Env']=[key+'=motdepasse_recette' if key.endswith('PASSWORD') and key!='WAVY_TIERS_SERVICE_PASSWORD' else entry
                                  for entry in obj['Config']['Env'] for key in [entry.split('=',1)[0]]]
        result=self.run_diagnostic()
        self.assertEqual(result['errors'],0,result['checks'])
        self.assertEqual(sum(r['category']=='AVERTISSEMENT' and r['code'].startswith('credentials.') for r in result['checks']),5)
        delivery.check_recette(self.root)  # Aucune seconde barrière sur les placeholders historiques.
        self.objects['socle-db-recette']['Config']['Env'].append('POSTGRES_PASSWORD=actually-different-fixture')
        blocked=self.run_diagnostic()
        self.assertTrue(any(r['code']=='database.identity' and r['category']=='BLOQUANT' for r in blocked['checks']))

    def test_https_from_vm_unavailable_does_not_turn_into_an_application_failure(self):
        self.http_failures={'/','/api/auth/session','cors'}
        result=self.run_diagnostic()
        self.assertEqual(result['errors'],0,result['checks'])
        self.assertEqual(result['decision'],'GO avec avertissements')
        checks=[r for r in result['checks'] if r['code'].startswith('https.') and r['status']=='warning']
        self.assertEqual(len(checks),3)
        self.assertTrue(all(r['category']=='AVERTISSEMENT' and r['evidence']=='NON_VERIFIE' for r in checks))
        self.assertTrue(any(r['code']=='execution' and r['category']=='INFORMATION' for r in result['checks']))

    def test_shell_for_caddy_windows_is_external_but_all_backends_stay_private(self):
        config=recette_compose(self.root,['config','--format','json'],capture=True)
        self.assertEqual(config['services']['wavy-erp-shell-recette']['ports'][0]['host_ip'],'0.0.0.0')
        self.assertTrue(all(p['host_ip']=='127.0.0.1' for name,svc in config['services'].items() if name!='wavy-erp-shell-recette' for p in svc.get('ports',[])))
        config['services']['wavy-factures-api-recette']['ports'][0]['host_ip']='0.0.0.0'
        with self.assertRaisesRegex(ValueError,'backend publié'):delivery.rendered_checks(config,'recette',release(self.root,'recette')[2])

    def test_internal_routes_remain_blocking_when_public_https_is_not_reachable(self):
        from io import StringIO
        from urllib.error import URLError
        from contextlib import redirect_stdout
        images=release(self.root,'recette')[2]
        state=delivery.check_recette(self.root)[0]
        calls=[]
        def fetch(base,path,codes=(200,)):
            calls.append((base,path))
            if base.startswith('https:'): raise URLError('fixture Caddy inaccessible depuis VM')
            return b'{"enabled":true}' if path=='/pwa-integration.json' else b'fixture-content'
        def cors(origin,base=None):
            if base is None: raise URLError('fixture Caddy inaccessible depuis VM')
        def inspect(args):return json.dumps([self.objects[args[-1]]]).encode()
        with patch.object(delivery,'check_recette',return_value=(state,images)), patch.object(delivery,'runtime_check'), \
             patch.object(delivery.subprocess,'check_output',side_effect=inspect), patch.object(delivery,'request',side_effect=fetch), \
             patch.object(delivery,'cors_runtime',side_effect=cors):
            output=StringIO()
            with redirect_stdout(output):delivery.runtime(self.root)
            report=json.loads(output.getvalue())
            self.assertEqual(report['errors'],0)
            self.assertEqual(report['warnings'],2)
            self.assertTrue(any(base=='http://127.0.0.1:24207' and path=='/pwa/' for base,path in calls))
            with patch.object(delivery,'request',side_effect=ValueError('Route interne indisponible')):
                with self.assertRaisesRegex(ValueError,'Route interne'):delivery.runtime(self.root)
            def unsafe_public_cors(origin,base=None):
                if base is None:raise delivery.UnsafeCorsError('CORS : origine globale observée')
            with patch.object(delivery,'cors_runtime',side_effect=unsafe_public_cors), redirect_stdout(StringIO()):
                with self.assertRaisesRegex(ValueError,'Non-conformité de sécurité'):delivery.runtime(self.root)

    def test_identical_duplicates_and_unused_legacy_cors_are_advisory(self):
        with self.machine.open('a') as stream:
            stream.write('WAVY_PWA_ENABLED=true\nWAVY_GATEWAY_CORS_ALLOWED_ORIGIN_PATTERNS=https://unused.invalid\n')
        result=self.run_diagnostic()
        self.assertEqual(result['errors'],0,result['checks'])
        self.assertTrue(any(r['code']=='dotenv.duplicate' and r['category']=='AVERTISSEMENT' for r in result['checks']))
        self.assertTrue(any(r['code']=='dotenv.legacy' and r['category']=='AVERTISSEMENT' for r in result['checks']))
        delivery.check_recette(self.root)

    def test_low_space_or_unreadable_measurement_warns_but_full_disk_blocks(self):
        from types import SimpleNamespace
        low=SimpleNamespace(f_bavail=512000,f_frsize=1024)
        full=SimpleNamespace(f_bavail=0,f_frsize=1024)
        with patch.object(diagnostic.os,'statvfs',return_value=low):result=self.run_diagnostic()
        self.assertEqual(result['errors'],0,result['checks'])
        self.assertTrue(any(r['code']=='disk' and r['category']=='AVERTISSEMENT' for r in result['checks']))
        with patch.object(diagnostic.os,'statvfs',side_effect=PermissionError()):result=self.run_diagnostic()
        self.assertEqual(result['errors'],0,result['checks'])
        with patch.object(diagnostic.os,'statvfs',return_value=full):result=self.run_diagnostic()
        self.assertTrue(any(r['code']=='disk.full' and r['category']=='BLOQUANT' for r in result['checks']))

    def test_stopped_static_front_is_information_not_a_backup_requirement(self):
        self.objects['wavy-pwa-recette']['State']['Running']=False
        result=self.run_diagnostic()
        self.assertEqual(result['errors'],0,result['checks'])
        self.assertTrue(any(r['code']=='container.running' and r['category']=='INFORMATION' for r in result['checks']))
        state,images=delivery.check_recette(self.root)
        with patch.object(delivery,'check_recette',return_value=(state,images)), patch.object(delivery,'preserve_storage'), \
             patch.object(delivery.subprocess,'check_output',return_value=json.dumps(list(self.objects.values())).encode()):
            delivery.preflight(self.root)

    def test_storage_capacity_probe_keeps_only_full_volume_blocking(self):
        from recette_pwa import STORAGE_PROBE
        store=self.root/'capacity-fixture';store.mkdir(mode=0o700);store.chmod(0o700)
        binary=self.root/'capacity-bin';binary.mkdir();df=binary/'df'
        env=dict(os.environ,PATH=str(binary)+':'+os.environ['PATH'])
        script=STORAGE_PROBE.replace('root=/app/justificatifs','root='+str(store))
        for available in (512000,0):
            df.write_text('#!/bin/sh\nprintf "Filesystem 1K-blocks Used Available Use%% Mounted\nfixture 1000000 0 '+str(available)+' 0%% /fixture\n"\n');df.chmod(0o700)
            result=subprocess.run(['sh','-c',script],env=env,capture_output=True,text=True)
            self.assertEqual('storage-error:capacity' in result.stdout,available==0)

    def test_observed_unsafe_public_cors_is_still_blocking(self):
        with patch.object(delivery,'cors_runtime',side_effect=delivery.UnsafeCorsError('CORS : origine globale observée')):
            result=self.run_diagnostic()
        self.assertTrue(any(r['code']=='security.cors' and r['category']=='BLOQUANT' and r['evidence']=='ECART_OBSERVE' for r in result['checks']))

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
