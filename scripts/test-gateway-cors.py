#!/usr/bin/env python3
"""Rendu Compose isolé : même origine effective pour Gateway et les cinq APIs."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.dont_write_bytecode = True
import preprod_config
import release_images

ROOT = Path(__file__).resolve().parent.parent


class GatewayCors(unittest.TestCase):
    def test_reference_and_machine_origin_are_shared_without_shell_override(self):
        for env in ('recette', 'preprod'):
            for custom in (False, True, None):
                if env == 'preprod' and custom is None:
                    continue
                with self.subTest(env=env, custom=custom), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    shutil.copytree(ROOT/'versions', root/'versions')
                    shutil.copytree(ROOT/'docker/recette-pwa', root/'docker/recette-pwa')
                    shutil.copy(ROOT/f'docker-compose.{env}.yml', root)
                    text = (ROOT/f'.env.{env}.example').read_text().replace('CHANGE_ME', 'fictional')
                    if custom or custom is None:
                        text = '\n'.join(line for line in text.splitlines() if not line.startswith('WAVY_CORS_ALLOWED_ORIGIN_PATTERNS='))
                        if custom:
                            text += f'\nWAVY_CORS_ALLOWED_ORIGIN_PATTERNS=https://{env}.wavyservices.fr\n'
                    path = root/f'.env.{env}'
                    path.write_text(text)
                    real_run = subprocess.run
                    rendered = []
                    def render(cmd, **kwargs):
                        result = real_run(cmd, **kwargs, capture_output=True, text=True, check=True)
                        import json
                        rendered.append(json.loads(result.stdout))
                        return result
                    with patch.dict(os.environ, {'WAVY_CORS_ALLOWED_ORIGIN_PATTERNS': 'https://untrusted.invalid'}):
                        if env == 'recette':
                            with patch.object(release_images.subprocess, 'run', side_effect=render):
                                release_images.recette_compose(root, ['config', '--format', 'json'])
                        else:
                            with patch.object(preprod_config, 'ROOT', root):
                                cmd, clean = preprod_config.compose_args(path, ['config', '--format', 'json'])
                                render(cmd, env=clean)
                    services = rendered[0]['services']
                    origins = {services[f'wavy-{c}-{env}']['environment']['WAVY_CORS_ALLOWED_ORIGIN_PATTERNS']
                               for c in ('gateway', 'socle-api', 'tiers-api', 'contrats-api', 'factures-api', 'tresorerie-api')}
                    self.assertEqual(len(origins), 1)
                    origin = origins.pop()
                    self.assertNotIn('*', origin)
                    self.assertNotIn('untrusted', origin)
                    if custom:
                        self.assertEqual(origin, f'https://{env}.wavyservices.fr')
                    elif env == 'recette':
                        self.assertIn('https://recette.wavyservices.fr', origin.split(','))
                    else:
                        self.assertEqual(origin, 'http://localhost:24443')

    def test_origins_are_not_pinned_in_version_manifest(self):
        self.assertNotIn('CORS', (ROOT/'versions/recette.env').read_text())
        self.assertNotIn('WAVY_GATEWAY_CORS_ALLOWED_ORIGIN_PATTERNS', (ROOT/'docker-compose.recette.yml').read_text())

    def test_historical_starter_uses_shared_cli(self):
        text = (ROOT/'scripts/start-docker-recette.sh').read_text()
        self.assertIn('exec "$ROOT_DIR/wavy" start recette', text)
        self.assertNotIn('--build', text)
        self.assertNotIn('mvnw', text)


if __name__ == '__main__':
    unittest.main()
