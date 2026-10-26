#!/usr/bin/env python3
"""Manual handoff must never auto-teardown, even after a partial-start failure."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('manual_auth',HERE/'local_auth.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)

class ManualSessionGuards(unittest.TestCase):
 def test_close_requires_explicit_confirmation_before_any_command(self):
  with patch('sys.argv',['wavy','recettelocal','manual-close','--run-dir','/tmp/no-run','--authorization','/tmp/no-run/authorization.json']),patch.object(a.m,'run',side_effect=AssertionError('No Docker')),contextlib.redirect_stderr(io.StringIO()):
   self.assertEqual(a.m.main(),1)

 def test_partial_start_failure_retains_reservation_without_cleanup(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);repo=root/'repo';repo.mkdir();run=root/'session';run.mkdir(mode=0o700)
   actors=repo/'preparation/pwa-notes-frais/private-shell';actors.mkdir(parents=True)
   (actors/'PLAN-MUTATIONS-RECETTE.json').write_text(json.dumps({'actors':[]}))
   def preflight():a.persist({'phase':'starting','servicesAttempted':True,'baseline':{},'counts':{'requests':0,'logins':0}})
   with patch.dict(sys.modules,{'manual_auth':a}),patch.object(a,'REPO',repo),patch.object(a,'guard',return_value={'fixtureMarker':'0123456789ab'}),patch.object(a,'preflight',side_effect=preflight),patch.object(a,'run',side_effect=AssertionError('No subprocess')),patch.object(a,'cleanup') as cleanup,contextlib.redirect_stdout(io.StringIO()):
    result=a.execute(run,run/'authorization.json',functional='manual')
   cleanup.assert_not_called()
   self.assertFalse(result['passed'])
   self.assertFalse(result['autoCleanup'])
   self.assertTrue(result['reservationRetained'])
   self.assertTrue((repo/'deployments/recette-https-reservation.json').exists())
   state=json.loads((run/'state.private.json').read_text())
   self.assertTrue(state['keepOpen'])
   self.assertEqual(state['phase'],'manual-open-failed')

if __name__=='__main__':unittest.main()
