#!/usr/bin/env python3
"""Cycle PREPROD original : Docker/SQL fictifs, scripts et chiffrement réels, hors dépôt."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
SECRET = 'fictional-smoke-password-do-not-log'
COMPONENTS = ('socle-api tiers-api contrats-api factures-api tresorerie-api gateway '
              'socle-front tiers-front contrats-front factures-front tresorerie-front pwa erp-shell').split()
POSTGRES = 'postgres:16-alpine@sha256:93d55776e04376e19adb2733e3ccebb4392ee7dd86d8ff238503b30fe719c84f'
ABANDONED = {'phase':'abandoned','mutationStarted':False,'previous':None,'completed':[],'observed':{}}


def manifest(path):
    return dict(line.split('=',1) for line in path.read_text().splitlines() if line and not line.startswith('#'))


def references(root):
    versions=manifest(root/'versions/preprod.env'); digests=manifest(root/'versions/preprod.digests')
    return {c:(versions['WAVY_IMAGE_REGISTRY']+'/wavy-'+c+':'+versions[c.upper().replace('-','_')+'_VERSION'],
               digests[c.upper().replace('-','_')+'_DIGEST']) for c in COMPONENTS}


def image_id(component):return 'sha256:'+hashlib.sha256(('target-'+component).encode()).hexdigest()


def fake_docker(args):
    root=Path(os.environ['FIXTURE_ROOT']); refs=references(root)
    state_path=root/'runtime.json';state=json.loads(state_path.read_text())
    def save():state_path.write_text(json.dumps(state))
    def record(op,service=''):
        with (root/'calls.jsonl').open('a') as out:out.write(json.dumps({'op':op,'service':service})+'\n')
    if args[:2]==['context','inspect']:print('unix:///var/run/docker.sock');return 0
    if args[:1]==['info']:print(root);return 0
    if args[:2]==['manifest','inspect'] or args[:1]==['pull']:return 0
    if args[:2]==['volume','inspect']:
        print('wavy-preprod' if any('com.docker.compose.project' in a for a in args) else 'documents-preprod');return 0
    if args[:2]==['image','tag']:record('rollback_cache');return 0
    if args[:2]==['image','inspect']:
        image=next((a for a in args[2:] if a.startswith(('ghcr.io/','postgres:'))),None)
        if image==POSTGRES:print(json.dumps([{'Id':'fixture-postgres'}]));return 0
        component=next((c for c,(tag,digest) in refs.items() if image in (tag,tag+'@'+digest,tag.rsplit(':',1)[0]+'@'+digest)),None)
        if component is None:return 97
        tag,digest=refs[component];version=tag.rsplit(':',1)[1];semver,revision=version.rsplit('-',1)
        labels={'org.opencontainers.image.revision':(revision+'0'*40)[:40],
                'org.opencontainers.image.version':semver,
                'org.opencontainers.image.source':'https://github.com/fabffo/wavy-'+component}
        repo=tag.rsplit(':',1)[0]+'@'+digest
        fmt=args[args.index('--format')+1] if '--format' in args else args[args.index('-f')+1] if '-f' in args else None
        if fmt is None:print(json.dumps([{'Id':image_id(component),'RepoDigests':[repo],'Config':{'Labels':labels}}]))
        elif 'RepoDigests' in fmt:print(repo)
        elif fmt=='{{.Id}}':print(image_id(component))
        elif 'json .Config.Labels' in fmt:print(json.dumps(labels))
        elif 'org.opencontainers.image.revision' in fmt:print(labels['org.opencontainers.image.revision'])
        else:return 97
        return 0
    if args[:1]==['inspect']:
        container=args[-1];fmt=args[args.index('-f')+1]
        if 'com.docker.compose.project' in fmt:print('wavy-preprod')
        elif 'com.docker.compose.service' in fmt:print(container[:-len('-db-preprod')]+'-postgres' if container.endswith('-db-preprod') else container)
        elif '.State.Running' in fmt:print(str(state['running'].get(container,True)).lower())
        elif '.State.StartedAt' in fmt:print('2026-11-04T00:00:00Z')
        elif '.State.ExitCode' in fmt:print('0')
        elif 'Health.Status' in fmt:print('healthy')
        elif fmt=='{{.Image}}':print(state['active'][container]['id'])
        elif fmt=='{{.Config.Image}}':print(state['active'][container]['reference'])
        else:return 97
        return 0
    if args[:1]==['compose']:
        if args[1:]==['version']:return 0
        if 'config' in args:
            # Seul rendu natif en lecture seule ; aucun autre appel au vrai Docker.
            os.execv(os.environ['FIXTURE_REAL_DOCKER'],[os.environ['FIXTURE_REAL_DOCKER'],*args])
        if 'up' in args:
            service=args[-1];component=service[len('wavy-'):-len('-preprod')]
            if component=='contrats-api':
                if os.environ.get('FIXTURE_CASE')=='apply_failure':return 37
                if os.environ.get('FIXTURE_CASE')=='apply_interrupt':
                    os.kill(os.getppid(),signal.SIGTERM)
                    return 143
            tag,digest=refs[component]
            state['active'][service]={'id':image_id(component),'reference':tag.rsplit(':',1)[0]+'@'+digest}
            state['updates'].append(component);state['running'][service]=True;save();record('replace',service);return 0
        if 'logs' in args:
            record('migration_logs',args[-1])
            if os.environ.get('FIXTURE_CASE')=='migration_failure':print('FlywayValidateException '+SECRET)
            if os.environ.get('FIXTURE_CASE')=='migration_unreadable':return 92
            return 0
        return 97
    if args[:1] in (['stop'],['start']):
        service=args[-1];state['running'][service]=args[0]=='start';save();record(args[0],service);return 0
    if args[:1]==['run']:
        assert '--read-only' in args and '--pull' in args and 'never' in args
        assert any('readonly' in a for a in args)
        command=args[-1]
        if command in ('test -d /documents/notes-frais; test ! -L /documents/notes-frais',
                       'test -r /documents; test -x /documents; test ! -L /documents/notes-frais; if test -e /documents/notes-frais; then test -d /documents/notes-frais; fi'):
            record('pwa_guard')
            if os.environ.get('FIXTURE_CASE')=='tool_error':return 125
            return subprocess.run(['/bin/sh','-eu','-c',command.replace('/documents',str(root/'documents'))]).returncode
        record('document_archive')
        output=io.BytesIO()
        with tarfile.open(fileobj=output,mode='w') as archive:
            for name in ('contrats','notes-frais'):
                if (root/'documents'/name).is_dir():
                    item=tarfile.TarInfo(name);item.type=tarfile.DIRTYPE;item.uid=100;item.gid=101;item.mode=0o700;archive.addfile(item)
        sys.stdout.buffer.write(output.getvalue());return 0
    if args[:1]==['exec']:
        container=args[1];command=args[2:]
        if command[0]=='pg_dump':
            record('dump',container)
            if os.environ.get('FIXTURE_CASE')=='dump_failure' and container=='contrats-db-preprod':return 66
            sys.stdout.buffer.write(b'FICTIONAL SQL DUMP ONLY');return 0
        if command[0]=='pg_restore':record('FORBIDDEN_RESTORE',container);return 98
        if command[0]=='getent':print('172.18.0.18 wavy-gateway-preprod');return 0
        if command[0]=='nginx':record('nginx_reload' if command[-1]=='reload' else 'nginx_test');return 0
        url=command[-1]
        if '/actuator/health' in url:print('{"status":"UP"}')
        elif '/api/tiers/referentiels/' in url:print('["SALARIE_INTERNE"]')
        elif url.endswith('/api/contrats') or '/api/tresorerie/' in url:print('[]')
        elif url.endswith('/api/tiers/health'):print('{"module":"wavy-tiers-api","status":"OK"}')
        else:print('<html>fixture front</html>')
        record('http',container);return 0
    return 97


class BackupTransition(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='wavy-complete-preprod-')
        self.root=Path(self.tmp.name)
        with tarfile.open(fileobj=io.BytesIO(subprocess.check_output(['git','archive','HEAD'],cwd=ROOT))) as archive:
            archive.extractall(self.root,filter='data')
        for name in ('backup-preprod.sh','release-preprod.sh','install.sh','_preprod.sh','preprod_operation.py',
                     'delivery_batch.py','delivery-preflight.sh','delivery-apply.sh'):
            shutil.copyfile(ROOT/'scripts'/name,self.root/'scripts'/name)
        lines=[]
        for line in (ROOT/'.env.preprod.example').read_text().splitlines():
            if line and not line.startswith('#') and '=' in line:
                key,value=line.split('=',1)
                if 'CHANGE_ME' in value:value='123456789' if key.endswith('SIREN') else 'fixture-'+key.lower()+'-0000000000000000'
                line=key+'='+value
            lines.append(line)
        lines += ['WAVY_SMOKE_TENANT_ID=1','WAVY_SMOKE_USER_ID=1','WAVY_SMOKE_COMPANY_ID=1',
                  'WAVY_SMOKE_USER=fixture@example.test','WAVY_SMOKE_PASSWORD='+SECRET]
        env=self.root/'.env.preprod';env.write_text('\n'.join(lines)+'\n');env.chmod(0o600)
        deploy=self.root/'deployments';deploy.mkdir(exist_ok=True)
        (deploy/'pwa-release').mkdir();(deploy/'pwa-release/state.json').write_text('{"phase":"prepared"}')
        (deploy/'pwa-release/state.json').chmod(0o600)
        refs=references(self.root)
        proof=deploy/'recette-validation.private.json'
        proof.write_text(json.dumps({'approved':True,'reviewer':'fictional-test-only',
                                    'images':{c:tag+'@'+digest for c,(tag,digest) in refs.items()}}));proof.chmod(0o600)
        docs=self.root/'documents';docs.mkdir();(docs/'contrats').mkdir()
        self.bin=self.root/'fixture-bin';self.bin.mkdir()
        shim=self.bin/'docker';shim.write_text('#!/usr/bin/env python3\nimport runpy,sys\nsys.argv=['+repr(str(Path(__file__).resolve()))+',"--fake-docker"]+sys.argv[1:]\nrunpy.run_path('+repr(str(Path(__file__).resolve()))+',run_name="__main__")\n');shim.chmod(0o700)
        hostname=self.bin/'hostname';hostname.write_text('#!/bin/sh\necho wavy-preprod\n');hostname.chmod(0o700)
        running={**{'wavy-'+c+'-preprod':True for c in COMPONENTS},**{db+'-db-preprod':True for db in ('socle','tiers','contrats','factures','tresorerie')}}
        self.initial={'active':{'wavy-'+c+'-preprod':{'id':'old-'+c,'reference':'fixture-old-'+c} for c in COMPONENTS},'running':running,'updates':[]}
        (self.root/'runtime.json').write_text(json.dumps(self.initial))
        self.history={p.name:p.read_bytes() for p in (self.root/'versions/history/preprod').glob('*.tsv')}
        self.env={k:v for k,v in os.environ.items() if k not in ('BASH_ENV','DOCKER_HOST','DOCKER_CONTEXT') and not k.startswith('BASH_FUNC_')}
        self.env.update(PATH=str(self.bin)+os.pathsep+self.env['PATH'],FIXTURE_ROOT=str(self.root),FIXTURE_REAL_DOCKER=shutil.which('docker'),WAVY_DEPLOY_MIN_FREE_KB='1',TMPDIR=str(self.root))

    def tearDown(self):self.tmp.cleanup()

    def set_pwa_state(self, state):
        (self.root/'deployments/pwa-release/state.json').write_text(json.dumps(state))

    def run_backup(self):
        result=subprocess.run(['bash',str(self.root/'scripts/backup-preprod.sh')],cwd=self.root,
                              env=self.env,capture_output=True,text=True,timeout=30)
        self.assertNotIn(SECRET,result.stdout+result.stderr)
        return result

    def run_cycle(self, baseline=False, scenario='ok'):
        if baseline:
            # Restaurer les deux fragments 3ecf3c9 fautifs dans la fixture seulement.
            # Ne depend pas de l'historique Git disponible (checkout CI superficiel).
            backup=self.root/'scripts/backup-preprod.sh'
            text=backup.read_text();start=text.index('# Un abandon avant toute preparation')
            end=text.index('require_command openssl',start)
            original='''# Dès qu'un lot PWA a été préparé, une archive Contrats seule ne doit plus masquer un stockage absent.
if [[ -f "$ROOT_DIR/deployments/pwa-release/state.json" ]]; then
  preprod_document_tool ro 'test -d /documents/notes-frais; test ! -L /documents/notes-frais'
fi
'''
            backup.write_text(text[:start]+original+text[end:])
        for args in (['init','-q'],['add','.'],['-c','user.name=Fixture','-c','user.email=fixture@example.test','commit','--allow-empty','-qm','fixture']):
            subprocess.run(['git',*args],cwd=self.root,check=True,capture_output=True)
        result=subprocess.run(['./wavy','install','preprod'],cwd=self.root,env=dict(self.env,FIXTURE_CASE=scenario),capture_output=True,text=True,timeout=180)
        self.assertNotIn(SECRET,result.stdout+result.stderr)
        state=json.loads((self.root/'runtime.json').read_text())
        calls=[json.loads(s) for s in (self.root/'calls.jsonl').read_text().splitlines()]
        return result,state,calls

    def assert_not_deployed(self,state,calls):
        self.assertEqual(state,self.initial)
        self.assertFalse((self.root/'backups').exists())
        self.assertFalse(any(c['op'] in ('replace','stop','start','dump') for c in calls))
        self.assertFalse((self.root/'deployments/preprod.tsv').exists())
        for path in (self.root/'versions/history/preprod').glob('*.tsv'):
            self.assertEqual(path.read_bytes(),self.history[path.name])

    def test_original_silent_backup_gate_is_reported_by_the_batch_engine(self):
        self.set_pwa_state(ABANDONED)
        result,state,calls=self.run_cycle(baseline=True)
        self.assertEqual(result.returncode,1,result.stdout+result.stderr)
        self.assertIn('etape=backup, code=1',result.stderr)
        self.assertIn('Image socle-api',result.stdout)
        self.assertNotIn('Sauvegarde chiff',result.stdout)
        self.assertTrue(any(c['op']=='pwa_guard' for c in calls))
        self.assert_not_deployed(state,calls)

    def test_same_gate_has_explicit_message_and_preserves_code_and_protections(self):
        result,state,calls=self.run_cycle()
        self.assertEqual(result.returncode,1,result.stdout+result.stderr)
        self.assertIn('notes-frais',result.stderr)
        self.assertIn('etape=backup, code=1',result.stderr)
        self.assert_not_deployed(state,calls)

    def test_symlink_is_still_refused(self):
        self.set_pwa_state(ABANDONED)
        other=self.root/'other';other.mkdir();(self.root/'documents/notes-frais').symlink_to(other,target_is_directory=True)
        result,state,calls=self.run_cycle()
        self.assertEqual(result.returncode,1,result.stderr)
        self.assertIn('controle documentaire PWA',result.stderr)
        self.assert_not_deployed(state,calls)

    def test_tool_error_code_reaches_the_cli_through_all_wrappers(self):
        result,state,calls=self.run_cycle(scenario='tool_error')
        self.assertEqual(result.returncode,125,result.stderr)
        self.assertIn('code=125',result.stderr)
        self.assert_not_deployed(state,calls)

    def test_complete_thirteen_components_use_real_scripts_and_real_encrypted_backups(self):
        self.set_pwa_state(ABANDONED)
        # Reprendre la situation reelle : sept composants deja sur la cible.
        for component in COMPONENTS[:7]:
            tag,digest=references(self.root)[component]
            self.initial['active']['wavy-'+component+'-preprod']={'id':image_id(component),'reference':tag.rsplit(':',1)[0]+'@'+digest}
        (self.root/'runtime.json').write_text(json.dumps(self.initial))
        legacy=self.root/'backups/preprod/20000101T000000Z-preserve'
        legacy.mkdir(parents=True);(legacy/'marker').write_text('PRESERVE HISTORICAL LOT')
        os.utime(legacy,(0,0))
        state_path=self.root/'deployments/pwa-release/state.json'
        original_state=state_path.read_bytes()
        result,state,calls=self.run_cycle()
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(state['updates'],COMPONENTS)
        self.assertTrue(all(state['running'].values()))
        for component,(tag,digest) in references(self.root).items():
            self.assertEqual(state['active']['wavy-'+component+'-preprod'],{'id':image_id(component),'reference':tag.rsplit(':',1)[0]+'@'+digest})
            path=self.root/'versions/history/preprod'/ (component+'.tsv')
            self.assertTrue(path.read_bytes().startswith(self.history[path.name]))
            self.assertIn(digest,path.read_text())
        batches=list((self.root/'backups/preprod').glob('????????T??????Z-*'))
        self.assertEqual(len(batches),2)  # un historique conserve + un seul nouveau lot
        self.assertEqual((legacy/'marker').read_text(),'PRESERVE HISTORICAL LOT')
        self.assertFalse(list((self.root/'backups/preprod').glob('.incomplete.*')))
        self.assertEqual(sum(c['op']=='dump' for c in calls),5)
        self.assertEqual(sum(c['op']=='document_archive' for c in calls),1)
        self.assertEqual(sum(c['op']=='nginx_reload' for c in calls),13)
        journal=(self.root/'deployments/preprod.tsv').read_text()
        self.assertEqual(journal.count('\tOK\t'),13)
        self.assertEqual([line.split('\t')[3] for line in journal.splitlines()[1:]],COMPONENTS)
        self.assertEqual(result.stdout.count('Smoke tests preprod : OK'),13)
        self.assertEqual(result.stdout.count('Toutes les APIs preprod'),13)
        self.assertEqual(result.stdout.count('DEPLOY PREPROD '),13)
        self.assertFalse((self.root/'documents/notes-frais').exists())
        self.assertEqual(state_path.read_bytes(),original_state)
        record=json.loads(next((self.root/'deployments').glob('preprod-delivery-*.private.json')).read_text())
        self.assertEqual(record['before'],{c:self.initial['active']['wavy-'+c+'-preprod'] for c in COMPONENTS})
        self.assertTrue(record['backupVerified'])

    def test_partial_apply_stops_without_second_backup_or_automatic_restore(self):
        self.set_pwa_state(ABANDONED)
        result,state,calls=self.run_cycle(scenario='apply_failure')
        self.assertEqual(result.returncode,37,result.stderr)
        self.assertEqual(state['updates'],COMPONENTS[:2])
        self.assertEqual(sum(c['op']=='dump' for c in calls),5)
        self.assertEqual(sum(c['op']=='document_archive' for c in calls),1)
        self.assertFalse(any(c['op']=='FORBIDDEN_RESTORE' for c in calls))
        record=json.loads(next((self.root/'deployments').glob('preprod-delivery-*.private.json')).read_text())
        self.assertEqual(record['phase'],'failed')
        self.assertEqual(record['completed'],COMPONENTS[:2])
        self.assertEqual(record['failedComponent'],'contrats-api')
        self.assertIn('composant=contrats-api, code=37',result.stderr)
        self.assertTrue(Path(record['backup']).is_dir())

    def test_interrupted_apply_then_same_command_resumes_all_thirteen(self):
        self.set_pwa_state(ABANDONED)
        first,state,calls=self.run_cycle(scenario='apply_interrupt')
        self.assertEqual(first.returncode,143,first.stderr)
        self.assertEqual(state['updates'],COMPONENTS[:2])
        lots=set((self.root/'backups/preprod').glob('????????T??????Z-*'))
        self.assertEqual(len(lots),1)
        first_record=next((self.root/'deployments').glob('preprod-delivery-*.private.json'))
        first_bytes=first_record.read_bytes()
        result,after,calls=self.run_cycle()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(after['updates'],COMPONENTS[:2]+COMPONENTS)
        self.assertEqual(len(list((self.root/'backups/preprod').glob('????????T??????Z-*'))),2)
        self.assertTrue(all(p.is_dir() for p in lots))
        self.assertEqual(first_record.read_bytes(),first_bytes)
        self.assertEqual(sum(c['op']=='dump' for c in calls),10)
        self.assertEqual(sum(c['op']=='document_archive' for c in calls),2)
        self.assertFalse(any(c['op']=='FORBIDDEN_RESTORE' for c in calls))
        records=[json.loads(p.read_text()) for p in (self.root/'deployments').glob('preprod-delivery-*.private.json') if p!=first_record]
        self.assertEqual(len(records),1)
        self.assertEqual(records[0]['phase'],'complete')
        for component in COMPONENTS[:2]:
            self.assertEqual(records[0]['before'][component]['id'],image_id(component))
        for path in (self.root/'versions/history/preprod').glob('*.tsv'):
            self.assertTrue(path.read_bytes().startswith(self.history[path.name]))

    def test_resume_refuses_failed_or_unreadable_current_migration_logs_before_backup(self):
        self.set_pwa_state(ABANDONED)
        for scenario in ('migration_failure','migration_unreadable'):
            with self.subTest(scenario=scenario):
                result,state,calls=self.run_cycle(scenario=scenario)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('migrations non valides pour socle-api',result.stderr)
                self.assert_not_deployed(state,calls)

    def test_failed_backup_retains_partial_lot_and_resumes_writers_without_deploying(self):
        self.set_pwa_state(ABANDONED)
        result,state,calls=self.run_cycle(scenario='dump_failure')
        self.assertEqual(result.returncode,66,result.stderr)
        self.assertEqual(state,self.initial)
        partials=list((self.root/'backups/preprod').glob('.incomplete.*'))
        self.assertEqual(len(partials),1)
        self.assertTrue(any(partials[0].iterdir()))
        self.assertFalse(any(c['op'] in ('replace','FORBIDDEN_RESTORE') for c in calls))
        self.assertTrue(all(state['running'].values()))

    def test_abandoned_after_any_storage_or_runtime_step_keeps_strict_guard(self):
        variants=[{'mutationStarted':True},{'previous':{}},{'completed':['socle-api']},
                  {'observed':{'socle-api':{}}},{'storagePreconditions':{}},{'backup':None},{'phase':'failed'}]
        missing_previous=dict(ABANDONED);del missing_previous['previous']
        for state in [dict(ABANDONED,**change) for change in variants]+[missing_previous,{}]:
            with self.subTest(state=state):
                self.set_pwa_state(state)
                result=self.run_backup()
                self.assertEqual(result.returncode,1,result.stderr)
                self.assertIn('controle documentaire PWA',result.stderr)
                self.assertFalse((self.root/'backups').exists())

    def test_regular_file_is_not_silently_omitted_for_abandoned_state(self):
        self.set_pwa_state(ABANDONED)
        (self.root/'documents/notes-frais').write_text('FICTIONAL DOCUMENT, PRESERVE')
        result=self.run_backup()
        self.assertEqual(result.returncode,1,result.stderr)
        self.assertIn('controle documentaire PWA',result.stderr)
        self.assertEqual((self.root/'documents/notes-frais').read_text(),'FICTIONAL DOCUMENT, PRESERVE')
        self.assertFalse((self.root/'backups').exists())

    def test_prepared_state_with_valid_notes_keeps_normal_backup(self):
        (self.root/'documents/notes-frais').mkdir()
        result=self.run_backup()
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(len(list((self.root/'backups/preprod').glob('????????T??????Z-*'))),1)


if __name__=='__main__':
    if sys.argv[1:2]==['--fake-docker']:
        raise SystemExit(fake_docker(sys.argv[2:]))
    unittest.main()
