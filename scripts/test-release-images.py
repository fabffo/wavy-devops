#!/usr/bin/env python3
"""Tests sans daemon : rendu Compose réel et précontrôle Docker simulé."""
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
import release_images as release

ROOT = Path(__file__).resolve().parent.parent


class ReleaseImages(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT/'versions', self.root/'versions')
        shutil.copytree(ROOT/'docker/recette-pwa', self.root/'docker/recette-pwa')
        for env in ('recette', 'preprod'):
            shutil.copy(ROOT/f'docker-compose.{env}.yml', self.root)
            text = (ROOT/f'.env.{env}.example').read_text().replace('CHANGE_ME', 'fictional-test-only')
            (self.root/f'.env.{env}').write_text(text)

    def tearDown(self):
        self.tmp.cleanup()

    def test_final_compose_has_exactly_13_pinned_application_images(self):
        for env in ('recette', 'preprod'):
            with self.subTest(env=env):
                versions, digests, images = release.release(self.root, env)
                clean = {k: v for k, v in os.environ.items() if not k.startswith(('COMPOSE_', 'WAVY_'))}
                clean.update(versions | digests)
                result = subprocess.run(['docker', 'compose', '--env-file', str(self.root/f'.env.{env}'),
                    '-f', str(self.root/f'docker-compose.{env}.yml'), 'config', '--format', 'json'],
                    env=clean, capture_output=True, text=True, check=True)
                services = json.loads(result.stdout)['services']
                actual = {c: services[f'wavy-{c}-{env}']['image'] for c in release.COMPONENTS}
                self.assertEqual(actual, images)
                self.assertEqual(len(actual), 13)
                self.assertTrue(all('@sha256:' in image for image in actual.values()))
                self.assertFalse(any('build' in svc for svc in services.values()))

    def test_install_render_transmits_machine_ai_config_without_shell_override_or_secret_output(self):
        # L'installateur appelle ce même chemin Compose, avec les trois env-files.
        path = self.root / '.env.recette'
        original = path.read_text()
        values = {'WAVY_AI_PROVIDER': 'anthropic', 'WAVY_AI_MODEL': 'claude-msi-fixture',
                  'WAVY_AI_API_KEY': 'private-fixture-key', 'WAVY_AI_TIMEOUT_SECONDS': '75',
                  'WAVY_AI_MAX_FILE_SIZE_MB': '12'}
        import re
        for key, value in values.items():
            original, count = re.subn(r'^'+key+r'=.*$', key+"='"+value+"'", original, flags=re.M)
            self.assertEqual(count, 1)
        path.write_text(original)
        with patch.dict(os.environ, {key: 'wrong-inherited-fixture' for key in values}):
            config = release.recette_compose(self.root, ['config', '--format', 'json'], capture=True)
        actual = config['services']['wavy-factures-api-recette']['environment']
        # Pas de valeur de clé dans un éventuel message d'assertion.
        for key, value in values.items():
            self.assertTrue(actual.get(key) == value, key+' not transmitted from machine dotenv')
        path.write_text(original.replace("WAVY_AI_API_KEY='private-fixture-key'", "WAVY_AI_API_KEY="))
        config = release.recette_compose(self.root, ['config', '--format', 'json'], capture=True)
        self.assertTrue(config['services']['wavy-factures-api-recette']['environment']['WAVY_AI_API_KEY'] == '')

    def test_missing_invalid_and_release_mismatch_fail_before_docker(self):
        p = self.root/'versions/recette.digests'
        original = p.read_text()
        for text in (original.replace('SOCLE_API_DIGEST=', '#SOCLE_API_DIGEST='),
                     original.replace('sha256:', 'sha512:', 1)):
            p.write_text(text)
            with patch.object(release.subprocess, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'Digest absent ou invalide'):
                    release.verify(self.root, 'recette')
                run.assert_not_called()
        p.write_text(original)
        _, _, images = release.release(self.root, 'recette')
        with patch.object(release.subprocess, 'run') as run:
            run.return_value.stdout = json.dumps([{'RepoDigests': ['wrong@sha256:'+'0'*64]}])
            with self.assertRaisesRegex(ValueError, 'incompatible avec la release'):
                release.verify(self.root, 'recette')
            self.assertFalse(any('up' in call.args[0] for call in run.call_args_list))

    def test_last_image_failure_prevents_replacement(self):
        _, _, images = release.release(self.root, 'recette')
        calls = []
        def docker(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:2] == ['docker', 'inspect']:
                return subprocess.CompletedProcess(cmd, 1, '', 'No such container')
            if cmd[:3] == ['docker', 'image', 'inspect']:
                pinned = next(i for i in images.values() if i.startswith(cmd[3].split('@')[0]+'@'))
                repo = cmd[3].split('@')[0].rsplit(':', 1)[0]
                digest = pinned.split('@')[1] if 'erp-shell:' not in pinned else 'sha256:'+'0'*64
                return subprocess.CompletedProcess(cmd, 0, json.dumps([{'RepoDigests': [repo+'@'+digest]}]))
            return subprocess.CompletedProcess(cmd, 0)
        with patch.object(release.subprocess, 'run', side_effect=docker):
            with self.assertRaisesRegex(ValueError, 'recette/erp-shell'):
                release.recette_compose(self.root, ['up', '-d'])
        self.assertEqual(sum(c[:3] == ['docker', 'image', 'inspect'] for c in calls), 13)
        self.assertFalse(any(c[:2] == ['docker', 'compose'] for c in calls))

    def test_recette_cache_uses_only_immutable_references_without_tag_pull(self):
        _, _, images = release.release(self.root,'recette')
        calls=[]
        def docker(cmd, **kwargs):
            calls.append(cmd)
            reference=cmd[-1]
            repo,digest=reference.split('@')
            return subprocess.CompletedProcess(cmd,0,json.dumps([{'RepoDigests':[repo.rsplit(':',1)[0]+'@'+digest]}]))
        with patch.object(release.subprocess,'run',side_effect=docker):
            release.verify(self.root,'recette')
        self.assertEqual(len(calls),13)
        self.assertTrue(all(c[:3]==['docker','image','inspect'] and c[3] in images.values() for c in calls))

    def test_historical_build_only_verifies_images(self):
        with patch.object(release, 'verify') as verify, patch.object(release.subprocess, 'run') as run:
            self.assertEqual(release.recette_compose(self.root, ['build']), 0)
            verify.assert_called_once_with(self.root, 'recette')
            run.assert_not_called()

    def test_all_13_checked_before_up_and_shell_cannot_override(self):
        _, _, images = release.release(self.root, 'recette')
        calls = []
        def docker(cmd, **kwargs):
            calls.append(cmd)
            if cmd[:2] == ['docker', 'inspect']:
                return subprocess.CompletedProcess(cmd, 1, '', 'No such container')
            if cmd[:3] == ['docker', 'image', 'inspect']:
                repo = cmd[3].split('@')[0].rsplit(':', 1)[0]
                pinned = next(i for i in images.values() if i.startswith(cmd[3].split('@')[0]+'@'))
                return subprocess.CompletedProcess(cmd, 0, json.dumps([{'RepoDigests': [repo+'@'+pinned.split('@')[1]]}]))
            if cmd[:2] == ['docker', 'compose']:
                self.assertEqual(sum(c[:3] == ['docker', 'image', 'inspect'] for c in calls), 13)
                self.assertEqual(kwargs['env']['SOCLE_API_DIGEST'], images['socle-api'].split('@')[1])
                self.assertIn('--no-build', cmd)
            return subprocess.CompletedProcess(cmd, 0)
        with patch.dict(os.environ, {'SOCLE_API_DIGEST': 'wrong'}), patch.object(release.subprocess, 'run', side_effect=docker):
            self.assertEqual(release.recette_compose(self.root, ['up', '-d']), 0)
        self.assertFalse(any('build' in c for c in calls))

    def run_install_with_sync_policy(self, *, changed, config_changed=(), session=True, operations=None,
                                     migration_result=0, install_result=0, rejected_session=False, proxy=False):
        _, _, images = release.release(self.root, 'recette')
        policy = self.root/'deployments/recette-sync-policy.json'
        policy.parent.mkdir(exist_ok=True)
        policy.write_text(json.dumps({'format': 1, 'contractsVolume': 'fixture-contracts'}))
        policy.chmod(0o600)
        state = policy.with_name('recette-sync.json')
        state.write_text(json.dumps({'phase': 'complete'}))
        state.chmod(0o600)
        if proxy:
            with (self.root/'.env.recette').open('a') as env_file:
                env_file.write('\nWAVY_RECETTE_ANTHROPIC_PROXY=true\n')
            shutil.copytree(ROOT/'docker/recette-anthropic', self.root/'docker/recette-anthropic')
        files = [policy, self.root/'.env.recette', self.root/'docker-compose.recette.yml']
        original = {path: path.read_bytes() for path in files}
        before = {c: {'reference': i, 'id': i.partition('@')[2]} for c, i in images.items()}
        for component in changed:
            before[component] = {'reference': 'fixture:old@sha256:'+'0'*64, 'id': 'fixture-old'}
        calls = []
        run_docker = subprocess.run

        def docker(command, **kwargs):
            if command[:2] == ['docker', 'inspect']:
                if '-f' in command and len(command) == 4 + len(images):
                    self.assertEqual(command[4:], [f'wavy-{c}-recette' for c in images])
                    output = ''.join(f'{("old" if c in config_changed else "no")}-{c} unless-stopped\n' for c in images)
                    return subprocess.CompletedProcess(command, 0, output)
                return subprocess.CompletedProcess(command, 1, '', 'No such container')
            if command[:3] == ['docker', 'image', 'inspect']:
                return subprocess.CompletedProcess(command, 0, images['tresorerie-api'].partition('@')[2])
            if command[:2] == ['docker', 'ps']:
                self.assertIn('label=fr.wavy.delivery.migration=', command[-1])
                calls.append(('cleanup', command))
                return subprocess.CompletedProcess(command, 0, 'fixture-temporary-id\n')
            if command[:2] == ['docker', 'rm']:
                self.assertEqual(command, ['docker', 'rm', '-f', 'fixture-temporary-id'])
                calls.append(('remove', command))
                return subprocess.CompletedProcess(command, 0)
            if '--hash' in command:
                prefix = 'no' if any(arg.endswith('/restart-reference.json') for arg in command) else 'current'
                output = ''.join(f'wavy-{c}-recette {prefix}-{c}\n' for c in images)
                if proxy:
                    output += 'wavy-anthropic-proxy-recette proxy-hash\n'
                return subprocess.CompletedProcess(command, 0, output)
            if command[-3:] == ['ps', '-q', 'wavy-anthropic-proxy-recette']:
                return subprocess.CompletedProcess(command, 0, '')
            verb = next(i for i, arg in enumerate(command) if arg in ('up', 'restart'))
            config = run_docker([*command[:verb], 'config', '--format', 'json'],
                                env=kwargs['env'], capture_output=True, text=True, check=True)
            calls.append((command[verb], command[verb+1:], json.loads(config.stdout)['services']))
            temporary = any(arg.endswith('/migration.json') for arg in command)
            return subprocess.CompletedProcess(command, migration_result if temporary else install_result)

        with patch.dict(os.environ) as env, patch('delivery_batch.validate_session') as validate, \
                patch.object(release, 'verify'), patch.object(release.subprocess, 'run', side_effect=docker):
            if session:
                env['WAVY_DELIVERY_SESSION_FD'] = '51'
            else:
                env.pop('WAVY_DELIVERY_SESSION_FD', None)
            validate.return_value = {'before': before}
            if rejected_session:
                validate.side_effect = ValueError('Sauvegarde de livraison absente')
                with self.assertRaisesRegex(ValueError, 'Sauvegarde de livraison absente'):
                    release.recette_compose(self.root, operations or ['up', '-d', '--wait', '--wait-timeout', '600'])
                self.assertEqual(calls, [])
                return calls
            result = release.recette_compose(self.root, operations or ['up', '-d', '--wait', '--wait-timeout', '600'])
            if session and (not operations or operations[0] == 'up'):
                validate.assert_called_once_with(self.root, 'recette')
            else:
                validate.assert_not_called()

        self.assertEqual(result, migration_result or install_result)
        self.assertEqual({path: path.read_bytes() for path in files}, original)
        return calls

    def test_install_enables_flyway_only_for_replaced_apis_and_recreates_them_normally(self):
        calls = self.run_install_with_sync_policy(changed=['tresorerie-api', 'tresorerie-front'])
        self.assertEqual(len(calls), 2)
        _, migration_args, migration = calls[0]
        self.assertEqual(migration_args[-2:], ['--no-deps', 'wavy-tresorerie-api-recette'])
        self.assertIn('--wait', migration_args)
        self.assertEqual(calls[1][1][-3:], ['--no-deps', 'wavy-tresorerie-api-recette', 'wavy-tresorerie-front-recette'])
        for component in release.COMPONENTS:
            if component.endswith('-api'):
                name = f'wavy-{component}-recette'
                expected = 'true' if component == 'tresorerie-api' else 'false'
                self.assertEqual(migration[name]['environment']['SPRING_FLYWAY_ENABLED'], expected)
                self.assertEqual(calls[1][2][name]['environment']['SPRING_FLYWAY_ENABLED'], 'false')
                self.assertEqual(migration[name]['environment']['SPRING_JPA_HIBERNATE_DDL_AUTO'], 'validate')
        self.assertEqual(migration['wavy-tresorerie-api-recette']['restart'], 'no')
        self.assertNotIn('fr.wavy.delivery.migration', calls[1][2]['wavy-tresorerie-api-recette'].get('labels', {}))

    def test_install_without_api_replacement_keeps_one_compose_start(self):
        calls = self.run_install_with_sync_policy(changed=['tresorerie-front'])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1][-2:], ['--no-deps', 'wavy-tresorerie-front-recette'])
        self.assertEqual(calls[0][2]['wavy-tresorerie-api-recette']['environment']['SPRING_FLYWAY_ENABLED'], 'false')

    def test_install_selects_real_config_change_without_enabling_flyway(self):
        calls = self.run_install_with_sync_policy(changed=[], config_changed=['tresorerie-api'])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1][-2:], ['--no-deps', 'wavy-tresorerie-api-recette'])
        self.assertEqual(calls[0][2]['wavy-tresorerie-api-recette']['environment']['SPRING_FLYWAY_ENABLED'], 'false')

    def test_install_ignores_historical_hash_when_restart_policy_is_already_correct(self):
        self.assertEqual(self.run_install_with_sync_policy(changed=[]), [])

    def test_install_selects_new_proxy_and_factures_without_other_dependencies(self):
        calls = self.run_install_with_sync_policy(changed=[], config_changed=['factures-api'], proxy=True)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1][-3:],
                         ['--no-deps', 'wavy-anthropic-proxy-recette', 'wavy-factures-api-recette'])

    def test_sync_restore_and_restart_keep_flyway_disabled(self):
        for operations, session in ((['up', '-d', '--wait'], False), (['restart'], True)):
            with self.subTest(operations=operations):
                calls = self.run_install_with_sync_policy(changed=['tresorerie-api'], session=session,
                                                          operations=operations)
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0][2]['wavy-tresorerie-api-recette']['environment']['SPRING_FLYWAY_ENABLED'], 'false')

    def test_install_requires_verified_backup_before_enabling_flyway(self):
        self.run_install_with_sync_policy(changed=['tresorerie-api'], rejected_session=True)

    def test_failed_start_removes_only_temporary_containers(self):
        for migration_result, install_result, expected in (
            (1, 0, ['up', 'cleanup', 'remove']),
            (0, 1, ['up', 'up', 'cleanup', 'remove']),
        ):
            with self.subTest(migration=migration_result, install=install_result):
                calls = self.run_install_with_sync_policy(changed=['tresorerie-api'],
                    migration_result=migration_result, install_result=install_result)
                self.assertEqual([call[0] for call in calls], expected)


if __name__ == '__main__':
    unittest.main()
