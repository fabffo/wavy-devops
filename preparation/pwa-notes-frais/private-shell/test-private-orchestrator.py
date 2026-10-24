#!/usr/bin/env python3
"""Moteur réel, flock/réservation/V3 réels ; Docker/volumes/DB entièrement simulés."""
from datetime import datetime,timezone
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

P=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('private_engine',P/'release-private.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
LOGICAL_TIME=datetime(2026,10,24,12,0,tzinfo=timezone.utc)
class LogicalDateTime(datetime):
    @classmethod
    def now(cls,tz=None):return LOGICAL_TIME


class Backend:
    def __init__(self,root):
        self.root=root;self.directory=root/'deployments/pwa-release'
        self.events=[];self.fault=None;self.opened=False;self.generation=0
        self.lock_fd=None;self.run_id=None;self.current_plan=None;self.snapshot_count=0
    def hit(self,name):
        self.events.append(name)
        if self.fault==name:raise InterruptedError('fixture')
    def host_guard(self):self.hit('host')
    def identity(self):return 'fixture-sources'
    def select(self,plan):
        self.current_plan=plan;m.op.atomic_json(self.directory/'runtime-plan.json',plan)
    def close_socket(self):self.opened=False;self.hit('unlink-socket')
    def close(self):
        self.close_socket();self.hit('close')
        m.op.atomic_json(self.directory/'edge.json',{'mode':'closed','run':self.run_id,'closureBlocked':False})
    def preflight(self,plan):self.hit('preflight')
    def images(self,plan):self.hit('images')
    def snapshot(self,plan):self.hit('snapshot');self.snapshot_count+=1;return json.loads(json.dumps(plan))
    def barrier(self,plan):self.hit('barrier')
    def provision_storage(self,fd):
        m.public.storage_auth.consume(self.root,self.directory/'runtime-plan.json',self.run_id,self.lock_fd,fd)
        self.hit('provision')
    def storage(self):self.hit('storage')
    def backup(self,baseline=False):
        self.hit('baseline' if baseline else 'backup')
        return {'directory':'backups/preprod/fixture-'+str(baseline),'manifestSha256':'a'*64}
    def verify_backup(self,backup):self.hit('verify-backup')
    def restore(self,backup):
        self.hit('restore')
        return dict(self.proof(['five-databases','contracts-and-notes','hmac','catalogues','document-hashes','notes-permissions']),backup=backup)
    def proof(self,checks):
        return {'run':self.run_id,'planHash':m.fingerprint(self.current_plan),'profile':m.PROFILE,
                'origin':'http://localhost:24443','reviewer':'fixture','checkedAt':LOGICAL_TIME.isoformat(),
                'checks':dict.fromkeys(checks,True)}
    def deploy(self,component,plan,mode):self.hit(mode+'-'+component);self.generation+=1
    def healthy(self,component):self.hit('healthy-'+component)
    def observed(self,component,plan):
        return {'reference':plan['images'][component]['reference'],'imageId':component,'containerId':component}
    def checks(self):self.hit('checks')
    def test_window(self,proof):self.opened=True;self.hit('test-window')


def independent_lock(root,reply):
    try:
        with m.op.Operation(root):reply.send(True)
    except (OSError,ValueError):reply.send(False)
    finally:reply.close()


def interrupted_restore(root,plan,run,reply):
    b=Backend(root);e=m.Engine(b,root/'deployments/pwa-release',plan,root/'deployments/preprod.lock')
    def restore(backup):
        reply.send(True)
        multiprocessing.Event().wait()
    b.restore=restore
    e.run('restore',run_id=run)


class Orchestration(unittest.TestCase):
    def setUp(self):
        for target,name,value in ((m.public,'datetime',LogicalDateTime),
                                  (m.public.storage_auth,'time',SimpleNamespace(time=lambda:LOGICAL_TIME.timestamp())),
                                  (m,'time',SimpleNamespace(time=lambda:LOGICAL_TIME.timestamp()))):
            clock=patch.object(target,name,value);clock.start();self.addCleanup(clock.stop)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.directory=self.root/'deployments/pwa-release'
        self.backend=Backend(self.root);self.plan=m.read_plan()
        self.engine=m.Engine(self.backend,self.directory,self.plan,self.root/'deployments/preprod.lock')
        self.run=self.engine.run('reserve')
        self.backend.select(self.plan)
    def proof(self,checks):return self.backend.proof(checks)
    def call(self,action,proof=None):return self.engine.run(action,proof,self.run)
    def prepare(self):self.call('prepare',self.proof(m.PREREQUISITES))
    def deploy(self):self.prepare();self.call('restore');self.call('deploy')
    def authorization(self):
        return dict(self.proof(['approved-test-session','synthetic-data-only']),
                    backup=self.engine.state['backup'],observed=self.engine.state['observed'])
    def test_full_order_closed_before_mutation_and_test_finally_closes(self):
        self.deploy();self.call('open-test',self.authorization())
        e=self.backend.events
        self.assertLess(e.index('preflight'),e.index('barrier'))
        self.assertLess(e.index('barrier'),e.index('baseline'))
        self.assertLess(e.index('baseline'),e.index('provision'))
        self.assertLess(e.index('provision'),e.index('backup'))
        self.assertLess(e.index('backup'),e.index('restore'))
        self.assertLess(e.index('restore'),e.index('closed-factures-api'))
        deployed=[x for x in e if x.startswith('closed-')]
        self.assertEqual(deployed,['closed-'+c for c in m.ORDER])
        self.assertFalse(self.backend.opened)
        self.assertEqual(self.engine.state['phase'],'tested')
        proof=dict(self.proof(m.FUNCTIONAL),backup=self.engine.state['backup'],observed=self.engine.state['observed'])
        self.call('validate',proof);self.assertEqual(self.engine.state['phase'],'validated')
        self.call('abandon');self.assertFalse(self.engine.reservation.exists())
    def test_every_prepare_failure_stays_reserved_and_closed(self):
        for stage in ('preflight','images','snapshot','barrier','baseline','provision','storage','backup'):
            with self.subTest(stage=stage),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);b=Backend(root);e=m.Engine(b,root/'deployments/pwa-release',self.plan,root/'deployments/preprod.lock')
                run=e.run('reserve');b.select(self.plan);b.fault=stage
                with self.assertRaises(InterruptedError):e.run('prepare',b.proof(m.PREREQUISITES),run)
                self.assertFalse(b.opened);self.assertTrue(e.reservation.exists())
                self.assertEqual(e.state['phase'],'failed')
    def test_v3_claim_is_consumed_before_effect_and_cannot_be_rearmed(self):
        self.backend.fault='provision'
        with self.assertRaises(InterruptedError):self.prepare()
        receipt=m.op.read_private(self.directory/'storage-authorization.json')
        self.assertTrue(receipt['consumed'])
        self.assertEqual(len(list(self.directory.glob('storage-consumed-*'))),1)
        self.assertEqual(self.engine.state['pending'],'provision-storage')
        self.backend.fault=None
        with self.assertRaises(ValueError):self.call('resume',dict(self.proof(['interrupted-effect-inspected']),pending='provision-storage',resumePhase='awaiting-restore'))
        self.call('rollback');self.assertEqual(self.engine.state['phase'],'rolled-back')
    def test_error_or_interruption_during_opening_closes_without_pwa(self):
        self.deploy();self.backend.fault='test-window'
        with self.assertRaises(InterruptedError):self.call('open-test',self.authorization())
        self.assertFalse(self.backend.opened);self.assertTrue(self.engine.state['closureConfirmed'])
        self.assertTrue(self.engine.reservation.exists())
    def test_wrong_owner_and_concurrent_operation_do_not_close_owner(self):
        self.backend.opened=True;before=list(self.backend.events)
        with self.assertRaises(ValueError):self.engine.run('close',run_id='b'*32)
        self.assertEqual(self.backend.events,before);self.assertTrue(self.backend.opened)
        ctx=multiprocessing.get_context('spawn');reader,writer=ctx.Pipe(False)
        process=ctx.Process(target=independent_lock,args=(self.root,writer));process.start();writer.close()
        self.assertTrue(reader.poll(10));self.assertFalse(reader.recv());process.join(10)
        self.assertEqual(process.exitcode,0);reader.close()
    def test_real_flock_blocks_owner_in_independent_process(self):
        # Retirer la réservation uniquement dans cette fixture pour isoler le flock.
        self.engine.reservation.unlink()
        ctx=multiprocessing.get_context('spawn')
        with m.op.Operation(self.root):
            reader,writer=ctx.Pipe(False);p=ctx.Process(target=independent_lock,args=(self.root,writer));p.start();writer.close()
            self.assertTrue(reader.poll(10));self.assertFalse(reader.recv());p.join(10);reader.close()
    def test_restore_required_and_replay_rejected(self):
        self.prepare()
        with self.assertRaises(ValueError):self.call('deploy')
        self.assertNotIn('closed-factures-api',self.backend.events)
    def test_expired_proof_refuses_open_and_never_logs_secrets(self):
        self.deploy();proof=self.authorization();proof['checkedAt']='2000-01-01T00:00:00+00:00'
        proof['secret']='CANARY_PRIVATE_SECRET'
        with self.assertRaises(ValueError):self.call('open-test',proof)
        self.assertNotIn('test-window',self.backend.events)
        self.assertNotIn('CANARY_PRIVATE_SECRET',(self.directory/'journal.jsonl').read_text())
    def test_rollback_failure_stays_closed_then_retry_restores_all(self):
        self.deploy();snapshot=self.engine.state['previous'];self.backend.fault='rollback-pwa'
        with self.assertRaises(InterruptedError):self.call('rollback')
        self.assertFalse(self.backend.opened);self.assertEqual(self.engine.state['phase'],'rollback-failed')
        self.backend.fault=None;self.call('rollback')
        self.assertEqual(self.engine.state['previous'],snapshot)
        self.assertEqual(self.engine.state['phase'],'rolled-back')
        self.call('abandon')
    def test_resume_after_restore_failure_preserves_snapshot_and_requires_inspection(self):
        self.prepare();snapshot=self.engine.state['previous'];self.backend.fault='restore'
        with self.assertRaises(InterruptedError):self.call('restore')
        self.backend.fault=None
        proof=dict(self.proof(['interrupted-effect-inspected']),pending='isolated-restore',resumePhase='awaiting-restore')
        self.call('resume',proof);self.call('restore');self.call('deploy')
        self.assertEqual(self.engine.state['previous'],snapshot);self.assertEqual(self.backend.snapshot_count,1)
    def test_sigkill_durable_restore_can_resume_without_replacing_snapshot(self):
        self.prepare();snapshot=self.engine.state['previous']
        ctx=multiprocessing.get_context('fork');reader,writer=ctx.Pipe(False)
        child=ctx.Process(target=interrupted_restore,args=(self.root,self.plan,self.run,writer))
        child.start();writer.close()
        try:
            self.assertTrue(reader.poll(10));self.assertTrue(reader.recv())
            child.kill();child.join(5)
            state=m.op.read_private(self.directory/'state.json')
            self.assertEqual(state['pending'],'isolated-restore')
            self.assertTrue(self.engine.reservation.exists())
            self.engine=m.Engine(self.backend,self.directory,self.plan,self.root/'deployments/preprod.lock')
            proof=dict(self.proof(['interrupted-effect-inspected']),pending='isolated-restore',resumePhase='awaiting-restore')
            self.call('resume',proof);self.call('restore')
            self.assertEqual(self.engine.state['previous'],snapshot)
        finally:
            if child.is_alive():child.kill();child.join(5)
            reader.close()

    def test_corrupt_owned_state_or_dead_docker_still_closes_socket(self):
        valid=m.op.read_private(self.directory/'state.json')
        self.backend.opened=True
        (self.directory/'state.json').write_text('corrupt')
        with self.assertRaises(ValueError):self.call('close')
        self.assertFalse(self.backend.opened)
        self.assertTrue(self.engine.reservation.exists())
        m.op.atomic_json(self.directory/'state.json',valid)
        self.backend.opened=True;self.backend.fault='host'
        with self.assertRaises(InterruptedError):self.call('close')
        self.assertFalse(self.backend.opened)
        self.assertTrue(self.engine.reservation.exists())

    def test_abandon_refuses_partial_mutation_and_unconfirmed_close(self):
        self.prepare()
        with self.assertRaises(ValueError):self.call('abandon')
        self.assertTrue(self.engine.reservation.exists())
        self.backend.fault='close'
        with self.assertRaises(InterruptedError):self.call('rollback')
        self.assertFalse(self.engine.state['closureConfirmed'])
        self.assertTrue(self.engine.reservation.exists())

if __name__=='__main__':unittest.main()
