#!/usr/bin/env python3
import importlib.util,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
P=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('auth',P/'local_auth.py');a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)

class LocalAuthGuards(unittest.TestCase):
 def test_stop_failure_keeps_data_and_reservation_for_recovery(self):
  for stop_failed in (True,False):
   with self.subTest(stop_failed=stop_failed):
    state={'servicesAttempted':True}
    def persist(value):state.clear();state.update(value)
    with patch.object(a,'state',side_effect=lambda:dict(state)),patch.object(a,'persist',side_effect=persist),patch.object(a,'restore_caddy'),patch.object(a,'run',side_effect=a.Refused('STOP_FAILED') if stop_failed else None),patch.object(a,'inspect',return_value={'State':{'Running':True}}),patch.object(a,'cleanup_data') as clean,patch.object(a,'restore_services') as restore:
     with self.assertRaisesRegex(a.Refused,'CLEANUP_INCOMPLETE'):a.cleanup()
     clean.assert_not_called();restore.assert_not_called()
     self.assertEqual(state['phase'],'recovery-required')
     self.assertNotIn('cleanupComplete',state)

 def test_symlink_run_refused_before_any_command(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'real').mkdir();(root/'alias').symlink_to(root/'real',target_is_directory=True)
   with patch.object(a,'run',side_effect=AssertionError('No subprocess')):
    with self.assertRaisesRegex(a.Refused,'PRIVATE_RUN_PATH'):a.execute(root/'alias',root/'alias/authorization.json')

 def test_compose_escaped_dollar_is_compared_as_literal_environment(self):
  obj={'State':{'Running':False},'Config':{'Labels':{'com.docker.compose.project':'wavy-recette'},'Env':['NGINX_ENVSUBST_FILTER=_UPSTREAM$']},'Image':'id','HostConfig':{'PortBindings':{}},'NetworkSettings':{'Networks':{'wavy-recette':{}}},'Mounts':[]}
  base={'image':'pinned','environment':{'NGINX_ENVSUBST_FILTER':'_UPSTREAM$$'}}
  with patch.object(a,'run',return_value=json.dumps([{'Id':'id','Config':{'Env':[]}}]).encode()):a.snapshot_guard(obj,base)

 def test_snapshot_rejects_running_or_foreign_service(self):
  for obj in ({'State':{'Running':True},'Config':{}},{'State':{'Running':False},'Config':{'Labels':{'com.docker.compose.project':'other'}}}):
   with patch.object(a,'run',side_effect=AssertionError('No Docker')):
    with self.assertRaises(a.Refused):a.snapshot_guard(obj,{})

 def test_cleanup_never_marked_complete_when_archive_fails(self):
  state={'baseline':{},'dataCleaned':True,'inputHashes':{},'backupComplete':True}
  def persist(value):state.clear();state.update(value)
  with patch.object(a,'state',side_effect=lambda:dict(state)),patch.object(a,'persist',side_effect=persist),patch.object(a,'restore_caddy'),patch.object(a,'cleanup_data'),patch.object(a,'restore_services'),patch.object(a,'archive_sensitive',side_effect=OSError('fixture')):
   with self.assertRaises(OSError):a.cleanup()
  self.assertIsNot(state.get('cleanupComplete'),True)

 def test_wrong_fixture_ownership_prevents_delete(self):
  state={'prefix':'QA_TEST','baseline':{d:{} for d in a.DATABASES},'users':{'fixture':{'email':'synthetic@example.invalid'}}}
  queries=[]
  def sql(db,text,write=False):
   queries.append(write)
   if 'FROM tenant WHERE code' in text:return '[100,101]'
   if 'json_agg(email)' in text:return '["different@example.invalid"]'
   raise AssertionError('No further SQL or delete')
  with patch.object(a,'state',return_value=state),patch.object(a,'baseline',return_value={}),patch.object(a,'sql',side_effect=sql):
   with self.assertRaisesRegex(a.Refused,'SYNTHETIC_USER_OWNERSHIP'):a.cleanup_data()
  self.assertFalse(any(queries))

 def test_remote_auth_phase_rejected_before_runtime_import(self):
  with patch('sys.argv',['wavy','preprod','auth-test','--run-dir','/tmp/x','--authorization','/tmp/x/authorization.json']),patch.object(a.m,'run',side_effect=AssertionError('No Docker')):
   self.assertEqual(a.m.main(),1)

if __name__=='__main__':unittest.main()
