#!/usr/bin/env python3
"""Politique et rendu réel Compose, sans données ni service Wavy actif."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.dont_write_bytecode = True
import recette_pwa as pwa
import release_images as images
ROOT = Path(__file__).resolve().parent.parent


class RecettePwa(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT/'versions', self.root/'versions')
        shutil.copytree(ROOT/'docker/recette-pwa', self.root/'docker/recette-pwa')
        shutil.copy(ROOT/'docker-compose.recette.yml', self.root)
        (self.root/'.env.recette').write_text((ROOT/'.env.recette.example').read_text())
        _, _, self.images = images.release(self.root, 'recette')
        self.machine = {'WAVY_PWA_ENABLED': 'false', 'WAVY_NOTES_WRITES_ENABLED': 'false'}

    def approve(self, writes=False):
        self.machine.update(WAVY_PWA_ENABLED='true', WAVY_NOTES_WRITES_ENABLED=str(writes).lower(),
            WAVY_PWA_QUALIFICATION_FILE='qualification.private.json', WAVY_FACTURES_JUSTIFICATIFS_VOLUME='existing-private-documents')
        self.proof = {'environment': 'recette', 'origin': 'https://recette.wavyservices.fr', 'approved': True,
            'reviewer': 'test-fixture-only', 'backup':{'manifestSha256':'a'*64,'restoredManifestSha256':'a'*64}, 'images': {c:self.images[c] for c in pwa.COMPONENTS},
            'storageVolume': 'existing-private-documents', 'checks': {c:True for c in pwa.READ_CHECKS+pwa.WRITE_CHECKS}}
        self.save()

    def save(self):
        path = self.root/'qualification.private.json'
        path.write_text(json.dumps(self.proof)); path.chmod(0o600)

    def test_default_is_closed_and_has_no_new_storage(self):
        result = pwa.overlay(self.root, {}, self.images)
        shell = result['services']['wavy-erp-shell-recette']
        self.assertTrue(all(m['read_only'] and not m['bind']['create_host_path'] for m in shell['volumes']))
        self.assertIn('routes-closed.conf', str(shell))
        self.assertIn('notes-read.conf', str(shell))
        self.assertNotIn('volumes', result)
        self.assertEqual(set(result['services']), {'wavy-erp-shell-recette'})

    def test_enabling_without_proof_fails_before_any_docker_call(self):
        with patch.object(pwa.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'NO-GO'):
                pwa.overlay(self.root, {'WAVY_PWA_ENABLED':'true'}, self.images, mutation=True)
            run.assert_not_called()

    def test_visibility_does_not_enable_writes_and_never_expires(self):
        self.approve()
        self.proof['checkedAt'] = '2020-01-01T00:00:00Z'; self.save()
        for _ in range(2):
            result = pwa.overlay(self.root, self.machine, self.images)
            self.assertIn('routes-open.conf', str(result))
            self.assertIn('notes-read.conf', str(result))
            self.assertEqual(result['volumes']['recette-justificatifs'], {'name':'existing-private-documents', 'external':True})

    def test_closing_pwa_does_not_detach_or_change_document_volume(self):
        self.approve()
        opened = pwa.overlay(self.root, self.machine, self.images)
        self.machine['WAVY_PWA_ENABLED'] = 'false'
        closed = pwa.overlay(self.root, self.machine, self.images)
        self.assertEqual(opened['volumes'], closed['volumes'])
        self.assertEqual(opened['services']['wavy-factures-api-recette'], closed['services']['wavy-factures-api-recette'])

    def test_missing_storage_setting_cannot_detach_an_existing_store(self):
        existing = {'Config': {'Env': ['WAVY_FACTURES_STOCKAGE_JUSTIFICATIFS=/app/justificatifs']},
                    'Mounts': [{'Destination':'/app/justificatifs','Type':'volume','Name':'must-preserve'}]}
        with patch.object(pwa.subprocess,'run',return_value=subprocess.CompletedProcess([],0,json.dumps([existing]))):
            with self.assertRaisesRegex(ValueError,'préserver le stockage existant'):
                pwa.overlay(self.root,self.machine,self.images,mutation=True)

    def test_notes_policy_is_independent_of_ui_visibility(self):
        self.approve(writes=True)
        self.machine['WAVY_PWA_ENABLED'] = 'false'
        result = pwa.overlay(self.root, self.machine, self.images)
        self.assertIn('routes-closed.conf', str(result)); self.assertIn('notes-write.conf', str(result))

    def test_each_missing_check_keeps_closed(self):
        self.approve(writes=True)
        for check in pwa.READ_CHECKS+pwa.WRITE_CHECKS:
            self.proof['checks'][check] = False; self.save()
            with self.subTest(check=check), self.assertRaisesRegex(ValueError, check):
                pwa.overlay(self.root, self.machine, self.images)
            self.proof['checks'][check] = True

    def test_foreign_environment_origin_images_volume_or_permissions_refused(self):
        self.approve()
        valid = copy.deepcopy(self.proof)
        for key, value in (('environment','preprod'), ('origin','https://other.invalid'), ('images',{}), ('storageVolume','other'), ('approved',False)):
            self.proof = copy.deepcopy(valid); self.proof[key] = value; self.save()
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'NO-GO'):
                pwa.overlay(self.root, self.machine, self.images)
        self.proof = valid; self.save(); (self.root/'qualification.private.json').chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'permissions'):
            pwa.overlay(self.root, self.machine, self.images)

    def test_custom_environment_origin_is_not_overwritten(self):
        self.approve()
        self.machine['WAVY_PWA_PUBLIC_ORIGIN'] = 'https://recette-specific.example.test'
        self.machine['WAVY_CORS_ALLOWED_ORIGIN_PATTERNS'] = self.machine['WAVY_PWA_PUBLIC_ORIGIN']
        self.proof['origin'] = self.machine['WAVY_PWA_PUBLIC_ORIGIN']; self.save()
        result = pwa.overlay(self.root, self.machine, self.images)
        self.assertEqual(result['services']['wavy-erp-shell-recette']['environment']['WAVY_PWA_PUBLIC_ORIGIN'], self.proof['origin'])

    def test_restore_attestation_must_match_the_backup_manifest(self):
        self.approve()
        self.proof['backup']['restoredManifestSha256']='b'*64;self.save()
        with self.assertRaisesRegex(ValueError,'restauration non liés'):
            pwa.overlay(self.root,self.machine,self.images)

    def test_inconsistent_api_cors_keeps_activation_closed(self):
        self.approve()
        self.machine['WAVY_CORS_ALLOWED_ORIGIN_PATTERNS'] = 'https://other.invalid'
        with self.assertRaisesRegex(ValueError,'liste CORS exacte'):
            pwa.overlay(self.root,self.machine,self.images)

    def test_nginx_injection_and_invalid_flags_refused(self):
        for origin in ('http://recette.wavyservices.fr', 'https://a/extra', 'https://a;return 200;', 'https://a"', 'https://a#x'):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                pwa.policy(self.root, {'WAVY_PWA_PUBLIC_ORIGIN':origin}, self.images)
        with self.assertRaises(ValueError): pwa.policy(self.root, {'WAVY_PWA_ENABLED':'yes'}, self.images)

    def test_runtime_unhealthy_or_missing_fails_without_mutation(self):
        self.approve()
        with patch.object(pwa.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'No such container')) as run:
            with self.assertRaisesRegex(ValueError, 'prérequis runtime absent'):
                pwa.overlay(self.root, self.machine, self.images, mutation=True)
            self.assertEqual(run.call_args.args[0][:2], ['docker','inspect'])

    def test_qualified_runtime_uses_only_inspection_and_keeps_storage(self):
        self.approve(writes=True)
        calls = []
        def inspect(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:2] == ['docker','exec']:
                return subprocess.CompletedProcess(cmd,0,'private-storage-ok\n')
            if cmd[:2] == ['docker','inspect'] and len(cmd)>3:
                return subprocess.CompletedProcess(cmd,0,json.dumps([{'Name':'/'+name,'HostConfig':{'PortBindings':{}}} for name in cmd[2:]]))
            if cmd[:3] == ['docker','image','inspect']:
                repository,digest = self.images[cmd[-1]].split('@')
                return subprocess.CompletedProcess(cmd,0,json.dumps([{'RepoDigests':[repository.rsplit(':',1)[0]+'@'+digest]}]))
            component = cmd[-1][len('wavy-'):-len('-recette')]
            obj = {'Image':component,'State':{'Running':True,'Health':{'Status':'healthy'}},
                   'Config':{'Env':[]},'Mounts':[]}
            if component == 'factures-api':
                obj['Config']['Env']=['WAVY_FACTURES_STOCKAGE_JUSTIFICATIFS=/app/justificatifs']
                obj['Mounts']=[{'Destination':'/app/justificatifs','Type':'volume','Name':'existing-private-documents','RW':True}]
            return subprocess.CompletedProcess(cmd,0,json.dumps([obj]))
        with patch.object(pwa.subprocess,'run',side_effect=inspect):
            result = pwa.overlay(self.root,self.machine,self.images,mutation=True)
        self.assertTrue(result['volumes']['recette-justificatifs']['external'])
        self.assertTrue(all(c[:2]==['docker','inspect'] or c[:3]==['docker','image','inspect'] or c[:2]==['docker','exec'] for c in calls))

    def test_direct_ports_and_storage_fail_closed(self):
        with patch.object(pwa.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'')):
            with self.assertRaisesRegex(ValueError,'Stockage privé'):
                pwa.storage_permissions()
        def inspect(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd,0,json.dumps([{'Name':'/'+name,'HostConfig':{'PortBindings':{'8080/tcp':[{'HostIp':'0.0.0.0'}]}}} for name in cmd[2:]]))
        with patch.object(pwa.subprocess,'run',side_effect=inspect):
            with self.assertRaisesRegex(ValueError,'hors loopback'): pwa.direct_ports()

    def test_plan_and_default_diagnostic_never_call_docker(self):
        with patch.object(pwa.subprocess,'run',side_effect=AssertionError('Aucun Docker')):
            plan = pwa.qualification_plan(self.images,'https://recette.wavyservices.fr')
            self.assertFalse(plan['writesExecuted'])
            self.assertIn('cross-tenant-write-denied',plan['requiredChecks'])

    def test_runtime_refuses_replacing_existing_document_volume(self):
        self.approve()
        def inspect(cmd, **kwargs):
            name = cmd[-1]; component = name[len('wavy-'):-len('-recette')]
            if cmd[:2] == ['docker','inspect']:
                return subprocess.CompletedProcess(cmd,0,json.dumps([{'Image':component,'State':{'Running':True},'Config':{'Env':[]},'Mounts':[]}]))
        def docker(cmd, **kwargs):
            if cmd[:3] == ['docker','image','inspect']:
                repository, digest = self.images[cmd[-1]].split('@')
                return subprocess.CompletedProcess(cmd,0,json.dumps([{'RepoDigests':[repository.rsplit(':',1)[0]+'@'+digest]}]))
            return inspect(cmd, **kwargs)
        with patch.object(pwa.subprocess,'run',side_effect=docker):
            with self.assertRaisesRegex(ValueError, 'stockage existant non qualifié'):
                pwa.overlay(self.root,self.machine,self.images,mutation=True)

    def test_hostconfig_subpath_cannot_be_replaced_by_a_volume_root(self):
        existing = {'Config':{'Env':['WAVY_FACTURES_STOCKAGE_JUSTIFICATIFS=/app/justificatifs']},
                    'Mounts':[{'Destination':'/app/justificatifs','Type':'volume','Name':'fixture-store'}],
                    'HostConfig':{'Mounts':[{'Target':'/app/justificatifs','VolumeOptions':{'Subpath':'notes-frais'}}]}}
        with patch.object(pwa.subprocess,'run',return_value=subprocess.CompletedProcess([],0,json.dumps([existing]))):
            with self.assertRaisesRegex(ValueError,'préserver le stockage'):
                pwa.preserve_storage({'volume':'fixture-store'})

    def test_standard_compose_renders_persistent_mounts_and_all_13_digests(self):
        real = subprocess.run; configs = []
        def render(cmd, **kwargs):
            result = real(cmd, **kwargs, capture_output=True, text=True, check=True)
            configs.append(json.loads(result.stdout)); return result
        with patch.object(images.subprocess,'run',side_effect=render):
            self.assertEqual(images.recette_compose(self.root,['config','--format','json']),0)
        shell = configs[0]['services']['wavy-erp-shell-recette']
        self.assertEqual(len(shell['volumes']),4)
        ports=[p for service in configs[0]['services'].values() for p in service.get('ports',[])]
        self.assertEqual(len(ports),18)
        self.assertTrue(all(p['host_ip']=='127.0.0.1' for p in ports))
        self.assertTrue(all(str(self.root/'docker/recette-pwa') in m['source'] for m in shell['volumes']))
        self.assertEqual(sum('@sha256:' in s['image'] for s in configs[0]['services'].values()),13)

    def test_stop_and_diagnostics_remain_available_when_qualification_is_missing(self):
        with patch.object(images.subprocess,'run', return_value=subprocess.CompletedProcess([],0)) as run:
            machine = self.root/'.env.recette'
            machine.write_text(machine.read_text().replace('WAVY_PWA_ENABLED=false','WAVY_PWA_ENABLED=true'))
            self.assertEqual(images.recette_compose(self.root,['stop']),0)
            self.assertIn('stop',run.call_args.args[0])
            with self.assertRaisesRegex(ValueError,'NO-GO'):
                images.recette_compose(self.root,['up','-d'])

    def test_operation_lock_is_shared_with_shell_and_released(self):
        command=['bash','-c','source "$1"; ROOT_DIR="$2"; recette_operation_lock','_',str(ROOT/'scripts/_common.sh'),str(self.root)]
        with images.recette_operation(self.root,True):
            busy=subprocess.run(command,capture_output=True,text=True)
            self.assertNotEqual(busy.returncode,0);self.assertIn('déjà en cours',busy.stderr)
        self.assertEqual(subprocess.run(command,capture_output=True).returncode,0)

    def test_shell_lock_can_be_inherited_by_the_compose_helper(self):
        code='import sys;from pathlib import Path;sys.path.insert(0,sys.argv[2]);from release_images import recette_operation;\nwith recette_operation(Path(sys.argv[1]),True): print("inherited-ok")'
        shell='source "$1"; ROOT_DIR="$2"; recette_operation_lock; python3 -c "$3" "$ROOT_DIR" "$4"'
        result=subprocess.run(['bash','-c',shell,'_',str(ROOT/'scripts/_common.sh'),str(self.root),code,str(ROOT/'scripts')],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn('inherited-ok',result.stdout)

    def test_historical_rollback_keeps_nginx_mounts_and_pins(self):
        real=subprocess.run;configs=[]
        def render(cmd, **kwargs):
            result=real(cmd,**kwargs,capture_output=True,text=True,check=True)
            configs.append(json.loads(result.stdout));return result
        old='0.1.0-98e2ced'
        expected=images.historical_image(self.root,'gateway',old,'ghcr.io/fabffo')
        with patch.object(images.subprocess,'run',side_effect=render):
            images.recette_compose(self.root,['config','--format','json'],rollback=('gateway',old))
        self.assertEqual(configs[0]['services']['wavy-gateway-recette']['image'],expected)
        self.assertEqual(len(configs[0]['services']['wavy-erp-shell-recette']['volumes']),4)
        self.assertEqual(sum('@sha256:' in service['image'] for service in configs[0]['services'].values()),13)

    def test_unvalidated_rollback_or_changed_pwa_cohort_is_rejected(self):
        with self.assertRaises((ValueError,OSError)):
            images.historical_image(self.root,'gateway','0.1.0-abcdef0','ghcr.io/fabffo')
        self.approve()
        machine=self.root/'.env.recette'
        machine.write_text(machine.read_text()+'\n'+'\n'.join(key+'='+value for key,value in self.machine.items())+'\n')
        with patch.object(images.subprocess,'run') as run:
            with self.assertRaisesRegex(ValueError,'qualification incompatible'):
                images.recette_compose(self.root,['up','-d'],rollback=('gateway','0.1.0-98e2ced'))
            run.assert_not_called()

    def test_preprod_cli_refused_without_execution(self):
        result = subprocess.run([sys.executable,str(ROOT/'scripts/recette_pwa.py'),'preprod','check'],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0); self.assertIn('PREPROD inchangé',result.stderr)


if __name__ == '__main__': unittest.main()
