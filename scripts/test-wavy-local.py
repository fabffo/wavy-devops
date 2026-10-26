#!/usr/bin/env python3
"""Dependency/ownership contracts for the existing ./wavy entry point; no real stop."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import types
import unittest
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1];HERE=ROOT/'preparation/https-msi'
def load(name,file):
 spec=importlib.util.spec_from_file_location(name,file);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
m=load('cycle_plan',HERE/'wavy_deploy.py');f=load('cycle_runtime',HERE/'local_functional.py');a=load('cycle_auth_test',HERE/'local_auth.py')

class ModuleGraph(unittest.TestCase):
 def test_socle_tiers_cycle_requires_only_two_databases_and_socle_front(self):
  self.assertEqual(m.local_services(['socle']),{'socle-api','tiers-api','socle-postgres','tiers-postgres','socle-front','gateway','erp-shell'})
 def test_factures_includes_contract_backend_but_not_optional_fronts(self):
  nodes=m.local_services(['factures'])
  self.assertTrue({'contrats-api','tiers-api','socle-api','factures-api','factures-front'}.issubset(nodes))
  self.assertNotIn('contrats-front',nodes);self.assertNotIn('tresorerie-api',nodes)
 def test_multi_selection_equals_union(self):
  self.assertEqual(m.local_services(['socle','contrats']),m.local_services(['socle'])|m.local_services(['contrats']))
 def test_pwa_needs_real_backends_not_all_erp_fronts(self):
  nodes=m.local_services(['pwa']);self.assertIn('factures-api',nodes);self.assertNotIn('factures-front',nodes)
 def test_down_socle_preserves_auth_for_factures(self):
  running=m.local_services(['socle','factures']);stop,keep=m.local_stop_plan(['socle'],['socle','factures'],running)
  self.assertEqual(stop,{'socle-front'});self.assertTrue({'socle-api','tiers-api','gateway','erp-shell','socle-postgres'}.issubset(keep))
 def test_unregistered_live_consumer_also_protects_dependency(self):
  stop,keep=m.local_stop_plan(['socle'],['socle'],m.local_services(['socle'])|{'factures-api'})
  self.assertIn('socle-api',keep);self.assertNotIn('socle-api',stop)
 def test_full_stop_covers_all_apps_and_databases_without_deletion(self):
  nodes=m.local_services(m.MODULES);stop,keep=m.local_stop_plan(m.MODULES,m.MODULES,nodes)
  self.assertEqual(stop,nodes);self.assertFalse(keep)
 def test_unknown_module_is_refused(self):
  with self.assertRaises(ValueError):m.local_services(['preprod'])
 def test_optional_proxy_is_lazy_and_preserves_asset_path_query(self):
  config=m.lazy_module_routes(m.shell_config('recettelocal.wavyservices.fr'),{c.upper()+'_FRONT_UPSTREAM':'http://wavy-'+c+'-front-recette/' for c in m.MODULES if c!='pwa'})
  self.assertIn('proxy_pass $wavy_module_socle$uri$is_args$args;',config)
  self.assertIn('rewrite ^/modules/socle/(.*)$ /$1 break;',config)
  self.assertIn('proxy_hide_header WWW-Authenticate;',config);self.assertIn('$wavy_origin_denied',config)

class PermanentPolicy(unittest.TestCase):
 def test_permanent_profile_rejects_remote_domains(self):
  for host in ('recette.wavyservices.fr','preprod.wavyservices.fr','wavyservices.fr'):
   with self.assertRaises(ValueError):m.permanent_local_shell(host)
   with self.assertRaises(ValueError):m.permanent_local_routes(host)
 def test_permanent_pwa_keeps_backend_authorization_and_https(self):
  shell=m.permanent_local_shell('recettelocal.wavyservices.fr');routes=m.permanent_local_routes('recettelocal.wavyservices.fr')
  self.assertIn('auth_request /__local_pwa_authorized;',routes)
  self.assertIn('$private_api_origin/api/notes-frais',routes)
  self.assertIn('alias /etc/nginx/wavy-https/pwa-integration.json',routes)
  self.assertNotIn('gate.sock',routes);self.assertNotIn('$wavy_manual_write_denied',shell)
  self.assertIn('proxy_hide_header WWW-Authenticate;',shell)
  self.assertIn('$wavy_origin_denied',shell);self.assertIn('X-Forwarded-Proto https',routes)
 def test_permanent_runtime_refuses_another_machine_before_docker(self):
  fake=types.SimpleNamespace(m=m,Refused=ValueError)
  def read(path,*args,**kwargs):
   return 'microsoft-standard-WSL2' if str(path).endswith('osrelease') else 'PREPROD'
  with patch.object(Path,'read_text',read),patch.object(m,'run') as docker:
   with self.assertRaisesRegex(ValueError,'MSI/WSL'):f.PermanentLocalCycle(fake)
   docker.assert_not_called()
 def test_deployment_defaults_stay_closed(self):
  self.assertIn('return 404',m.CLOSED)
  self.assertIn('closed.conf',m.shell_config('preprod.wavyservices.fr'))

class RuntimeOperations(unittest.TestCase):
 def fake(self,root):
  c=object.__new__(f.LocalCycle);c.m=m;c.directory=root;c.scope='HTTPS_MANUAL_12_SERVICES_READONLY_NO_FIXTURES';c.components=m.COMPONENTS;c.session={};c.ledger={}
  active=set(m.local_services(m.MODULES));calls=[]
  def run(args,**kw):
   calls.append(args)
   if args[:2]==['docker','stop']:
    active.difference_update(n for n in m.LOCAL_DEPS if c.name(n) in args[2:])
   return b''
  c.a=types.SimpleNamespace(REPO=root,Refused=ValueError,run=run,restore_caddy=Mock(),PROFILE=types.SimpleNamespace(close_gate=Mock()))
  c.running=lambda:set(active);c.roots=lambda running:set(m.MODULES);c.inspect=lambda node:{'State':{'Running':node in active}}
  c.lazy_shell=Mock();c.start=Mock();c.save=Mock()
  return c,calls
 def test_down_pwa_stops_only_pwa_no_database_or_erp(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(m,'run',return_value=b''):
   c,calls=self.fake(Path(tmp));result=c.command('down',['pwa'])
   self.assertEqual(calls,[['docker','stop','wavy-pwa-recette']]);self.assertTrue(result['passed']);self.assertFalse(result['volumesDeleted']);c.a.restore_caddy.assert_not_called()
 def test_restart_shared_tiers_keeps_socle_and_tiers_apis(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(m,'run',return_value=b''):
   c,calls=self.fake(Path(tmp));c.command('restart',['tiers'])
   self.assertEqual(calls,[['docker','stop','wavy-tiers-front-recette']]);c.start.assert_called_once()
 def test_full_down_default_keeps_every_database(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(m,'run',return_value=b''):
   c,calls=self.fake(Path(tmp));c.command('down',list(m.MODULES))
   self.assertEqual(len(calls),1);self.assertEqual(set(calls[0][2:]),{'wavy-'+n+'-recette' for n in m.COMPONENTS})
 def test_explicit_database_stop_still_preserves_shared_ones(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(m,'run',return_value=b''):
   c,calls=self.fake(Path(tmp));c.command('down',['socle'],databases=True)
   self.assertEqual(calls,[['docker','stop','wavy-socle-front-recette']])
 def test_dry_run_performs_no_command(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(m,'run',return_value=b''):
   c,calls=self.fake(Path(tmp));out=c.command('restart',['pwa'],dry_run=True)
   self.assertTrue(out['dryRun']);self.assertFalse(calls);c.start.assert_not_called();c.save.assert_not_called()
 def test_adding_module_records_original_image_for_explicit_restore(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);c=object.__new__(f.LocalCycle);c.directory=root;c.m=m;c.components=('socle-api',)
   c.name=lambda node:'wavy-'+node+'-recette'
   obj={'Image':'sha256:original'};c.inspect=lambda node:obj
   (root/'snapshots.private.json').write_text('{}');(root/'original-runtime.private.json').write_text(json.dumps({'services':{'wavy-contrats-api-recette':{}}}))
   saved={};state={}
   def run(args):
    return json.dumps({'services':{'wavy-contrats-api-recette':{}}} if 'config' in args else [{'RepoDigests':['ghcr.io/fabffo/wavy-contrats-api@sha256:original']}]).encode()
   c.a=types.SimpleNamespace(Refused=ValueError,run=run,compose=lambda:[],PROFILE=types.SimpleNamespace(snapshot_guard=Mock()),save=lambda path,data:saved.update({Path(path).name:data}),state=lambda:state,persist=lambda s:None)
   c.snapshot_components({'contrats-api'})
   c.a.PROFILE.snapshot_guard.assert_called_once_with(obj,{},'wavy-contrats-api-recette')
   self.assertEqual(state['managedComponents'],['socle-api','contrats-api'])
   self.assertIn('wavy-contrats-api-recette',saved['snapshots.private.json'])
   self.assertEqual(saved['original-runtime.private.json']['services']['wavy-contrats-api-recette']['image'],'ghcr.io/fabffo/wavy-contrats-api@sha256:original')
 def test_preview_routes_use_session_gate_and_live_auth_without_global_enable(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);runtime=root/'runtime';runtime.mkdir();template=runtime/'shell.conf.template'
   template.write_text('map x $wavy_manual_write_denied {default 1;}\n'+m.shell_config('recettelocal.wavyservices.fr'))
   c=object.__new__(f.LocalCycle);c.directory=root;c.name=lambda n:'wavy-'+n+'-recette';state={}
   c.a=types.SimpleNamespace(Refused=ValueError,PROFILE=types.SimpleNamespace(private=ROOT/'preparation/pwa-notes-frais/private-shell'),run=Mock(),state=lambda:state,persist=Mock())
   c.pwa_routes();routes=(runtime/'pwa-preview.conf').read_text();shell=template.read_text()
   self.assertIn('auth_request /__private_cookie_gate;',routes);self.assertIn('$private_api_origin/api/auth/session',routes)
   self.assertIn('auth_request /__private_pwa_session;',routes);self.assertIn('@pwa_preview_disabled',routes)
   self.assertIn('map x $wavy_manual_write_denied',shell);self.assertIn('proxy_hide_header WWW-Authenticate;',shell)
   self.assertNotIn('location = /pwa-integration.json { add_header',shell)
   self.assertEqual(state['gateSocketDir'],str(runtime/'gate'))
   self.assertEqual(c.a.run.call_count,1)
 def test_explicit_pwa_close_never_stops_services_or_cleans_data(self):
  with tempfile.TemporaryDirectory() as tmp:
   c,calls=self.fake(Path(tmp));result=c.pwa_close()
   c.a.PROFILE.close_gate.assert_called_once();self.assertFalse(calls)
   self.assertFalse(result['servicesStopped']);self.assertFalse(result['businessDataCleaned'])
 def test_foreign_reservation_not_adopted(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'deployments').mkdir();p=root/'deployments/recette-https-reservation.json';p.write_text(json.dumps({'scope':'OTHER','runDirectory':'/tmp/untrusted'}));p.chmod(0o600);before=p.read_bytes()
   with patch.object(a,'REPO',root):
    with self.assertRaisesRegex(ValueError,'autre opération'):f.LocalCycle(a)
   self.assertEqual(p.read_bytes(),before)

class Compatibility(unittest.TestCase):
 def test_legacy_restart_and_logs_dispatch_still_work(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'scripts').mkdir();shutil.copy(ROOT/'wavy',root/'wavy')
   (root/'scripts/_common.sh').write_text('SCRIPT_DIR="'+str(root/'scripts')+'"\nROOT_DIR="'+str(root)+'"\ndie(){ echo "$*" >&2;exit 1;}\n')
   for name in ('restart-socle-api.sh','logs.sh'):
    p=root/'scripts'/name;p.write_text('#!/usr/bin/env bash\nprintf "legacy:%s:%s\\n" "$WAVY_ENV" "$*"\n');p.chmod(0o700)
   for argv in (['restart','local','socle-api'],['logs','local','factures-api']):
    result=subprocess.run(['bash',str(root/'wavy'),*argv],capture_output=True,text=True)
    self.assertEqual(result.returncode,0,result.stderr);self.assertIn('legacy:local:',result.stdout)
 def test_invalid_local_module_does_not_touch_docker(self):
  result=subprocess.run([str(ROOT/'wavy'),'local','up','invalid'],capture_output=True,text=True)
  self.assertEqual(result.returncode,2);self.assertIn('invalid choice',result.stderr)
 def test_help_describes_both_syntaxes(self):
  result=subprocess.run([str(ROOT/'wavy'),'help'],capture_output=True,text=True)
  self.assertEqual(result.returncode,0);self.assertIn('./wavy local up|down',result.stdout);self.assertIn('./wavy start local|recette',result.stdout)

if __name__=='__main__':unittest.main()
