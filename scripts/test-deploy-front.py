#!/usr/bin/env python3
"""Vérifie le choix du transport HTTP du deploy existant, sans Docker ni VM."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('deploy.sh').read_text()
FUNCTION = SCRIPT[SCRIPT.index('front_http_check() {'):SCRIPT.index('\nif $is_api; then')]


class FrontHttpCheck(unittest.TestCase):
    def check(self, env, isolated=False, fail=False):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'deployments').mkdir()
            if isolated:
                (root / 'deployments/recette-sync-policy.json').write_text('{}')
            code = '''
front_url() { printf 'http://localhost:24201/'; }
docker() { printf 'docker'; printf ' <%s>' "$@"; return "$FAIL"; }
curl() { printf 'curl'; printf ' <%s>' "$@"; return "$FAIL"; }
''' + FUNCTION.replace('>/dev/null 2>&1', '') + '\nfront_http_check\n'
            return subprocess.run(['bash', '-c', code], capture_output=True, text=True,
                                  env={**os.environ, 'env': env, 'ROOT_DIR': folder,
                                       'service': 'wavy-tiers-front-' + env, 'FAIL': str(int(fail))})

    def test_isolated_recette_uses_existing_container_and_internal_http(self):
        result = self.check('recette', True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('docker <exec> <wavy-tiers-front-recette> <wget>', result.stdout)
        self.assertIn('<http://127.0.0.1/>', result.stdout)
        self.assertNotIn('24201', result.stdout)

    def test_local_and_normal_recette_preserve_host_http(self):
        for env in ('local', 'recette'):
            with self.subTest(env=env):
                result = self.check(env)
                self.assertEqual(result.returncode, 0)
                self.assertIn('curl <-fsS>', result.stdout)
                self.assertIn('<http://localhost:24201/>', result.stdout)

    def test_http_failures_are_not_hidden(self):
        for isolated in (True, False):
            self.assertNotEqual(self.check('recette', isolated, True).returncode, 0)

    def test_preprod_still_uses_its_existing_release_engine(self):
        self.assertIn('exec "$SCRIPT_DIR/release-preprod.sh" DEPLOY "$@"', SCRIPT)
        self.assertLess(SCRIPT.index('exec "$SCRIPT_DIR/release-preprod.sh"'), SCRIPT.index('front_http_check()'))


if __name__ == '__main__':
    unittest.main()
