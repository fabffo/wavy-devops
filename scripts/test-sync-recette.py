#!/usr/bin/env python3
"""Tests sans Docker, SSH ou données réelles ; chiffrement réel sur fixtures privées."""
import copy
from contextlib import ExitStack, contextmanager
import io
import json
import os
from pathlib import Path
import subprocess
import shutil
import tarfile
import tempfile
import unittest
from unittest.mock import patch, Mock
import sys
sys.dont_write_bytecode = True
import sync_recette as sync


def add(archive, name, data=b'document', kind=None):
    item = tarfile.TarInfo(name); item.mode = 0o600; item.uid = 100; item.gid = 101
    if kind:
        item.type = kind
    else: item.size = len(data)
    archive.addfile(item, None if kind else io.BytesIO(data))


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        for name in ['deployments', 'versions', 'backups']:
            (self.root/name).mkdir()
        self.addCleanup(self.tmp.cleanup)

    def test_cli_rejects_every_other_direction_without_io(self):
        with patch.object(sync, 'run') as run:
            for args in [[], ['recette', 'preprod'], ['preprod','local'], ['preprod','recette','--yes']]:
                with self.assertRaises(ValueError): sync.main(args)
            run.assert_not_called()
        result = subprocess.run(['bash', str(sync.ROOT/'wavy'), 'sync', 'recette', 'preprod'], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'seul sens', result.stderr)

    def test_preprod_digest_only_reference_is_accepted_but_other_digest_is_refused(self):
        expected='ghcr.io/fixture/wavy-api:1.0.0-abcdef0@sha256:'+'a'*64
        self.assertTrue(sync.same_reference(expected,expected))
        self.assertTrue(sync.same_reference('ghcr.io/fixture/wavy-api@sha256:'+'a'*64,expected))
        self.assertFalse(sync.same_reference('ghcr.io/fixture/wavy-api@sha256:'+'b'*64,expected))

    def test_transport_rejects_traversal_links_duplicates_and_missing_files(self):
        for names in [[('../escape', None)], [('source.json', tarfile.SYMTYPE)],
                      [('source.json',None),('source.json',None)], [('source.json',None)]]:
            stream = io.BytesIO()
            with tarfile.open(fileobj=stream, mode='w') as archive:
                for name, kind in names: add(archive, name, kind=kind)
            stream.seek(0)
            folder = self.root/str(len(list(self.root.iterdir()))); folder.mkdir()
            with self.assertRaises(ValueError): sync.unpack_bundle(stream, folder)
        self.assertFalse((self.root.parent/'escape').exists())

    def test_source_document_mapping_preserves_ids_content_and_permissions(self):
        path = self.root/'documents.tar'
        with tarfile.open(path,'w') as archive:
            for root in ['contrats','notes-frais']:
                add(archive, root, kind=tarfile.DIRTYPE)
                add(archive, root+'/11/22/33/uuid', b'private document')
        sync.validate_source_documents(str(path))
        sync.split_documents(path,self.root)
        for name in ['contrats','justificatifs']:
            sync.validate_tar(self.root/(name+'.tar'))
            with tarfile.open(self.root/(name+'.tar')) as archive:
                member = archive.getmember('11/22/33/uuid')
                self.assertEqual(archive.extractfile(member).read(), b'private document')
                self.assertEqual((member.uid,member.gid,member.mode),(100,101,0o600))

    def test_document_archives_reject_symlink_and_traversal(self):
        for name, kind in [('../escape',None), ('/absolute',None), ('link',tarfile.SYMTYPE)]:
            path = self.root/'bad.tar'
            with tarfile.open(path,'w') as archive: add(archive,name,kind=kind)
            with self.assertRaises(ValueError): sync.validate_tar(path)

    def test_real_encryption_authentication_and_tampering(self):
        key = 'fixture-key-only-0123456789abcdef0123456789'
        path = self.root/'recette.tar'; path.write_bytes(b'synthetic database and documents')
        sync.crypt(path,self.root/'recette.tar.enc',key)
        sync.auth(self.root,key,'recette',['recette.tar.enc'],'sign')
        sync.auth(self.root,key,'recette',['recette.tar.enc'])
        sync.crypt(self.root/'recette.tar.enc',self.root/'clear',key,True)
        self.assertEqual(path.read_bytes(),(self.root/'clear').read_bytes())
        with self.assertRaises(ValueError): sync.auth(self.root,'wrong-key','recette',['recette.tar.enc'])
        with (self.root/'recette.tar.enc').open('ab') as output: output.write(b'tampered')
        with self.assertRaises(ValueError): sync.auth(self.root,key,'recette',['recette.tar.enc'])

    def test_overlay_preserves_other_configuration_and_blocks_external_network(self):
        sync.atomic_json(self.root/sync.POLICY, {'format':1,'contractsVolume':'contracts-recette'})
        original = {'services':{'wavy-factures-api-recette':{'environment':{'SECRET':'recette-secret'},'volumes':[]}}}
        overlay = sync.sync_overlay(self.root,copy.deepcopy(original))
        self.assertEqual(overlay['networks']['wavy-recette'],{'name':'wavy-recette-sync','internal':True})
        self.assertEqual(overlay['services']['wavy-factures-api-recette']['environment']['SECRET'],'recette-secret')
        self.assertEqual(overlay['services']['wavy-factures-api-recette']['environment']['SPRING_FLYWAY_ENABLED'],'false')
        self.assertEqual(overlay['services']['wavy-contrats-api-recette']['volumes'][0]['target'],'/app/data/contrats')
        for component in sync.COMPONENTS:
            self.assertEqual(overlay['services']['wavy-'+component+'-recette']['restart'],'no')

    def test_interrupted_state_blocks_restart_but_allows_diagnostics(self):
        sync.atomic_json(self.root/sync.STATE,{'phase':'restoring','owner':-1})
        with self.assertRaises(ValueError): sync.sync_overlay(self.root,{})
        self.assertEqual(sync.sync_overlay(self.root,{},mutation=False),{})

    def test_restore_targets_only_recette_and_drops_old_schema(self):
        for db in sync.DATABASES: (self.root/(db+'.dump')).write_bytes(b'synthetic')
        obj={'Config':{'Env':['POSTGRES_USER=recette-role','POSTGRES_DB=recette-db']}}
        with patch.object(sync,'inspect',return_value=obj), patch.object(sync,'psql') as sql, patch.object(sync,'command') as command:
            sync.db_restore(self.root)
        self.assertEqual(sql.call_count,5)
        for call in sql.call_args_list: self.assertIn('DROP SCHEMA public',call.args[1])
        for call in command.call_args_list:
            args=call.args[0]
            self.assertIn('--no-acl',args); self.assertIn('--single-transaction',args)
            self.assertTrue(args[3].endswith('-db-recette'))
            self.assertNotIn('preprod',' '.join(args))

    def test_actual_compose_render_keeps_images_and_secrets_with_isolated_network(self):
        fixture=self.root/'render'; fixture.mkdir()
        shutil.copytree(sync.ROOT/'versions',fixture/'versions')
        shutil.copytree(sync.ROOT/'docker/recette-pwa',fixture/'docker/recette-pwa')
        shutil.copy(sync.ROOT/'docker-compose.recette.yml',fixture)
        text=(sync.ROOT/'.env.recette.example').read_text().replace('CHANGE_ME','fixture-only')
        (fixture/'.env.recette').write_text(text)
        (fixture/'deployments').mkdir()
        sync.atomic_json(fixture/sync.POLICY,{'format':1,'contractsVolume':'fixture-contracts'})
        config=sync.recette_compose(fixture,['config','--format','json'],capture=True)
        self.assertTrue(config['networks']['wavy-recette']['internal'])
        self.assertEqual(config['networks']['wavy-recette']['name'],'wavy-recette-sync')
        images=sync.release(fixture,'recette')[2]
        for component in sync.COMPONENTS:
            service=config['services']['wavy-'+component+'-recette']
            self.assertEqual(service['image'],images[component])
            self.assertEqual(set(service['networks']),{'wavy-recette'})
        contracts=config['services']['wavy-contrats-api-recette']
        self.assertEqual({v['target'] for v in contracts['volumes']},
                         {'/app/data/contrats','/app/data/contrats/pieces-jointes'})
        factures=config['services']['wavy-factures-api-recette']['environment']
        self.assertEqual(factures['WAVY_AI_ACHAT_AUTO_CREATION_ENABLED'],'false')
        self.assertEqual(factures['SPRING_FLYWAY_ENABLED'],'false')
        self.assertEqual((fixture/'.env.recette').read_text(),text)

    def test_recovery_verifies_whole_backup_before_touching_recette(self):
        state={'backup':str(self.root),'before':{'runtime':{}},'volumes':{},'toolImage':'fixture',
               'savedFiles':{'versions/recette.env':'original'},'phase':'restoring'}
        with patch.object(sync,'auth',side_effect=ValueError('HMAC')), patch.object(sync,'runtime_stop') as stop:
            with self.assertRaises(ValueError): sync.recover(self.root,state,'fixture',self.root)
            stop.assert_not_called()
        with ExitStack() as stack:
            events=[]
            for name in ['auth','crypt','unpack_rollback','check_dumps','validate_tar','runtime_stop','db_restore',
                         'compose','restart_policies','command']:
                stack.enter_context(patch.object(sync,name,side_effect=lambda *a,_name=name,**k:events.append(_name)))
            sync.recover(self.root,state,'fixture',self.root)
        self.assertLess(events.index('check_dumps'),events.index('runtime_stop'))
        self.assertLess(events.index('db_restore'),events.index('compose'))
        self.assertEqual((self.root/'versions/recette.env').read_text(),'original')
        self.assertEqual(sync.read_private(self.root/sync.STATE)['phase'],'rolled-back')

    def test_backup_shell_holds_writers_only_after_complete_sync_backup(self):
        # Exécute réellement backup-db.sh ; remplace uniquement les primitives Docker.
        common = r'''
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
env_name(){ echo recette; }
die(){ echo "$*" >&2; exit 1; }
require_docker(){ :; }; recette_operation_lock(){ :; }
require_command(){ command -v "$1" >/dev/null; }
db_container(){ echo "$1-db-recette"; }; db_user(){ echo fixture; }; db_name(){ echo fixture; }
ensure_container_running(){ :; }; info(){ :; }; success(){ :; }; error(){ :; }
docker(){
 case "$1" in
 inspect) echo fixture-contracts;;
 exec) if [[ "$*" == *pg_dump* ]]; then echo synthetic-dump; fi;;
 run) if [[ "${FAIL_ARCHIVE:-0}" == 1 ]]; then return 9; fi
      tar -cf - --files-from /dev/null;;
 *) return 99;;
 esac
}
'''
        documents = r'''
recette_documents_setup(){ DOCUMENT_VOLUME=fixture-docs; DOCUMENT_IMAGE=fixture; }
recette_quiesce(){ QUIESCED_SERVICES=(fixture); echo stop >> "$EVENTS"; }
recette_resume(){ if ((${#QUIESCED_SERVICES[@]})); then echo resume >> "$EVENTS"; fi; QUIESCED_SERVICES=(); }
recette_archive_documents(){ tar -cf "$backup_dir/justificatifs.tar" --files-from /dev/null; }
'''
        for hold, fail in [(False, False), (True, False), (True, True)]:
            with self.subTest(hold=hold,fail=fail):
                fixture=self.root/('shell-'+str(hold)+str(fail)); (fixture/'scripts').mkdir(parents=True)
                shutil.copy(sync.ROOT/'scripts/backup-db.sh',fixture/'scripts')
                (fixture/'scripts/_common.sh').write_text(common)
                (fixture/'scripts/_recette-documents.sh').write_text(documents)
                events=fixture/'events'
                result=subprocess.run(['bash',str(fixture/'scripts/backup-db.sh')]+(['--sync-hold'] if hold else []),
                    env=dict(os.environ,EVENTS=str(events),FAIL_ARCHIVE=str(int(fail))),capture_output=True)
                self.assertEqual(result.returncode == 0,not fail)
                self.assertEqual(events.read_text().splitlines(),['stop'] if hold and not fail else ['stop','resume'])
                published=list((fixture/'backups').glob('20*'))
                if not fail:
                    self.assertEqual(len(published),1)
                    self.assertEqual(len(list(published[0].glob('*.dump'))),5)
                    self.assertEqual((published[0]/'contrats.tar').exists(),hold)
                else: self.assertEqual(published,[])

    @contextmanager
    def fixture_run(self, failure=None, recover_failure=False):
        versions={'WAVY_IMAGE_REGISTRY':'ghcr.io/fixture'}
        digests={}; images={}; runtime={}
        for c in sync.COMPONENTS:
            key=c.upper().replace('-','_')
            versions[key+'_VERSION']='1.0.0-abcdef0'; digests[key+'_DIGEST']='sha256:'+'a'*64
            images[c]='ghcr.io/fixture/wavy-'+c+':1.0.0-abcdef0@'+digests[key+'_DIGEST']
            runtime[c]={'id':'sha256:fixture','reference':images[c].split('@')[0].rsplit(':',1)[0]+'@'+digests[key+'_DIGEST'],
                        'restart':{'Name':'unless-stopped'}}
        data={'versions':versions,'digests':digests,'images':images,'runtime':runtime,'capturedAt':'fixture-date'}
        archive=self.root/'fixture.tar'
        with tarfile.open(archive,'w') as output:
            for name in ['contrats','notes-frais']: add(output,name,kind=tarfile.DIRTYPE)
        for name,key in [('recette.env','versions'),('recette.digests','digests')]:
            (self.root/'versions'/name).write_text('original '+key)
        values={'WAVY_SYNC_PREPROD_BACKUP_PASSPHRASE':'x'*40,
                'WAVY_RECETTE_VALIDATION_MODE':'technical',
                'WAVY_FACTURES_JUSTIFICATIFS_VOLUME':'factures-api-volume'}
        @contextmanager
        def locked(*args): yield 0, {}
        def receive(root, values, source): (source/'source.json').write_text(json.dumps(data))
        def crypt(source,dest,*args):
            if source.name=='documents.tar.enc': dest.write_bytes(archive.read_bytes())
            else: dest.write_bytes(b'fixture')
        backup = self.root/'backups'/'2026-01-01_000000'
        events=[]
        def backup_run(*args,**kwargs):
            events.append('backup'); backup.mkdir()
            if failure=='backup': raise RuntimeError('fixture backup failure')
        def save(*args): events.append('sealed')
        def restore(*args):
            events.append('restore')
            if failure=='restore': raise RuntimeError('fixture restore failure')
        def compose(*args):
            events.append('start')
            if failure=='start': raise RuntimeError('fixture start failure')
        def recover(*args):
            events.append('recover')
            if recover_failure: raise RuntimeError('fixture recovery failure')
            state=args[1]; state['phase']='rolled-back'; sync.atomic_json(self.root/sync.STATE,state)
        replacements={'machine':Mock(return_value=values),'guard_host':Mock(),'locked':locked,
                      'declared_snapshot':Mock(return_value=data),'volume_for':lambda c,d:c+'-volume',
                      'shared_database_guard':Mock(),'database_guard':Mock(),'receive':receive,
                      'auth':Mock(),'verify':Mock(),'inspect':Mock(return_value={'Id':'sha256:fixture'}),
                      'crypt':crypt,'check_dumps':Mock(),'save_rollback':save,'runtime_stop':Mock(),
                      'db_restore':restore,'compose':compose,'verify_isolation':Mock(),
                      'command':Mock(),'recover':recover}
        with ExitStack() as stack:
            for name,value in replacements.items(): stack.enter_context(patch.object(sync,name,value))
            stack.enter_context(patch('subprocess.run',side_effect=backup_run))
            stack.enter_context(patch('builtins.input',return_value='ECRASER RECETTE'))
            stack.enter_context(patch.object(sys.stdin,'isatty',return_value=True))
            yield events

    def test_success_orders_backup_before_restore_and_keeps_recette_config(self):
        with self.fixture_run() as events: sync.run(self.root)
        self.assertEqual(events,['backup','sealed','restore','start'])
        state=sync.read_private(self.root/sync.STATE)
        self.assertEqual(state['phase'],'complete')
        self.assertIn('WAVY_IMAGE_REGISTRY=ghcr.io/fixture',(self.root/'versions/recette.env').read_text())
        self.assertFalse((self.root/'.env.preprod').exists())

    def test_failure_after_mutation_automatically_recovers(self):
        for stage in ['restore','start']:
            with self.subTest(stage=stage):
                (self.root/sync.STATE).unlink(missing_ok=True)
                shutil_path=self.root/'backups'/'2026-01-01_000000'
                if shutil_path.exists(): shutil_path.rmdir()
                with self.fixture_run(failure=stage) as events:
                    with self.assertRaises(RuntimeError): sync.run(self.root)
                self.assertEqual(events[-1],'recover')
                self.assertEqual(sync.read_private(self.root/sync.STATE)['phase'],'rolled-back')

    def test_failed_backup_never_restores_or_changes_versions(self):
        with self.fixture_run(failure='backup') as events:
            with self.assertRaises(RuntimeError): sync.run(self.root)
        self.assertEqual(events,['backup'])
        self.assertEqual((self.root/'versions/recette.env').read_text(),'original versions')
        self.assertEqual(sync.read_private(self.root/sync.STATE)['phase'],'backup-failed')

    def test_failed_recovery_keeps_durable_maintenance_state(self):
        with self.fixture_run(failure='restore',recover_failure=True) as events:
            with self.assertRaises(RuntimeError): sync.run(self.root)
        self.assertEqual(events[-1],'recover')
        self.assertEqual(sync.read_private(self.root/sync.STATE)['phase'],'recovery-failed')

    def test_next_invocation_recovers_interruption_without_starting_new_sync(self):
        with self.fixture_run() as events, patch.object(sync,'receive') as receive:
            sync.atomic_json(self.root/sync.STATE,{'phase':'restoring','backupVerified':True,'owner':-1})
            sync.run(self.root)
            receive.assert_not_called()
        self.assertEqual(events,['recover'])
        self.assertEqual(sync.read_private(self.root/sync.STATE)['phase'],'rolled-back')

    def test_cancel_before_replacement_never_stops_or_backs_up_recette(self):
        with self.fixture_run() as events, patch('builtins.input',return_value='non'):
            with self.assertRaises(ValueError): sync.run(self.root)
        self.assertEqual(events,[])
        self.assertFalse((self.root/sync.STATE).exists())
        self.assertEqual((self.root/'versions/recette.env').read_text(),'original versions')


if __name__=='__main__': unittest.main()
