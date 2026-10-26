#!/usr/bin/env python3
"""Interactive/legacy dispatch contracts. Sandbox tools only; no Docker or VM."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
COMMON=r'''
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
BLUE='' GREEN='' RED='' YELLOW='' NC=''
die(){ echo "REFUSED:$*" >&2;exit 1; }
info(){ echo "INFO:$*"; };warn(){ echo "WARN:$*"; };success(){ echo "OK:$*"; }
require_docker(){ :; };ensure_container_running(){ :; }
compose(){ echo "COMPOSE:$*"; }
service_name(){ printf 'wavy-%s-%s' "$1" "$2"; }
db_container(){ printf '%s-db-%s' "$1" "$2"; }
docker(){
 case "$1" in
 inspect) if [[ "$3" == *Health* ]];then echo healthy;else echo running;fi;;
 port) :;;exec) echo configured;;*) echo "UNEXPECTED_DOCKER" >&2;return 98;;
 esac
}
'''
BACKEND=r'''
import json,os,sys
from pathlib import Path
args=sys.argv[1:]
if os.environ.get('MENU_EAT_STDIN'):sys.stdin.read()
with open(os.environ['MENU_TRACE'],'a') as f:f.write(json.dumps(args)+'\n')
if args[0]!='--local-cli':print(json.dumps({'environment':args[0],'vmAccess':False}));sys.exit()
args=args[1:];action=args[0]
if os.environ.get('MENU_FAIL')==action:sys.exit(7)
if '--dry-run' in args:
 print(json.dumps({'required':['pwa','gateway','socle-api'],'wouldStop':['pwa'] if action in ('down','restart') else [],'retainedShared':['gateway','socle-api']}))
elif action=='status':print(json.dumps({'origin':'https://recettelocal.wavyservices.fr','services':{'pwa':{'running':True,'state':'running','health':None},'gateway':{'running':True,'state':'running','health':'healthy'}}}))
else:print(json.dumps({'passed':True,'action':action}))
'''

class MenuTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);scripts=self.root/'scripts';scripts.mkdir()
  shutil.copy(ROOT/'wavy',self.root/'wavy');(scripts/'_common.sh').write_text(COMMON)
  for name in ['doctor','build-local','build-recette','restart-all','logs','backup-db','backup-preprod','restore-db','restore-preprod','stop-all','clean','healthcheck','deploy']+['restart-'+c for c in ['socle-api','tiers-api','contrats-api','factures-api','tresorerie-api','gateway','socle-front','tiers-front','contrats-front','factures-front','tresorerie-front','pwa','erp-shell']]:
   p=scripts/(name+'.sh');p.write_text('#!/usr/bin/env bash\nprintf "SCRIPT:%s:%s:%s\\n" "${0##*/}" "${WAVY_ENV:-none}" "$*"\n');p.chmod(0o700)
  backend=self.root/'preparation/https-msi/wavy_deploy.py';backend.parent.mkdir(parents=True);backend.write_text(BACKEND)
  self.trace=self.root/'trace';self.env=dict(os.environ,MENU_TRACE=str(self.trace))
 def run_menu(self,inputs,**extra):
  r=subprocess.run([str(self.root/'wavy')],input=inputs,text=True,capture_output=True,timeout=8,env=dict(self.env,**extra))
  self.assertEqual(r.returncode,0,r.stdout+r.stderr);return r.stdout+r.stderr
 def calls(self):return [json.loads(line) for line in self.trace.read_text().splitlines()] if self.trace.exists() else []
 def test_eof_and_quit_are_clean(self):
  for data in ('','q\n','0\n'):
   with self.subTest(data=data):self.run_menu(data)
  self.assertFalse(self.calls())
 def test_multiple_modules_and_real_health_format(self):
  out=self.run_menu('1\n4\n2,6,2\nq\n')
  self.assertEqual(self.calls(),[['--local-cli','status','tiers','pwa']]);self.assertIn('healthy',out);self.assertIn('non définie',out)
 def test_full_mode_has_no_module_arguments(self):
  self.run_menu('1\n4\n\nq\n');self.assertEqual(self.calls(),[['--local-cli','status']])
 def test_cancel_stop_only_runs_preview(self):
  out=self.run_menu('1\n2\npwa\nnon\nq\n')
  self.assertEqual(self.calls(),[['--local-cli','down','pwa','--dry-run']]);self.assertIn('partagées conservées',out);self.assertIn('Action annulée',out)
 def test_confirmed_start_uses_existing_cli_after_preview(self):
  self.run_menu('1\n1\n2 4\noui\nq\n')
  self.assertEqual(self.calls(),[['--local-cli','up','tiers','factures','--dry-run'],['--local-cli','up','tiers','factures']])
 def test_build_scope_and_confirmation(self):
  out=self.run_menu('1\n8\npwa\noui\nq\n')
  self.assertIn('SIX fronts',out);self.assertEqual(self.calls()[-1],['--local-cli','up','pwa','--build-frontends'])
 def test_failed_preview_cannot_mutate(self):
  out=self.run_menu('1\n3\npwa\nq\n',MENU_FAIL='restart')
  self.assertEqual(self.calls(),[['--local-cli','restart','pwa','--dry-run']]);self.assertIn('aucune mutation exécutée',out)
 def test_invalid_modules_are_reprompted_without_shell_evaluation(self):
  out=self.run_menu('1\n4\npwa;touch\nall pwa\n4\nq\n')
  self.assertEqual(self.calls(),[['--local-cli','status','factures']]);self.assertEqual(out.count('Sélection invalide'),2)
 def test_navigation_back_main_and_remote_unavailable(self):
  out=self.run_menu('1\n4\nb\nm\n2\n4\nm\n3\n4\nq\n')
  self.assertFalse(self.calls());self.assertIn('https://recette.wavyservices.fr',out);self.assertIn('https://preprod.wavyservices.fr',out);self.assertIn('non interrogé',out)
 def test_remote_plan_is_read_only_existing_command(self):
  self.run_menu('3\n11\nq\n');self.assertEqual(self.calls(),[['preprod','plan']])
 def test_health_reuses_existing_test(self):
  self.run_menu('1\n5\n6\nq\n');self.assertEqual(self.calls(),[['--local-cli','test','pwa']])
 def test_logs_bound_and_validate_input(self):
  self.run_menu('1\n6\n6\ninvalid\n1001\n08\nq\n');self.assertEqual(self.calls(),[['--local-cli','logs','pwa','--tail','8']])
 def test_chrome_test_requires_explicit_confirmation(self):
  self.run_menu('1\n7\n6\n2\noui\nq\n');self.assertEqual(self.calls(),[['--local-cli','test','pwa','--chrome']])
 def test_backup_cancel_and_restore_unavailable(self):
  out=self.run_menu('1\n9\nnon\n\n10\nq\n');self.assertFalse(self.calls());self.assertIn('documents',out);self.assertNotIn('SCRIPT:restore',out)
 def test_failure_does_not_exit_menu(self):
  out=self.run_menu('1\n5\npwa\n\n4\npwa\nq\n',MENU_FAIL='test')
  self.assertIn('échec',out);self.assertEqual(self.calls()[-1],['--local-cli','status','pwa'])
 def test_child_cannot_consume_the_next_menu_inputs(self):
  self.run_menu('1\n5\npwa\n\n4\npwa\nq\n',MENU_EAT_STDIN='1')
  self.assertEqual(self.calls(),[['--local-cli','test','pwa'],['--local-cli','status','pwa']])
 def test_all_historical_commands_dispatch_like_previous_menu_version(self):
  # Replace only the menu block with the repository baseline. All pre-existing CLI
  # functions/guards and usage text remain identical for this compatibility oracle.
  old=subprocess.check_output(['git','show','HEAD:wavy'],cwd=ROOT,text=True)
  current=(ROOT/'wavy').read_text();baseline=current[:current.index('# The interactive UI delegates')]+old[old.index('pause_menu() {'):old.index('\nmain() {')]+current[current.index('\nmain() {'):]
  path=self.root/'wavy-previous-menu';path.write_text(baseline);path.chmod(0o700)
  commands=[['help'],['-h'],['--help'],['status'],['doctor'],['clean'],['ai','recette'],['unknown'],['health'],['restore','preprod'],['restart','local','invalid']]
  for env in ('local','recette','preprod'):
   commands.extend([[verb,env] for verb in ('start','status','health','logs','backup','restore','stop')])
   commands.extend([[verb,env,target] for verb in ('build','restart') for target in ('all','gateway')])
   commands.extend([['logs',env,'factures-api'],['restore',env,'backups/test','--with-documents']])
  for args in commands:
   with self.subTest(command=args):
    actual=subprocess.run([str(self.root/'wavy'),*args],capture_output=True,text=True,env=self.env,timeout=5)
    previous=subprocess.run([str(path),*args],capture_output=True,text=True,env=self.env,timeout=5)
    self.assertEqual((actual.returncode,actual.stdout,actual.stderr),(previous.returncode,previous.stdout,previous.stderr))

if __name__=='__main__':unittest.main()
