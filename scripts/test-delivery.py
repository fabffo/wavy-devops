#!/usr/bin/env python3
"""Livraison : rendu réel isolé et garde-fous de provisionnement simulés."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.dont_write_bytecode = True
import delivery_check as delivery
import preprod_config
import recette_pwa as pwa
import recette_storage as storage
from release_images import release, recette_compose

ROOT = Path(__file__).resolve().parent.parent


class Delivery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT/'versions', self.root/'versions')
        shutil.copytree(ROOT/'docker/recette-pwa', self.root/'docker/recette-pwa')
        for env in ('recette','preprod'):
            shutil.copy(ROOT/f'docker-compose.{env}.yml', self.root)
            text = (ROOT/f'.env.{env}.example').read_text().replace('motdepasse_recette','fixture-secret').replace('CHANGE_ME','fixture-secret').replace('WAVY_TIERS_SERVICE_PASSWORD=', 'WAVY_TIERS_SERVICE_PASSWORD=fixture-secret').replace('WAVY_TIERS_SERVICE_USERNAME=', 'WAVY_TIERS_SERVICE_USERNAME=fixture-service')
            if env == 'recette':
                text = text.replace('WAVY_PWA_ENABLED=false','WAVY_PWA_ENABLED=true').replace('WAVY_NOTES_WRITES_ENABLED=false','WAVY_NOTES_WRITES_ENABLED=true').replace('WAVY_FACTURES_JUSTIFICATIFS_VOLUME=','WAVY_FACTURES_JUSTIFICATIFS_VOLUME=fixture-docs')
            path = self.root/f'.env.{env}'; path.write_text(text); path.chmod(0o600)

    def test_real_render_and_release_parity(self):
        state, images = delivery.check_recette(self.root)
        self.assertEqual(state['mode'],'technical')
        self.assertTrue(state['writes'])
        rendered = recette_compose(self.root,['config','--format','json'],capture=True)
        for c in ('factures-api','tresorerie-api'):
            health = rendered['services'][f'wavy-{c}-recette']['healthcheck']
            self.assertEqual(health['start_period'],'2m0s')
            self.assertEqual(health['retries'],18)
        with patch.object(preprod_config,'ROOT',self.root):
            cmd, env = preprod_config.compose_args(self.root/'.env.preprod', ['config','--format','json'])
            config = json.loads(subprocess.check_output(cmd,env=env))
        _, _, preprod = release(self.root,'preprod')
        self.assertEqual(images,preprod)
        delivery.rendered_checks(config,'preprod',preprod)
        config['services']['wavy-gateway-preprod']['environment']['WAVY_CORS_ALLOWED_ORIGIN_PATTERNS']='https://contradiction.invalid'
        with self.assertRaisesRegex(ValueError,'CORS'): delivery.rendered_checks(config,'preprod',preprod)

    def test_machine_duplicates_and_release_overrides_rejected(self):
        path = self.root/'.env.recette'; original = path.read_text()
        for extra in ('\nWAVY_PWA_ENABLED=true','\nGATEWAY_VERSION=0.1.0-abcdef0','\nWAVY_GATEWAY_CORS_ALLOWED_ORIGIN_PATTERNS=https://x'):
            path.write_text(original+extra)
            with self.assertRaises(ValueError): delivery.check_recette(self.root)

    def test_technical_mode_needs_no_fabricated_functional_proof(self):
        _, _, images = release(self.root,'recette')
        values = delivery.machine(self.root)
        state = pwa.policy(self.root,values,images)
        self.assertTrue(state['go'])
        images['gateway'] = images['gateway'].replace('3ff5c3b','abcdef0')
        self.assertTrue(pwa.policy(self.root,values,images)['go'])
        with patch.object(pwa,'preserve_storage') as preserve, patch.object(storage,'check_volume') as check:
            result = pwa.overlay(self.root,values,images,mutation=True)
            preserve.assert_called_once(); check.assert_called_once()
        self.assertIn('notes-write.conf',str(result))
        values['WAVY_FACTURES_JUSTIFICATIFS_VOLUME']=''
        with self.assertRaisesRegex(ValueError,'NO-GO'): pwa.overlay(self.root,values,images)

    def test_render_rejects_exposure_missing_store_wrong_profile_or_digest(self):
        state, images = delivery.check_recette(self.root)
        original = recette_compose(self.root,['config','--format','json'],capture=True)
        mutations = [lambda c: c['services']['wavy-gateway-recette']['ports'][0].update(host_ip='0.0.0.0'),
                     lambda c: c['services']['wavy-gateway-recette']['environment'].update(SPRING_PROFILES_ACTIVE='local'),
                     lambda c: c['services']['wavy-factures-api-recette']['environment'].pop('WAVY_FACTURES_STOCKAGE_JUSTIFICATIFS'),
                     lambda c: c['services']['wavy-pwa-recette'].update(image='mutable:latest')]
        import copy
        for mutation in mutations:
            config = copy.deepcopy(original); mutation(config)
            with self.assertRaises(ValueError): delivery.rendered_checks(config,'recette',images,state['origin'])

    def test_existing_volume_is_never_chowned_or_created(self):
        with patch.object(storage,'run',return_value='existing') as run, patch.object(storage,'check_volume') as check:
            storage.provision('existing','image',allowed=True)
            self.assertEqual(run.call_count,1); check.assert_called_once()

    def test_absent_volume_requires_explicit_initial_provision(self):
        with patch.object(storage,'run',return_value='') as run:
            with self.assertRaisesRegex(ValueError,'autoriser une fois'): storage.provision('new','image')
            self.assertEqual(run.call_count,1)

    def test_initial_provision_changes_only_empty_root(self):
        with patch.object(storage.uuid,'uuid4') as uuid, patch.object(storage,'run',side_effect=['','100 101','new',json.dumps([{'Labels':{'wavy.provision':'fixture-token'}}])]) as run, patch.object(storage,'tool') as tool, patch.object(storage,'check_volume'):
            uuid.return_value.hex='fixture-token'
            storage.provision('new','pinned@sha256:fixture',allowed=True)
            script = tool.call_args.args[2]
            self.assertIn('test -z "$(ls -A',script)
            self.assertIn('chown 100:101 /app/justificatifs;',script)
            self.assertNotIn('-R',script)
            self.assertIn('volume',run.call_args.args[0])

    def test_concurrently_created_volume_never_changes_permissions(self):
        with patch.object(storage,'run',side_effect=['','100 101','new',json.dumps([{'Labels':{}}])]), patch.object(storage,'tool') as tool:
            with self.assertRaisesRegex(ValueError,'concurremment'):
                storage.provision('new','image',allowed=True)
            tool.assert_not_called()

    def test_promotion_requires_real_human_decision_for_same_images(self):
        with self.assertRaises(OSError): delivery.promotion(self.root)
        directory = self.root/'deployments'; directory.mkdir()
        path = directory/'recette-validation.private.json'
        path.write_text(json.dumps({'approved':True,'reviewer':'fixture-human','images':release(self.root,'recette')[2]}));path.chmod(0o600)
        delivery.promotion(self.root)
        proof=json.loads(path.read_text());proof['images'].pop('pwa');path.write_text(json.dumps(proof))
        with self.assertRaisesRegex(ValueError,'Validation fonctionnelle'): delivery.promotion(self.root)

    def test_install_order_and_fail_closed_without_real_docker(self):
        for failure in ('', 'diagnose', 'preflight', 'storage', 'backup', 'up', 'runtime'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); scripts=root/'scripts'; scripts.mkdir(); (root/'deployments').mkdir()
                binary=root/'bin'; binary.mkdir(); log=root/'events'
                shutil.copy(ROOT/'scripts/install.sh',scripts)
                (scripts/'_common.sh').write_text("""set -euo pipefail
