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
            if cmd[:3] == ['docker', 'image', 'inspect']:
                pinned = next(i for i in images.values() if i.startswith(cmd[3]+'@'))
                repo = cmd[3].rsplit(':', 1)[0]
                digest = pinned.split('@')[1] if 'erp-shell:' not in pinned else 'sha256:'+'0'*64
                return subprocess.CompletedProcess(cmd, 0, json.dumps([{'RepoDigests': [repo+'@'+digest]}]))
            return subprocess.CompletedProcess(cmd, 0)
        with patch.object(release.subprocess, 'run', side_effect=docker):
            with self.assertRaisesRegex(ValueError, 'recette/erp-shell'):
                release.recette_compose(self.root, ['up', '-d'])
        self.assertEqual(sum(c[:3] == ['docker', 'image', 'inspect'] for c in calls), 13)
        self.assertFalse(any(c[:2] == ['docker', 'compose'] for c in calls))

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
            if cmd[:3] == ['docker', 'image', 'inspect']:
                repo = cmd[3].rsplit(':', 1)[0]
                pinned = next(i for i in images.values() if i.startswith(cmd[3]+'@'))
                return subprocess.CompletedProcess(cmd, 0, json.dumps([{'RepoDigests': [repo+'@'+pinned.split('@')[1]]}]))
            if cmd[:2] == ['docker', 'compose']:
                self.assertEqual(sum(c[:3] == ['docker', 'image', 'inspect'] for c in calls), 13)
                self.assertEqual(kwargs['env']['SOCLE_API_DIGEST'], images['socle-api'].split('@')[1])
                self.assertIn('--no-build', cmd)
            return subprocess.CompletedProcess(cmd, 0)
        with patch.dict(os.environ, {'SOCLE_API_DIGEST': 'wrong'}), patch.object(release.subprocess, 'run', side_effect=docker):
            self.assertEqual(release.recette_compose(self.root, ['up', '-d']), 0)
        self.assertFalse(any('build' in c for c in calls))


if __name__ == '__main__':
    unittest.main()
