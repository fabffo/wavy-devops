#!/usr/bin/env python3
"""Restore integration/order/cleanup with guarded fixture owner; Docker entirely mocked."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
import tempfile
from unittest.mock import patch

P=Path(__file__).resolve().parent


def load(file,name):
    s=importlib.util.spec_from_file_location(name,P/file);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


review=load('test-final-review.py','validator_review_fixtures')
r=review.restore
engine_fixture=review.fixture
plan=load('prepare-isolation-cases.py','isolation_offline_plan')


class RestoreHook(unittest.TestCase):
    def cycle(self, failure=None, validator_cleanup=True, down_failure=False):
        with review.restore_fixture(down_fails=down_failure) as (root,directory,folder,docker):
            original=r.command;events=[]
            def command(args,**kwargs):
                if 'up' in args:events.append('up');return b''
                if 'pg_restore' in args:return b''
                if 'psql' in args:return b'1'
                if 'stat' in args:return b'100:101:700'
                if 'tar' in args:return next(directory.glob('restore-private-*/documents.tar')).read_bytes()
                if 'down' in args:events.append('down')
                return original(args,**kwargs)
            def validation(cmd,project,tmp,evidence,binding,**kwargs):
                events.append('validation')
                report={**binding,'status':'failed' if failure else 'passed','cleanup':validator_cleanup,'images':{}}
                r.op.atomic_json(evidence,report)
                if failure:raise failure
                return report
            with patch.object(r,'command',command),patch.object(r.subprocess,'run',return_value=SimpleNamespace(returncode=0)),\
                 patch.object(r.validator,'validate_copies',side_effect=validation):
                try:r.restore(root/'.env.preprod',folder)
                except BaseException as error:self.error=error
                else:self.error=None
            self.events=events
            self.report=json.loads((directory/'schema-validation.json').read_text())
            self.proof=(directory/'restore-proof.json').exists()
            self.attempt=json.loads((directory/'restore-attempt.json').read_text())
            self.staging_exists=Path(self.attempt.get('envFile','/does-not-exist')).exists()

    def test_hook_precedes_down_and_proof_after_down(self):
        self.cycle()
        self.assertIsNone(self.error)
        self.assertLess(self.events.index('validation'),self.events.index('down'))
        self.assertTrue(self.proof)
        self.assertEqual(self.attempt['phase'],'cleaned')

    def test_failed_validation_or_interruption_still_destroys_copies_and_preserves_report(self):
        for error in (ValueError('checksum'),InterruptedError('signal'),KeyboardInterrupt()):
            self.cycle(error)
            self.assertIsInstance(self.error,type(error))
            self.assertIn('down',self.events)
            self.assertFalse(self.proof)
            self.assertEqual(self.report['status'],'failed')
            self.assertEqual(self.attempt['phase'],'cleaned')

    def test_remaining_validator_blocks_down_and_retains_recovery(self):
        self.cycle(ValueError('validator cleanup'),False)
        self.assertIsInstance(self.error,ValueError)
        self.assertNotIn('down',self.events)
        self.assertFalse(self.proof)
        self.assertEqual(self.attempt['phase'],'creating')
        self.assertTrue(self.staging_exists)

    def test_copy_cleanup_failure_never_publishes_restore_proof(self):
        self.cycle(down_failure=True)
        self.assertIsInstance(self.error,RuntimeError)
        self.assertFalse(self.proof)
        self.assertTrue(self.staging_exists)
        self.assertEqual(self.report['status'],'passed')
        # Schema passed != complete restore success; no restore-proof is published.


class Recovery(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.directory=Path(self.tmp.name);self.run='a'*32
        self.backup={'directory':'fixture','manifestSha256':'b'*64}
        self.project='wavy-pwa-restore-'+self.run+'-1234abcd'
        self.stage=self.directory/'restore-private-fixture';self.stage.mkdir(mode=0o700)
        self.config=self.stage/'restore.env';self.config.write_text('synthetic');self.config.chmod(0o600)
        self.name='wavy-validator-'+'c'*24
        self.attempt={'run':self.run,'backup':self.backup,'project':self.project,'phase':'creating','envFile':str(self.config)}
        self.report={'run':self.run,'backup':self.backup,'project':self.project,'cleanup':False,'status':'cleanup-failed','containers':[self.name]}
        r.op.atomic_json(self.directory/'restore-attempt.json',self.attempt)
        r.op.atomic_json(self.directory/'schema-validation.json',self.report)
        self.commands=[]
    def command(self,args,**kwargs):
        self.commands.append(args)
        if args[-3:]==['config','--format','json']:
            return __import__('json').dumps({'services':{name:{'network_mode':'none','read_only':True,'image':r.validator.PG_IMAGE} for name in (*r.DATABASES,'documents')},'volumes':{}}).encode()
        if args[:2]==['docker','ps']:return b'fixture-id'
        if args[:2]==['docker','inspect']:
            return __import__('json').dumps([{'Name':'/'+self.name,'Config':{'Labels':{'wavy.validator.project':self.project},'Image':r.validator.IMAGES['new'][0]},'HostConfig':{'ReadonlyRootfs':True}}]).encode()
        return b''
    def recover(self,command=None):
        with patch.object(r,'command',side_effect=command or self.command):r.recover_previous(self.directory,self.run,self.backup)
    def test_owned_recovery_removes_validator_before_copies_and_staging(self):
        self.recover()
        self.assertLess(next(i for i,c in enumerate(self.commands) if c[:3]==['docker','rm','-f']),next(i for i,c in enumerate(self.commands) if 'down' in c))
        self.assertFalse(self.stage.exists())
        self.assertEqual(r.op.read_private(self.directory/'restore-attempt.json')['phase'],'cleaned')
        self.assertEqual(r.op.read_private(self.directory/'schema-validation.json')['status'],'failed-recovered')
    def test_foreign_owner_or_backup_refused_before_docker(self):
        for key,value in [('run','foreign'),('backup',{})]:
            r.op.atomic_json(self.directory/'restore-attempt.json',dict(self.attempt,**{key:value}))
            with self.assertRaises(ValueError):self.recover()
            self.assertFalse(self.commands)
    def test_completed_prior_report_does_not_block_new_attempt_cleanup(self):
        stale=dict(self.report,project='wavy-pwa-restore-'+self.run+'-87654321',cleanup=True,containers=[],status='passed')
        path=self.directory/'schema-validation.json';r.op.atomic_json(path,stale)
        previous=path.read_bytes()
        self.recover()
        self.assertFalse(self.stage.exists())
        self.assertEqual(path.read_bytes(),previous)
        self.assertTrue(any('down' in c for c in self.commands))
        self.assertFalse(any(c[:3]==['docker','rm','-f'] for c in self.commands))

    def test_foreign_validator_label_is_never_removed(self):
        def command(args,**kwargs):
            result=self.command(args,**kwargs)
            if args[:2]==['docker','inspect']:
                data=json.loads(result);data[0]['Config']['Labels']['wavy.validator.project']='foreign';return json.dumps(data).encode()
            return result
        with self.assertRaises(ValueError):self.recover(command)
        self.assertFalse(any(c[:3]==['docker','rm','-f'] for c in self.commands))
        self.assertTrue(self.config.exists())
    def test_cleanup_failure_preserves_recovery_and_retries(self):
        def command(args,**kwargs):
            if 'down' in args:raise TimeoutError('synthetic')
            return self.command(args,**kwargs)
        with self.assertRaises(TimeoutError):self.recover(command)
        self.assertTrue(self.config.exists())
        self.assertNotEqual(r.op.read_private(self.directory/'restore-attempt.json')['phase'],'cleaned')
        self.recover()
        self.assertFalse(self.stage.exists())
    def test_staging_failure_after_docker_cleanup_is_retryable_without_docker(self):
        with patch.object(r.shutil,'rmtree',side_effect=OSError('synthetic')):
            with self.assertRaises(OSError):self.recover()
        self.assertEqual(r.op.read_private(self.directory/'restore-attempt.json')['phase'],'docker-cleaned')
        self.commands.clear();self.recover()
        self.assertFalse(self.commands)
        self.assertFalse(self.stage.exists())


class ProofConsumption(unittest.TestCase):
    setUp=engine_fixture.Orchestration.setUp
    proof=engine_fixture.Orchestration.proof
    call=engine_fixture.Orchestration.call
    prepare=engine_fixture.Orchestration.prepare
    deploy=engine_fixture.Orchestration.deploy
    authorization=engine_fixture.Orchestration.authorization
    def test_missing_jpa_result_blocks_deploy_before_any_component(self):
        self.prepare();self.call('restore')
        self.engine.state['restore']['checks']['jpa']=False;self.engine.save()
        with self.assertRaises(ValueError):self.call('deploy')
        self.assertFalse(any(x.startswith('closed-') for x in self.backend.events))

    def test_old_format_proof_and_wrong_image_block_resume(self):
        for mutation in ('missing','wrong-image'):
            with self.subTest(mutation=mutation):
                # Fresh fixture per mutation; cannot recover a failed test by editing state.
                self.setUp()
                self.prepare();self.call('restore')
                if mutation=='missing':self.engine.state['restore'].pop('schemaValidation')
                else:self.engine.state['restore']['schemaValidation']['images']['old']['reference']='other'
                self.engine.save()
                proof=dict(self.proof(['interrupted-effect-inspected']),pending=None,resumePhase='restored')
                with self.assertRaises(ValueError):self.call('resume',proof)

    def test_missing_jpa_result_blocks_open_test(self):
        self.deploy()
        self.engine.state['restore']['checks']['flyway']=False;self.engine.save()
        with self.assertRaises(ValueError):self.call('open-test',self.authorization())
        self.assertFalse(self.backend.opened)

    def test_unexpected_old_image_blocks_before_barrier(self):
        with patch.object(self.backend,'snapshot',return_value=self.plan):
            with self.assertRaises(ValueError):self.prepare()
        self.assertNotIn('barrier',self.backend.events)


class OfflineCases(unittest.TestCase):
    def test_247_work_items_are_plans_without_results(self):
        matrix=json.loads((P/'MATRICE-CORRECTIONS-PREPROD.json').read_text())
        cases=list(plan.prepare(matrix))
        self.assertEqual(len(cases),247)
        self.assertEqual(len({c['id'] for c in cases}),247)
        self.assertTrue(all(c['status']=='NON_EXECUTE' for c in cases))
        self.assertTrue(all(c['result']['httpStatus'] is None for c in cases))
        for key in ('cookie','password','token'):
            self.assertNotIn('"'+key+'"',json.dumps(cases))

    def test_missing_duplicate_or_claimed_case_refused(self):
        for kind in ('missing','duplicate','executed'):
            matrix=json.loads((P/'MATRICE-CORRECTIONS-PREPROD.json').read_text())
            if kind=='missing':matrix['sessionCases'].pop()
            elif kind=='duplicate':matrix['sessionCases'].append(matrix['sessionCases'][0])
            else:matrix['sessionCases'][0]['status']='CONFORME'
            with self.assertRaises(ValueError):list(plan.prepare(matrix))


if __name__=='__main__':unittest.main()
