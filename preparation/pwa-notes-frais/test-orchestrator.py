#!/usr/bin/env python3
"""Tests de la machine d'état avec backend simulé ; aucun conteneur/volume/VM utilisé."""
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

sys.dont_write_bytecode = True
C = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('release', C / 'scripts/release_pwa_preprod.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class MockBackend:
    def __init__(self, plan):
        self.events = []
        self.fail = set()
        self.alive = True
        self.open = False
        self.shell_open = False
        self.refs = {c: i['reference'] for c, i in plan['images'].items()}
        self.generations = dict.fromkeys(release.ORDER, 0)
        self.previous = copy.deepcopy(plan)
        for image in self.previous['images'].values():
            image['digest'] = 'sha256:' + 'b' * 64
            image['reference'] = image['reference'].split('@')[0] + '@' + image['digest']

    def step(self, event):
        self.events.append(event)
        if event in self.fail:
            raise ValueError('SECRET_CANARY_FROM_CHILD_OUTPUT')

    def identity(self): return 'fixture-config-hash'
    def guard(self, plan): self.step('guard')
    def preflight(self, plan): self.step('preflight')
    def images(self, plan): self.step('images')
    def snapshot(self, plan):
        self.step('snapshot')
        return self.previous
    def close(self, readonly=False):
        self.step('close')
        self.open = False
    def allow_notes(self): self.step('allow-notes')
    def open_edge(self, expiry):
        self.step('open-edge')
        if not self.shell_open: raise ValueError('Shell fermé')
        self.open = True
    def storage(self): self.step('storage')
    def backup(self):
        self.step('backup')
        return {'directory':'fixture-only','manifestSha256':'a'*64}
    def deploy(self, component, plan, mode):
        self.step('deploy-' + component + '-' + mode)
        self.refs[component] = plan['images'][component]['reference']
        self.generations[component] += 1
        if component == 'erp-shell':
            self.alive = mode != 'stopped'
            self.shell_open = mode == 'open'
    def healthy(self, component): self.step('healthy-' + component)
    def observed(self, component, plan):
        self.step('observed-' + component)
        if self.refs[component] != plan['images'][component]['reference']:
            raise ValueError('Drift')
        return {'reference': self.refs[component], 'imageId': self.refs[component].split('@')[1],
                'containerId': str(self.generations[component])}
    def stopped_shell(self, plan):
        self.step('stopped-shell')
        if self.alive or self.refs['erp-shell'] != plan['images']['erp-shell']['reference']:
            raise ValueError('Rollback shell non fermé')
    def checks(self): self.step('checks')
    def route(self, mode):
        self.step('route-' + mode)
        if self.open != (mode == 'opened') or (mode == 'opened' and not self.alive):
            raise ValueError('Route incohérente')
    def record(self, plan): self.step('record')


class Orchestration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.plan = json.loads((C / 'release-plan.json').read_text())
        self.backend = MockBackend(self.plan)
        self.engine = release.Engine(self.backend, self.root / 'state', self.plan, self.root / 'preprod.lock')

    def evidence(self, functional=False):
        proof = {'planHash': release.fingerprint(self.plan), 'checkedAt': release.now(), 'reviewer': 'local-test',
                 'checks': {k: True for k in ['restore-five-databases-and-documents', 'https-certificate',
                                             'storage-provisioned', *self.plan['requiredChecks']]}}
        if functional:
            proof.update(run=self.engine.state['run'], observed=copy.deepcopy(self.engine.state['observed']),
                         backup=copy.deepcopy(self.engine.state['backup']))
        return proof

    def prepared(self):
        self.engine.run('prepare', self.evidence())
        self.assertEqual(self.engine.state['phase'], 'prepared')
        self.assertFalse(self.backend.open)

    def validated(self):
        self.prepared()
        self.engine.run('validate', self.evidence(True))

    def test_exact_order_and_explicit_activation(self):
        self.validated()
        self.assertEqual([e for e in self.backend.events if e.startswith('deploy-')],
                         ['deploy-' + c + '-closed' for c in release.ORDER])
        self.assertNotIn('record', self.backend.events)
        self.engine.run('activate')
        self.assertTrue(self.backend.open)
        self.assertEqual(self.engine.state['phase'], 'active')
        self.assertEqual(self.backend.events[-1], 'record')

    def test_prepare_failure_at_every_step_stops_and_never_activates(self):
        stages = ['preflight', 'images', 'snapshot', 'close', 'storage', 'backup', 'checks', 'route-closed']
        stages += [prefix + c + suffix for c in release.ORDER for prefix, suffix in
                   [('deploy-', '-closed'), ('healthy-', ''), ('observed-', '')]]
        for stage in stages:
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as tmp:
                backend = MockBackend(self.plan);backend.fail = {stage}
                engine = release.Engine(backend, Path(tmp) / 'state', self.plan, Path(tmp) / 'lock')
                with self.assertRaises(ValueError):engine.run('prepare', self.evidence())
                if stage != 'close':self.assertFalse(backend.open)
                self.assertNotIn('deploy-erp-shell-open', backend.events)
                self.assertNotIn('record', backend.events)
                self.assertNotIn('SECRET_CANARY', engine.journal.read_text())
                if stage == 'close':self.assertIn('CLOSE_FAILED', engine.journal.read_text())

    def test_activation_requires_prepared_functional_proof(self):
        with self.assertRaises(ValueError):self.engine.run('activate')
        self.prepared()
        with self.assertRaises(ValueError):self.engine.run('activate')
        self.assertFalse(self.backend.open)

    def test_wrong_partial_stale_or_other_run_proof_rejected(self):
        mutations = [lambda e: e.update(planHash='wrong'),
                     lambda e: e.update(run='other-run'),
                     lambda e: e.update(checkedAt='2000-01-01T00:00:00+00:00'),
                     lambda e: e['checks'].update(android=False),
                     lambda e: e.update(observed={}),
                     lambda e: e.update(backup={'manifestSha256':'wrong'})]
        for mutate in mutations:
            with self.subTest(mutation=mutate), tempfile.TemporaryDirectory() as tmp:
                backend = MockBackend(self.plan)
                engine = release.Engine(backend, Path(tmp) / 'state', self.plan, Path(tmp) / 'lock')
                engine.run('prepare', self.evidence())
                old = self.engine;self.engine = engine
                proof = self.evidence(True);mutate(proof)
                self.engine = old
                with self.assertRaises(ValueError):engine.run('validate', proof)
                self.assertFalse(backend.open)

    def test_runtime_drift_invalidates_functional_validation(self):
        self.validated()
        self.backend.generations['pwa'] += 1
        with self.assertRaises(ValueError):self.engine.run('activate')
        self.assertFalse(self.backend.open)

    def test_every_activation_failure_closes_shell(self):
        for stage in ('preflight', 'images', 'storage', 'healthy-pwa', 'observed-pwa',
                      'route-closed', 'deploy-erp-shell-open', 'open-edge', 'checks', 'route-opened', 'record'):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as tmp:
                backend = MockBackend(self.plan)
                engine = release.Engine(backend, Path(tmp) / 'state', self.plan, Path(tmp) / 'lock')
                engine.run('prepare', self.evidence())
                old = self.engine;self.engine = engine
                proof = self.evidence(True);self.engine = old
                engine.run('validate', proof)
                backend.fail = {stage}
                with self.assertRaises(ValueError):engine.run('activate')
                self.assertFalse(backend.open)
                self.assertEqual(engine.state['phase'], 'failed')

    def test_proof_expiring_during_preflight_never_opens(self):
        self.validated()
        checked = datetime.fromisoformat(self.engine.state['validation']['checkedAt'])
        class Clock(datetime):
            current = checked + timedelta(hours=23, minutes=59)
            @classmethod
            def now(cls, tz=None): return cls.current
        original = self.backend.preflight
        def delayed(plan):
            original(plan)
            Clock.current += timedelta(minutes=2)
        with unittest.mock.patch.object(release, 'datetime', Clock), \
             unittest.mock.patch.object(self.backend, 'preflight', side_effect=delayed):
            with self.assertRaises(ValueError): self.engine.run('activate')
        self.assertNotIn('deploy-erp-shell-open', self.backend.events)
        self.assertFalse(self.backend.open)
        self.assertEqual(self.engine.state['phase'], 'failed')

    def test_proof_expiring_during_opening_closes_and_never_records_success(self):
        self.validated()
        checked = datetime.fromisoformat(self.engine.state['validation']['checkedAt'])
        class Clock(datetime):
            current = checked + timedelta(hours=23, minutes=59)
            @classmethod
            def now(cls, tz=None): return cls.current
        original = self.backend.deploy
        def delayed(component, plan, mode):
            original(component, plan, mode)
            if mode == 'open': Clock.current += timedelta(minutes=2)
        with unittest.mock.patch.object(release, 'datetime', Clock), \
             unittest.mock.patch.object(self.backend, 'deploy', side_effect=delayed):
            with self.assertRaises(ValueError): self.engine.run('activate')
        self.assertIn('deploy-erp-shell-open', self.backend.events)
        self.assertNotIn('open-edge', self.backend.events)
        self.assertNotIn('record', self.backend.events)
        self.assertFalse(self.backend.open)
        self.assertEqual(self.engine.state['phase'], 'failed')

    def test_partial_deploy_can_be_rolled_back_completely_without_restore(self):
        self.backend.fail = {'deploy-pwa-closed'}
        with self.assertRaises(ValueError):self.engine.run('prepare', self.evidence())
        self.assertEqual(self.engine.state['completed'], ['factures-api', 'factures-front'])
        self.backend.fail.clear()
        self.engine.run('rollback')
        self.assertEqual(self.engine.state['rollbackCompleted'], release.ORDER)
        self.assertEqual(self.engine.state['phase'], 'rolled-back')
        self.assertFalse(self.backend.open)
        for component in release.ORDER:
            self.assertEqual(self.backend.refs[component], self.backend.previous['images'][component]['reference'])

    def test_partial_rollback_keeps_entry_closed_and_can_be_retried(self):
        self.validated();self.engine.run('activate')
        self.backend.fail = {'deploy-factures-front-closed'}
        with self.assertRaises(ValueError):self.engine.run('rollback')
        self.assertFalse(self.backend.open)
        self.assertEqual(self.engine.state['rollbackCompleted'], ['factures-api', 'pwa'])
        self.assertEqual(self.engine.state['phase'], 'rollback-failed')
        self.backend.fail.clear();self.engine.run('rollback')
        self.assertEqual(self.engine.state['phase'], 'rolled-back')

    def test_rollback_failure_for_each_component_stays_closed(self):
        for component in release.ORDER:
            with self.subTest(component=component), tempfile.TemporaryDirectory() as tmp:
                backend=MockBackend(self.plan)
                engine=release.Engine(backend,Path(tmp)/'state',self.plan,Path(tmp)/'lock')
                engine.run('prepare',self.evidence())
                backend.fail={'deploy-'+component+('-stopped' if component=='erp-shell' else '-closed')}
                with self.assertRaises(ValueError):engine.run('rollback')
                self.assertFalse(backend.open)
                self.assertEqual(engine.state['phase'],'rollback-failed')
                backend.fail.clear();engine.run('rollback')
                self.assertEqual(engine.state['phase'],'rolled-back')

    def test_rollback_recovers_durable_interrupted_state(self):
        self.prepared()
        state=release.private_json(self.engine.path);state['phase']='rolling-back'
        release.write_json(self.engine.path,state)
        restarted=release.Engine(self.backend,self.root/'state',self.plan,self.root/'preprod.lock')
        restarted.run('rollback', run_id=state['run'])
        self.assertEqual(restarted.state['phase'],'rolled-back')
        self.assertFalse(self.backend.open)

    def test_global_lock_excludes_existing_flock_and_other_process(self):
        lock = self.root / 'preprod.lock'
        with release.GlobalLock(lock):
            result = subprocess.run(['flock', '-n', str(lock), 'true'])
            self.assertNotEqual(result.returncode, 0)
            code = 'import fcntl,sys; f=open(sys.argv[1],"a"); fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)'
            result = subprocess.run([sys.executable, '-c', code, str(lock)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            with self.assertRaises(BlockingIOError):self.engine.run('prepare', self.evidence())
            self.assertEqual(self.backend.events, [])  # Le concurrent ne ferme pas le Shell du détenteur.
        self.prepared()

    def test_private_state_and_timestamps_without_secrets(self):
        self.backend.fail = {'backup'}
        with self.assertRaises(ValueError):self.engine.run('prepare', self.evidence())
        self.assertEqual(self.engine.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.engine.journal.stat().st_mode & 0o777, 0o600)
        for line in self.engine.journal.read_text().splitlines():
            event = json.loads(line)
            self.assertIn('+00:00', event['time'])
            self.assertNotIn('SECRET_CANARY', line)
        self.assertNotIn('SECRET_CANARY', self.engine.path.read_text())

    def test_backup_inherits_lock_without_deadlock(self):
        lock = self.root / 'deployments/preprod.lock'
        with release.GlobalLock(lock) as fd:
            script = 'source "$1"; ROOT_DIR="$2"; exec 9<&"$3"; preprod_backup_operation_lock'
            result = subprocess.run(['bash', '-c', script, '_', str(release.ROOT/'scripts/_preprod.sh'),
                                     str(self.root), str(fd)], pass_fds=(fd,), capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotEqual(subprocess.run(['flock','-n',str(lock),'true']).returncode, 0)

    def test_signal_closes_shell_and_snapshot_survives(self):
        with unittest.mock.patch.object(self.backend, 'storage', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):self.engine.run('prepare', self.evidence())
        self.assertFalse(self.backend.open)
        self.assertEqual(self.engine.state['previous'], self.backend.previous)
        self.engine.run('rollback')
        self.assertEqual(self.engine.state['phase'], 'rolled-back')

    def test_child_failure_output_never_leaks(self):
        backend = release.DockerBackend(self.root/'unused.env', self.root)
        result = subprocess.CompletedProcess([], 1, b'SECRET_CANARY_STDOUT', b'SECRET_CANARY_STDERR')
        with unittest.mock.patch.object(release.subprocess,'run',return_value=result):
            with self.assertRaises(ValueError) as error:backend.command(['unused'])
        self.assertNotIn('SECRET_CANARY',str(error.exception))

    def test_persistent_reservation_refuses_second_prepare_after_process_restart(self):
        self.prepared()
        run=self.engine.state['run']
        restarted=release.Engine(self.backend,self.root/'state',self.plan,self.root/'preprod.lock')
        before=list(self.backend.events)
        with self.assertRaises(ValueError):restarted.run('prepare',self.evidence())
        with self.assertRaises(ValueError):restarted.run('validate',self.evidence(True),run_id='b'*32)
        self.assertEqual(self.backend.events,before)
        self.assertEqual(release.private_json(self.engine.reservation)['run'],run)

    def test_resume_preserves_snapshot_and_requires_new_proof(self):
        self.backend.fail={'deploy-pwa-closed'}
        with self.assertRaises(ValueError):self.engine.run('prepare',self.evidence())
        original=copy.deepcopy(self.engine.state['previous']);run=self.engine.state['run']
        self.backend.fail.clear()
        restarted=release.Engine(self.backend,self.root/'state',self.plan,self.root/'preprod.lock')
        restarted.run('resume',run_id=run)
        self.assertEqual(restarted.state['phase'],'prepared')
        self.assertEqual(restarted.state['previous'],original)
        self.assertNotIn('validation',restarted.state)
        with self.assertRaises(ValueError):restarted.run('activate',run_id=run)

    def test_abandon_requires_rollback_and_confirmed_edge_and_is_journaled(self):
        self.prepared();run=self.engine.state['run']
        with self.assertRaises(ValueError):self.engine.run('abandon')
        self.assertTrue(self.engine.reservation.exists())
        self.engine.run('rollback')
        self.backend.fail={'close'}
        with self.assertRaises(ValueError):self.engine.run('abandon')
        self.assertTrue(self.engine.reservation.exists())
        self.backend.fail.clear()
        # Une fermeture échouée conserve les composants restaurés ; refaire rollback pour vérifier le lot.
        self.engine.run('rollback')
        self.engine.run('abandon')
        self.assertFalse(self.engine.reservation.exists())
        self.assertEqual(self.engine.state['phase'],'abandoned')
        self.assertTrue((self.engine.directory/('archive-'+run+'.json')).is_file())
        self.assertIn('abandon-reservation',self.engine.journal.read_text())

    def test_abandon_cannot_release_first_mutation_that_failed_healthcheck(self):
        self.backend.fail={'healthy-factures-api'}
        with self.assertRaises(ValueError):self.engine.run('prepare',self.evidence())
        self.assertEqual(self.engine.state['completed'],[])
        self.assertTrue(self.engine.state['mutationStarted'])
        self.backend.fail.clear()
        with self.assertRaises(ValueError):self.engine.run('abandon')
        self.assertTrue(self.engine.reservation.exists())

    def test_unconfirmed_edge_blocks_activation_and_keeps_reservation(self):
        import contextlib,io
        self.validated();self.backend.fail={'route-opened','close'}
        alert=io.StringIO()
        with contextlib.redirect_stderr(alert),self.assertRaises(ValueError):self.engine.run('activate')
        self.assertIn('ALERTE',alert.getvalue())
        self.assertNotIn('SECRET_CANARY',alert.getvalue())
        self.assertFalse(self.engine.state['closureConfirmed'])
        self.assertTrue(self.engine.reservation.exists())
        self.backend.fail.clear()
        with self.assertRaises(ValueError):self.engine.run('activate')
        self.assertNotIn('record',self.backend.events)

    def test_cli_inactive_by_default(self):
        result = subprocess.run(['bash', str(C / 'scripts/release-pwa-preprod.sh'), 'prepare'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('Candidat inactif', result.stderr)


if __name__ == '__main__':
    unittest.main()