ROOT_DIR="$FIXTURE_ROOT"; SCRIPT_DIR="$ROOT_DIR/scripts"
die() { echo "$*" >&2; exit 1; }
success() { :; }
env_value() { case "$2" in WAVY_INSTALL_HOSTNAME) hostname -s;; *) echo 600;; esac; }
require_docker() { :; }; require_command() { :; }; recette_operation_lock() { :; }
compose() { echo up >> "$FIXTURE_LOG"; [[ $FIXTURE_FAIL != up ]]; }
""")
                commands={
                    'python3': '#!/bin/bash\n[[ ${1:-} != -B ]] || shift\naction=${2:-}; echo "$action" >> "$FIXTURE_LOG"; [[ $FIXTURE_FAIL != "$action" ]]\n',
                    'docker': '#!/bin/bash\nif [[ $1 == context ]]; then echo unix:///var/run/docker.sock; fi\n',
                    'git': '#!/bin/bash\nexit 0\n'}
                for name, body in commands.items():
                    path=binary/name;path.write_text(body);path.chmod(0o700)
                backup=scripts/'backup-db.sh'
                backup.write_text('#!/bin/bash\necho backup >> "$FIXTURE_LOG"; [[ $FIXTURE_FAIL != backup ]]\n');backup.chmod(0o700)
                env=dict(os.environ, PATH=str(binary)+':'+os.environ['PATH'], FIXTURE_ROOT=str(root), FIXTURE_LOG=str(log), FIXTURE_FAIL=failure, HOME=str(root))
                result=subprocess.run(['bash',str(scripts/'install.sh'),'recette'],env=env,capture_output=True,text=True)
                events=log.read_text().splitlines()
                expected=['diagnose','preflight','verify','storage','backup','up','migrations','runtime']
                self.assertEqual(events,expected[:expected.index(failure)+1] if failure else expected)
                self.assertEqual(result.returncode == 0,not bool(failure),result.stderr)
                if failure in ('up','runtime'):
                    self.assertIn('KO',(root/'deployments/recette-install.tsv').read_text())

    def test_runtime_cors_requires_exact_https_origin(self):
        origin='https://recette.wavyservices.fr'
        from unittest.mock import MagicMock
        response=MagicMock();response.status=204
        response.headers={'Access-Control-Allow-Origin':origin}
        with patch.object(delivery,'urlopen') as open_url:
            open_url.return_value.__enter__.return_value=response
            delivery.cors_runtime(origin)
            self.assertEqual(open_url.call_args.args[0].method,'OPTIONS')
            response.headers={'Access-Control-Allow-Origin':'*'}
            with self.assertRaisesRegex(ValueError,'CORS'):delivery.cors_runtime(origin)

    def test_cli_refuses_wrong_host_before_mutation(self):
        result=subprocess.run([str(ROOT/'wavy'),'install','recette'],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('WAVY_INSTALL_HOSTNAME',result.stdout+result.stderr)



class GitDeliveryGuard(unittest.TestCase):
    """Vrai Git isolé ; arrêt avant preflight, sans daemon ou données métier."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        scripts = self.root/'scripts'; scripts.mkdir()
        (self.root/'bin').mkdir()
        shutil.copy(ROOT/'scripts/install.sh', scripts)
        shutil.copytree(ROOT/'versions', self.root/'versions')
        for name in ('wavy','docker-compose.recette.yml','docker-compose.preprod.yml'):
            shutil.copy(ROOT/name, self.root/name)
        (self.root/'docker').mkdir()
        (self.root/'docker/fixture.conf').write_text('fixture\n')
        (scripts/'_common.sh').write_text("""set -euo pipefail
ROOT_DIR="$FIXTURE_ROOT"; SCRIPT_DIR="$ROOT_DIR/scripts"
die() { echo "$*" >&2; exit 1; }
env_value() { case "$2" in WAVY_INSTALL_HOSTNAME) hostname -s;; *) echo 600;; esac; }
require_docker() { :; }; require_command() { :; }; recette_operation_lock() { :; }
""")
        commands = {
            'docker': '#!/bin/bash\n[[ $1 == context ]] || exit 99; echo unix:///var/run/docker.sock\n',
            'python3': '#!/bin/bash\n[[ ${1:-} != -B ]] || shift\n[[ $2 != diagnose ]] || exit 0; echo "$2"; exit 73\n'}
        for name, body in commands.items():
            path=self.root/'bin'/name; path.write_text(body); path.chmod(0o700)
        self.git('init','-q')
        self.git('add','.')
        self.git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture')
        self.env = dict(os.environ, PATH=str(self.root/'bin')+':'+os.environ['PATH'],
                        FIXTURE_ROOT=str(self.root), HOME=str(self.root))
        self.env.pop('DOCKER_HOST',None); self.env.pop('DOCKER_CONTEXT',None)

    def git(self, *args):
        return subprocess.check_output(['git','-C',str(self.root),*args],stderr=subprocess.STDOUT)

    def install_guard(self):
        history = {str(p.relative_to(self.root)):p.read_bytes()
                   for p in (self.root/'versions/history').rglob('*') if p.is_file()}
        staged = self.git('diff','--cached','--binary')
        result = subprocess.run(['bash',str(self.root/'scripts/install.sh'),'recette'],
                                env=self.env,capture_output=True,text=True)
        self.assertEqual(history, {str(p.relative_to(self.root)):p.read_bytes()
                         for p in (self.root/'versions/history').rglob('*') if p.is_file()})
        self.assertEqual(staged,self.git('diff','--cached','--binary'))
        return result

    def test_modified_recette_history_reaches_preflight_and_is_preserved(self):
        path=self.root/'versions/history/recette/gateway.tsv'
        for staged in (False,True):
            with self.subTest(staged=staged):
                with path.open('a') as stream:
                    stream.write('0.1.0-abcdef0\tsha256:'+'a'*64+'\tabcdef0\t2026-10-28T10:00:00+01:00\n')
                if staged: self.git('add','versions/history/recette/gateway.tsv')
                result=self.install_guard()
                self.assertEqual(result.returncode,73,result.stderr)
                self.assertEqual(result.stdout.strip(),'preflight')
                self.assertNotIn('non synchronisée',result.stderr)

    def test_dirty_active_manifests_block_even_with_modified_history(self):
        history=self.root/'versions/history/recette/gateway.tsv'
        with history.open('a') as stream: stream.write('# fixture runtime history\n')
        for name in ('versions/recette.env','versions/recette.digests','versions/preprod.env','versions/preprod.digests'):
            path=self.root/name; original=path.read_bytes()
            for staged in (False,True):
                with self.subTest(name=name,staged=staged):
                    path.write_bytes(original+b'\n# unpublished fixture\n')
                    if staged: self.git('add',name)
                    result=self.install_guard()
                    self.assertEqual(result.returncode,1)
                    self.assertIn('Livraison non synchronisée',result.stderr)
                    self.assertEqual(result.stdout,'')
                    path.write_bytes(original)
                    if staged: self.git('add',name)

    def test_scripts_compose_and_other_version_files_remain_strict(self):
        for name in ('wavy','scripts/unpublished.sh','docker/fixture.conf','docker-compose.recette.yml',
                     'docker-compose.preprod.yml','docker-compose.unpublished.yml',
                     'versions/unknown.env','versions/history/recette/unknown.tsv',
                     'versions/history/preprod/gateway.tsv'):
            with self.subTest(name=name):
                path=self.root/name; original=path.read_bytes() if path.exists() else None
                path.write_bytes((original or b'')+b'\n# unpublished fixture\n')
                result=self.install_guard()
                self.assertEqual(result.returncode,1)
                self.assertIn('Livraison non synchronisée',result.stderr)
                self.assertEqual(result.stdout,'')
                if original is None: path.unlink()
                else: path.write_bytes(original)

    def test_runtime_history_digest_conflict_is_still_rejected(self):
        versions, _, _ = release(self.root,'recette')
        path=self.root/'versions/history/recette/gateway.tsv'
        with path.open('a') as stream:
            stream.write(versions['GATEWAY_VERSION']+'\tsha256:'+'0'*64+'\tfixture\t2026-10-28T10:00:00+01:00\n')
        with self.assertRaisesRegex(ValueError,'Digest incompatible avec la release'):
            release(self.root,'recette')

    def test_git_failure_blocks_before_preflight(self):
        executable=self.root/'bin/git'; executable.write_text('#!/bin/bash\nexit 128\n'); executable.chmod(0o700)
        result=self.install_guard()
        self.assertEqual(result.returncode,1)
        self.assertIn('Impossible de vérifier',result.stderr)
        self.assertEqual(result.stdout,'')

if __name__ == '__main__': unittest.main()
