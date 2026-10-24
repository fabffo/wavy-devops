#!/usr/bin/env python3
"""Consommateurs réellement forkés : copies du jeton, FD communs/indépendants, SIGKILL et rejeu."""
import fcntl
from datetime import datetime, timezone
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
C = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


fixtures = load(C/'test-storage-security.py', 'concurrency_fixtures')


def consumer(root, plan, run, inherited, token_fd, reply, start, snapshots, independent, interrupt, logical_time):
    m = load(os.environ.get('WAVY_TEST_AUTH_SOURCE', str(C/'scripts/storage_authorization.py')), 'process_authorization')
    m.time.time = lambda: logical_time
    fd = os.open(root/'deployments/preprod.lock', os.O_RDWR) if independent else inherited
    try:
        original = m.operation.read_private
        def read(path):
            data = original(path)
            if Path(path).name == 'storage-authorization.json' and snapshots is not None:
                # Tous ont lu le même reçu AVANT la transition terminale : ancien défaut déterministe.
                snapshots.wait(timeout=10)
            return data
        m.operation.read_private = read
        def halt():
            reply.send({'point':interrupt})
            # Synchronisation explicite, aucun sleep ni fenêtre temporelle supposée.
            multiprocessing.Event().wait()
        if interrupt in ('before-claim', 'after-claim'):
            original_claim = m.claim_once
            def claim(*args):
                if interrupt == 'before-claim': halt()
                result = original_claim(*args)
                if interrupt == 'after-claim': halt()
                return result
            m.claim_once = claim
        if interrupt == 'during-claim-fsync':
            m.os.fsync = lambda fd: halt()
        start.wait(timeout=10)
        m.consume(root, plan, run, fd, token_fd)
        reply.send({'accepted':True})
        if interrupt == 'after-consume': multiprocessing.Event().wait()
    except Exception as error:
        reply.send({'accepted':False, 'error':type(error).__name__})
    finally:
        if independent: os.close(fd)
        reply.close()


