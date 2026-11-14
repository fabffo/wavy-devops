#!/usr/bin/env python3
"""Tests sans Docker, SSH ou données réelles ; chiffrement réel sur fixtures privées."""
import copy
from contextlib import ExitStack, contextmanager, redirect_stderr
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

    def test_key_is_loaded_from_existing_source_secret_not_stale_recette_setting(self):
        values={'WAVY_SYNC_PREPROD_SSH':'operator@preprod', 'WAVY_SYNC_PREPROD_ROOT':'/srv/wavy devops',
                'WAVY_SYNC_PREPROD_BACKUP_PASSPHRASE':'stale-unused-copy'}
        secret='synthetic-source-key-0123456789abcdef0123456789'
        with patch.object(sync,'command',return_value=secret.encode()) as command:
            self.assertTrue(sync.backup_key(values) == secret)
        args=command.call_args.args[0]
        self.assertEqual(args[0],'ssh')
        self.assertIn('BatchMode=yes',args); self.assertIn('StrictHostKeyChecking=yes',args)
        self.assertIn("cd '/srv/wavy devops'",args[-1])
        self.assertNotIn('_export',args[-1])
        self.assertNotIn(secret,' '.join(args))
        self.assertNotIn('stale-unused-copy',' '.join(args))

    def test_existing_preprod_parser_reads_secret_without_changing_dotenv(self):
        (self.root/'scripts').mkdir()
        shutil.copy(sync.ROOT/'scripts/preprod_config.py',self.root/'scripts')
        path=self.root/'.env.preprod'
        secret='synthetic-only-source-key-0123456789abcdef0123456789'
        content="WAVY_BACKUP_ENCRYPTION_PASSPHRASE='"+secret+"'\n"
        path.write_text(content); path.chmod(0o600)
        code="import socket; socket.gethostname=lambda:'wavy-preprod'\n"+sync.REMOTE_KEY_READER
        result=subprocess.run(['python3','-B','-c',code],cwd=self.root,capture_output=True)
        self.assertEqual(result.returncode,0)
        self.assertTrue(result.stdout.decode() == secret)
        self.assertTrue(path.read_text() == content)
        self.assertEqual(result.stderr,b'')
        path.chmod(0o644)
        refused=subprocess.run(['python3','-B','-c',code],cwd=self.root,capture_output=True)
        self.assertNotEqual(refused.returncode,0)
        self.assertEqual(refused.stdout,b'')
        self.assertNotIn(secret.encode(),refused.stderr)

    def test_key_errors_do_not_expose_remote_output_or_trigger_backup(self):
        values={'WAVY_SYNC_PREPROD_SSH':'operator@preprod','WAVY_SYNC_PREPROD_ROOT':'/srv/devops'}
        secret=b'synthetic-sensitive-error-payload'
        error=subprocess.CalledProcessError(1,['ssh'],output=secret,stderr=secret)
        with patch.object(sync,'command',side_effect=error):
            with self.assertRaises(ValueError) as caught: sync.backup_key(values)
        self.assertNotIn(secret.decode(),str(caught.exception))
        with patch.object(sync,'command',return_value=b''):
            with self.assertRaises(ValueError): sync.backup_key(values)

    def test_receive_reports_remote_phase_and_code_without_raw_secrets(self):
        secret='fixture-sensitive-message-never-display'
        cases=[(1,'WAVY_SYNC_ERROR phase=preprod-resume code=1\nWAVY_SYNC_ERROR phase=preprod-backup code=1\n','preprod-resume',1),
               (1,'WAVY_SYNC_ERROR phase=preprod-backup code=66\n','preprod-backup',66),
               (255,'WAVY_SYNC_ERROR phase=preprod-backup code=1\n','ssh',255),
               (17,'WAVY_SYNC_ERROR phase=unknown-secret code=17\n','preprod-export',17),
               (0,'','transfer',1)]
        for code,markers,phase,expected in cases:
            with self.subTest(code=code):
                child=[sys.executable,'-B','-c',"import sys;sys.stderr.write("+repr(secret+'\n'+markers)+");sys.exit("+str(code)+")"]
                with patch.object(sync,'source_ssh',return_value=child):
                    with self.assertRaises(ValueError) as caught: sync.receive(self.root,{},self.root)
                message=str(caught.exception)
                self.assertIn('phase='+phase+', code='+str(expected)+', ssh_code='+str(code),message)
                self.assertNotIn(secret,message);self.assertNotIn('unknown-secret',message)
                self.assertFalse((self.root/sync.STATE).exists())

    def test_receive_preserves_successful_binary_transfer(self):
        path=self.root/'bundle.tar'
        with tarfile.open(path,'w') as archive:
            for name in sync.SOURCE_FILES: add(archive,name,b'fixture')
        target=self.root/'received';target.mkdir()
        child=[sys.executable,'-B','-c','import sys;from pathlib import Path;sys.stdout.buffer.write(Path(sys.argv[1]).read_bytes())',str(path)]
        with patch.object(sync,'source_ssh',return_value=child): sync.receive(self.root,{},target)
        self.assertEqual({p.name for p in target.iterdir()},sync.SOURCE_FILES)

    def test_source_export_marks_preflight_and_backup_failures(self):
        errors=io.StringIO()
        with patch.object(sync.socket,'gethostname',return_value='wrong-host'), redirect_stderr(errors):
            with self.assertRaises(ValueError): sync.source_export(self.root)
        self.assertIn('phase=preprod-preflight code=1',errors.getvalue())
        @contextmanager
        def locked(*args): yield 3, {}
        errors=io.StringIO()
        with patch.object(sync.socket,'gethostname',return_value='wavy-preprod'), \
             patch.object(sync,'locked',locked), patch.object(sync,'database_guard'), \
             patch.object(sync,'shared_database_guard'), patch.object(sync,'declared_snapshot'), \
             patch.object(sync,'backup_folders',return_value=set()), \
             patch.object(sync.subprocess,'run',side_effect=subprocess.CalledProcessError(66,['fixture-backup'],stderr=b'fixture-sensitive')), \
             redirect_stderr(errors):
            with self.assertRaises(subprocess.CalledProcessError): sync.source_export(self.root)
        self.assertIn('phase=preprod-backup code=66',errors.getvalue())
        self.assertNotIn('fixture-sensitive',errors.getvalue())

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
                      'backup_key':Mock(return_value='x'*40),
                      'declared_snapshot':Mock(return_value=data),'volume_for':lambda c,d:c+'-volume',
                      'shared_database_guard':Mock(),'database_guard':Mock(),'receive':receive,
                      'auth':Mock(),'verify':Mock(),'inspect':Mock(return_value={'Id':'sha256:fixture'}),
                      'crypt':crypt,'check_dumps':Mock(),'save_rollback':save,'runtime_stop':Mock(),
                      'db_restore':restore,'compose':compose,'verify_isolation':Mock(),
                      'command':Mock(),'check_shell':Mock(),'recover':recover}
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

    def control_fixture(self, env, internal, script, mode='ok'):
        fixture=Path(tempfile.mkdtemp(dir=self.root)); (fixture/'scripts').mkdir()
        (fixture/'deployments').mkdir(); (fixture/('.env.'+env)).write_text('')
        for name in ['_common.sh',script]: shutil.copy(sync.ROOT/'scripts'/name,fixture/'scripts'/name)
        if internal: (fixture/sync.POLICY).write_text('{}')
        binary=fixture/'bin';binary.mkdir();log=fixture/'calls.jsonl'
        fake=r'''import json,os,sys
from pathlib import Path
kind=Path(sys.argv[0]).name;args=sys.argv[1:];container=None
if kind=='docker':
 if args[:1]==['info'] or args[:2]==['compose','version']:sys.exit(0)
 if args[:1]!=['exec']:sys.exit(99)
 container=args[1]
url=args[-1]
with open(os.environ['FIXTURE_CONTROL_LOG'],'a') as f:
 f.write(json.dumps({'kind':kind,'container':container,'url':url,'basicAuth':'-u' in args})+'\n')
mode=os.environ['FIXTURE_CONTROL_MODE']
if mode=='transport-failure':sys.exit(7)
if '/referentiels/natures-personne' in url:
 print('{"value":"SALARIE_INTERNE"}' if mode=='bad-json-shape' else '["SALARIE_INTERNE"]')
elif url.endswith('/api/tiers/health'):
 print('{"module":"wrong","status":"OK"}' if mode=='bad-gateway' else '{"module":"wavy-tiers-api","status":"OK"}')
elif '/actuator/health' in url:print('{"status":"DOWN"}' if mode=='down' else '{"status":"UP"}')
else:print('[]')
'''
        for name in ['docker','curl']:
            path=binary/name;path.write_text('#!'+sys.executable+'\n'+fake);path.chmod(0o700)
        envvars=dict(os.environ,PATH=str(binary)+os.pathsep+os.environ['PATH'],
                     FIXTURE_CONTROL_LOG=str(log),FIXTURE_CONTROL_MODE=mode,
                     HEALTHCHECK_MAX_ATTEMPTS='1',HEALTHCHECK_INTERVAL_SECONDS='0',
                     WAVY_SMOKE_TENANT_ID='1',WAVY_SMOKE_USER_ID='1',WAVY_SMOKE_COMPANY_ID='1',
                     WAVY_SMOKE_USER='fixture@example.test',WAVY_SMOKE_PASSWORD='synthetic-private-password')
        result=subprocess.run(['bash',str(fixture/'scripts'/script),env],env=envvars,capture_output=True)
        self.assertNotIn(b'synthetic-private-password',result.stdout+result.stderr)
        calls=[json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []
        return result,calls

    def test_isolated_recette_controls_use_only_docker_exec(self):
        for script in ['healthcheck.sh','smoke-test.sh']:
            with self.subTest(script=script):
                result,calls=self.control_fixture('recette',True,script)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(len(calls),6)
                self.assertTrue(all(c['kind']=='docker' and c['container'].endswith('-recette') for c in calls))
                self.assertFalse(any('2808' in c['url'] or 'preprod' in c['url'] for c in calls))
                if script=='smoke-test.sh':
                    self.assertTrue(all(c['container']=='wavy-socle-api-recette' for c in calls))
                    self.assertTrue(any('http://wavy-gateway-recette:8088/api/tiers/health'==c['url'] for c in calls))
                    for c in calls:
                        if '/wavy-socle-api-' in c['url'] or '/wavy-contrats-api-' in c['url']:
                            self.assertFalse(c['basicAuth'])

    def test_legacy_recette_local_and_preprod_keep_their_transports(self):
        for env in ['local','recette','preprod']:
            for script in ['healthcheck.sh','smoke-test.sh']:
                with self.subTest(env=env,script=script):
                    result,calls=self.control_fixture(env,False,script)
                    self.assertEqual(result.returncode,0,result.stderr)
                    self.assertEqual(len(calls),6)
                    self.assertTrue(all(c['kind']==('docker' if env=='preprod' else 'curl') for c in calls))
                    if env=='preprod':self.assertTrue(all(c['container'].endswith('-preprod') for c in calls))

    def test_internal_smoke_tests_keep_response_validations(self):
        for mode in ['bad-json-shape','bad-gateway','down','transport-failure']:
            with self.subTest(mode=mode):
                result,calls=self.control_fixture('recette',True,'smoke-test.sh',mode)
                self.assertNotEqual(result.returncode,0)
                self.assertEqual(len(calls),6)
        result,_=self.control_fixture('recette',True,'healthcheck.sh','transport-failure')
        self.assertNotEqual(result.returncode,0)

    def shell_response(self, args, enabled=True, broken=None):
        if args[-1]=='-t':return b''
        self.assertEqual(args[:4],['docker','exec','wavy-socle-api-recette','curl'])
        self.assertNotIn('-k',args);self.assertNotIn('-X',args);self.assertNotIn('-L',args)
        url=args[-1];self.assertTrue(url.startswith('http://wavy-erp-shell-recette/'))
        path=url.removeprefix('http://wavy-erp-shell-recette')
        if path==broken:return b'fixture-private-error\n502'
        if path=='/api/auth/session':return b'\n401'
        if path=='/api/tiers/health':return b'{"module":"wavy-tiers-api","status":"OK"}\n200'
        if path=='/pwa-integration.json':return json.dumps({'enabled':enabled}).encode()+b'\n200'
        if path.endswith('.js'):return b'/* synthetic service worker */\n200'
        return ('<html><head><base href="'+path+'"></head></html>\n200').encode()

    def test_erp_shell_checks_proxies_auth_and_optional_pwa_without_public_ports(self):
        for enabled in [True,False]:
            with self.subTest(pwa=enabled), patch.object(sync,'command',side_effect=lambda args:self.shell_response(args,enabled)) as cmd:
                sync.check_shell({'WAVY_PWA_ENABLED':str(enabled).lower()})
                urls=[c.args[0][-1] for c in cmd.call_args_list]
                for module in ['socle','tiers','contrats','factures','tresorerie']:
                    self.assertIn('http://wavy-erp-shell-recette/modules/'+module+'/',urls)
                self.assertEqual('http://wavy-erp-shell-recette/pwa/ngsw-worker.js' in urls,enabled)

    def test_erp_shell_refuses_proxy_errors_wrong_content_and_unprotected_sessions(self):
        for path in ['/','/modules/factures/','/api/tiers/health','/pwa/']:
            with self.subTest(path=path), patch.object(sync,'command',side_effect=lambda args:self.shell_response(args,broken=path)):
                with self.assertRaises(ValueError):sync.check_shell({'WAVY_PWA_ENABLED':'true'})
        for path,payload in [('/modules/tiers/',b'<html><base href="/"></html>\n200'),
                             ('/api/tiers/health',b'{"status":"OK","module":"wrong"}\n200'),
                             ('/api/auth/session',b'{}\n200'),
                             ('/pwa/ngsw-worker.js',b'<html>fallback</html>\n200')]:
            def response(args):
                return payload if args[-1]=='http://wavy-erp-shell-recette'+path else self.shell_response(args)
            with self.subTest(path=path),patch.object(sync,'command',side_effect=response):
                with self.assertRaises(ValueError):sync.check_shell({'WAVY_PWA_ENABLED':'true'})

    def test_post_start_failures_are_saved_before_rollback_without_secrets(self):
        for check,code in [('isolation',1),('healthcheck',7),('smoke-test',8),('erp-shell',22)]:
            with self.subTest(check=check),self.fixture_run():
                # Chaque scénario utilise une nouvelle opération après le rollback précédent.
                (self.root/sync.STATE).unlink(missing_ok=True)
                backup=self.root/'backups/2026-01-01_000000'
                if backup.exists():backup.rmdir()
                old_recover=sync.recover
                def recover(*args):
                    persisted=sync.read_private(self.root/sync.STATE)
                    self.assertEqual(persisted['failure'],{'check':check,'code':code})
                    old_recover(*args)
                def command(args, **kwargs):
                    if Path(str(args[1])).name==('healthcheck.sh' if check=='healthcheck' else 'smoke-test.sh'):
                        raise subprocess.CalledProcessError(code,args,stderr=b'sensitive-fixture-error')
                with ExitStack() as stack:
                    stack.enter_context(patch.object(sync,'recover',side_effect=recover))
                    if check=='isolation':stack.enter_context(patch.object(sync,'verify_isolation',side_effect=ValueError('sensitive-fixture-error')))
                    elif check=='erp-shell':stack.enter_context(patch.object(sync,'check_shell',side_effect=subprocess.CalledProcessError(code,['fixture'],stderr=b'sensitive-fixture-error')))
                    else:stack.enter_context(patch.object(sync,'command',side_effect=command))
                    with self.assertRaises((ValueError,subprocess.CalledProcessError)):sync.run(self.root)
                state=sync.read_private(self.root/sync.STATE)
                self.assertEqual(state['phase'],'rolled-back')
                self.assertEqual(state['failure'],{'check':check,'code':code})
                self.assertNotIn('sensitive-fixture-error',(self.root/sync.STATE).read_text())

    def test_diagnostic_write_failure_does_not_prevent_automatic_rollback(self):
        with self.fixture_run(failure='restore') as events:
            original=sync.atomic_json;failed=False
            def write(path,state):
                nonlocal failed
                if 'failure' in state and not failed:
                    failed=True
                    raise OSError('synthetic disk error')
                original(path,state)
            with patch.object(sync,'atomic_json',side_effect=write):
                with self.assertRaises(RuntimeError):sync.run(self.root)
        self.assertTrue(failed)
        self.assertEqual(events[-1],'recover')
        state=sync.read_private(self.root/sync.STATE)
        self.assertEqual(state['phase'],'rolled-back')
        self.assertEqual(state['failure'],{'check':'restore-databases','code':1})


if __name__=='__main__': unittest.main()
