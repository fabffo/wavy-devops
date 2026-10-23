#!/usr/bin/env python3
"""Barrière native : fichier privé, HTTP local et horloge simulée ; aucun Docker/VM."""
from datetime import datetime,timedelta,timezone
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

sys.dont_write_bytecode=True
C=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('gate',C/'scripts/edge_gate.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class Gate(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'edge.json';self.gate=m.Gate(self.path);self.run='a'*32
        self.expiry=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()

    def test_default_missing_invalid_public_or_symbolic_state_is_closed(self):
        self.assertFalse(self.gate.permits('/check'))
        for value in ('broken-json','[]','{}','{"mode":"other"}'):
            self.path.write_text(value);self.path.chmod(0o600)
            self.assertFalse(self.gate.permits('/check'))
        self.gate.close(self.run);self.gate.confirm_closed();self.gate.open(self.run,self.expiry)
        self.path.chmod(0o644);self.assertFalse(self.gate.permits('/check'))
        self.path.unlink();other=self.path.with_name('other.json');other.write_text('{}');self.path.symlink_to(other)
        self.assertFalse(self.gate.permits('/check'))

    def test_open_requires_confirmed_closure_matching_run_and_recent_proof(self):
        self.gate.close(self.run)
        with self.assertRaises(ValueError):self.gate.open(self.run,self.expiry)
        self.gate.confirm_closed()
        with self.assertRaises(ValueError):self.gate.open('b'*32,self.expiry)
        with self.assertRaises(ValueError):self.gate.open(self.run,'2000-01-01T00:00:00+00:00')
        self.gate.open(self.run,self.expiry);self.assertTrue(self.gate.permits('/check'))

    def test_expiry_is_enforced_on_each_request_even_without_orchestrator_process(self):
        self.gate.close(self.run);self.gate.confirm_closed();self.gate.open(self.run,self.expiry)
        # Recréation du contrôleur = redémarrage du service natif ; aucune suppression du lease.
        restarted=m.Gate(self.path);self.assertTrue(restarted.permits('/check'))
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return datetime.fromisoformat(self.expiry)+timedelta(seconds=1)
        with patch.object(m,'datetime',Clock):self.assertFalse(restarted.permits('/check'))
        self.assertTrue(self.path.exists())

    def test_readonly_is_distinct_from_pwa_closure(self):
        self.gate.close(self.run,readonly=False)
        self.assertTrue(self.gate.permits('/notes-write'))
        self.assertFalse(self.gate.permits('/check'))
        self.gate.close(self.run,readonly=True)
        self.assertFalse(self.gate.permits('/notes-write'))
        self.assertFalse(self.gate.permits('/unknown'))
        self.gate.confirm_closed()
        with self.assertRaises(ValueError):self.gate.allow_notes('b'*32)
        self.gate.allow_notes(self.run)
        self.assertTrue(self.gate.permits('/notes-write'))
        self.assertFalse(self.gate.permits('/check'))

    def test_http_is_read_only_no_cache_and_no_sensitive_logs(self):
        self.gate.close(self.run);self.gate.confirm_closed()
        server=m.ThreadingHTTPServer(('127.0.0.1',0),m.handler(self.gate))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        url='http://127.0.0.1:'+str(server.server_port)
        error_output=io.StringIO()
        with contextlib.redirect_stderr(error_output):
            with self.assertRaises(urllib.error.HTTPError) as result:urllib.request.urlopen(url+'/check')
            self.assertEqual(result.exception.code,403)
            self.gate.open(self.run,self.expiry)
            with urllib.request.urlopen(url+'/check') as response:
                self.assertEqual(response.status,204);self.assertEqual(response.headers['Cache-Control'],'no-store')
            before=self.path.read_bytes()
            for request in (urllib.request.Request(url+'/open?SECRET_CANARY=1'),
                            urllib.request.Request(url+'/check',data=b'SECRET_CANARY',method='POST')):
                with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(request)
            self.assertEqual(self.path.read_bytes(),before)
        self.assertNotIn('SECRET_CANARY',error_output.getvalue())


if __name__=='__main__':unittest.main()