class ConsumptionConcurrency(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.AuthorizationSecurity(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.ctx = multiprocessing.get_context('fork')
        self.current = datetime(2026,10,24,12,0,tzinfo=timezone.utc).timestamp()
        state_path = self.fixture.directory/'state.json'
        state = fixtures.auth.operation.read_private(state_path)
        state['storagePreconditions']['checkedAt'] = self.current
        state['prerequisites']['checkedAt'] = datetime.fromtimestamp(self.current,timezone.utc).isoformat()
        fixtures.auth.operation.atomic_json(state_path,state)
        clock = patch.object(fixtures.auth.time,'time',return_value=self.current)
        self.logical_clock = clock.start(); self.addCleanup(clock.stop)
        self.fd = self.fixture.ticket()
        self.token = os.read(self.fd, 32)

    def children(self, count, independent=False, interrupt=None):
        t = self.fixture
        if independent:
            fcntl.flock(t.lock.fd, fcntl.LOCK_UN)
        start = self.ctx.Barrier(count+1)
        snapshots = None if independent or interrupt else self.ctx.Barrier(count)
        jobs = []
        for unused in range(count):
            reader, writer = os.pipe(); os.write(writer, self.token); os.close(writer)
            parent, child = self.ctx.Pipe(duplex=False)
            process = self.ctx.Process(target=consumer, args=(t.root,t.plan,t.run,t.lock.fd,reader,child,
                                                             start,snapshots,independent,interrupt,self.current))
            process.start(); child.close(); os.close(reader)
            jobs.append((process,parent))
            self.addCleanup(self.cleanup_process,process,parent)
        start.wait(timeout=10)
        return jobs

    @staticmethod
    def cleanup_process(process, pipe):
        if process.is_alive(): process.kill()
        process.join(timeout=5); pipe.close()

    def results(self, jobs):
        out = []
        for process, pipe in jobs:
            self.assertTrue(pipe.poll(10), 'Consommateur sans résultat')
            out.append(pipe.recv())
            process.join(timeout=10)
            self.assertFalse(process.is_alive())
            self.assertEqual(process.exitcode,0)
        return out

    def race(self, count, independent=False, expected=1):
        out = self.results(self.children(count, independent))
        successes = sum(r.get('accepted') is True for r in out)
        self.assertLessEqual(successes,1,out)
        self.assertEqual(successes,expected,out)
        return out

    def test_two_consumers_shared_inherited_fd(self): self.race(2)
    def test_ten_consumers_shared_inherited_fd(self): self.race(10)
    def test_two_consumers_independently_opened_fd(self): self.race(2,independent=True)
    def test_ten_consumers_independently_opened_fd(self): self.race(10,independent=True)

    def test_replay_after_process_restart(self):
        envelope=self.fixture.directory/'storage-authorization.json'
        pending=json.loads(envelope.read_text())
        self.race(2)
        # Nouveaux processus et nouveaux pipes contenant exactement le même jeton.
        self.race(2,expected=0)
        # Même une ancienne enveloppe encore valide ne réarme pas le reçu terminal.
        self.fixture.fixture.operation.atomic_json(envelope,pending)
        self.race(2,expected=0)
        self.assertEqual(len(list(self.fixture.directory.glob('storage-consumed-*.json'))),1)

    def test_invalid_expired_or_other_run_has_no_winner(self):
        path = self.fixture.directory/'storage-authorization.json'
        original = path.read_bytes()
        for kind in ('modified','expired','other-run'):
            with self.subTest(kind=kind):
                data = json.loads(original)
                if kind == 'modified': data['stateHash']='0'*64
                elif kind == 'expired': data.update(issuedAt=time.time()-62,expiresAt=time.time()-2)
                else: data['run']='b'*32
                self.fixture.fixture.operation.atomic_json(path,data)
                self.race(2,expected=0)
        self.assertFalse(list(self.fixture.directory.glob('storage-consumed-*.json')))

    def test_fsync_failures_never_authorize_or_rearm(self):
        for scope in ('file','directory'):
            with self.subTest(scope=scope):
                fd=self.fixture.ticket();self.token=os.read(fd,32)
                reader,writer=os.pipe();os.write(writer,self.token);os.close(writer)
                try:
                    target=fixtures.auth.os if scope=='file' else fixtures.auth.operation
                    name='fsync' if scope=='file' else 'sync_directory'
                    with patch.object(target,name,side_effect=OSError('fixture fsync failure')):
                        with self.assertRaises(OSError):self.fixture.consume(reader)
                finally:os.close(reader)
                # L'enveloppe reste pending, le reçu exclusif suffit à interdire tout rejeu.
                self.assertEqual(fixtures.auth.operation.read_private(self.fixture.directory/'storage-authorization.json')['action'],
                                 'provision-storage')
                self.race(2,expected=0)
        self.assertEqual(len(list(self.fixture.directory.glob('storage-consumed-*.json'))),2)

    def test_expiry_during_durable_transition_burns_without_authorizing(self):
        original=fixtures.auth.operation.sync_directory
        expires=fixtures.auth.operation.read_private(self.fixture.directory/'storage-authorization.json')['expiresAt']
        def sync_then_expire(path):
            original(path)
            self.logical_clock.return_value=expires+1
        reader,writer=os.pipe();os.write(writer,self.token);os.close(writer)
        try:
            with patch.object(fixtures.auth.operation,'sync_directory',side_effect=sync_then_expire):
                with self.assertRaisesRegex(ValueError,'expirée pendant'):
                    self.fixture.consume(reader)
        finally:os.close(reader)
        # Remettre l'horloge de la simulation ne peut pas réarmer le reçu terminal.
        self.logical_clock.return_value=self.current
        self.race(2,expected=0)
        self.assertEqual(len(list(self.fixture.directory.glob('storage-consumed-*.json'))),1)

    def interrupted(self, point, claimed, authorized=False):
        process,pipe = self.children(1,interrupt=point)[0]
        self.assertTrue(pipe.poll(10))
        result=pipe.recv()
        self.assertEqual(result,{'accepted':True} if authorized else {'point':point})
        process.kill();process.join(timeout=5)
        self.assertFalse(process.is_alive())
        self.assertEqual(process.exitcode,-9)
        traces=list(self.fixture.directory.glob('storage-consumed-*.json'))
        self.assertEqual(len(traces),int(claimed))
        self.race(2,expected=0 if claimed else 1)
        # Les reçus terminaux survivent aux erreurs et ne sont jamais effacés pour permettre le rejeu.
        self.assertEqual(len(list(self.fixture.directory.glob('storage-consumed-*.json'))),1)

    def test_interruption_before_claim(self): self.interrupted('before-claim',False)
    def test_interruption_after_durable_claim(self): self.interrupted('after-claim',True)
    def test_interruption_during_claim_fsync(self): self.interrupted('during-claim-fsync',True)
    def test_interruption_after_consumption(self): self.interrupted('after-consume',True,authorized=True)


if __name__=='__main__':unittest.main()
