#!/usr/bin/env python3
"""Tests statiques isolés : aucun daemon Docker ni service démarré."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import sys
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('config', ROOT/'scripts/preprod_config.py')
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)


def fixture():
    text = (ROOT/'.env.preprod.example').read_text()
    lines = []
    for line in text.splitlines():
        if '=' in line and not line.startswith('#'):
            key, value = line.split('=', 1)
            if 'CHANGE_ME' in value:
                value = '123456789' if key.endswith('SIREN') else 'ci-fiction-only-'+key.lower()+'-0000000000000000'
            line = key+'='+value
        lines.append(line)
    return '\n'.join(lines)+'\n'


class Validation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='wavy-preprod-static-')
        self.root = Path(self.tmp.name)
        self.env = self.root/'fixture.env'
        self.env.write_text(fixture())
        self.env.chmod(0o600)
        (self.root/'versions').mkdir()
        for f in ('versions/preprod.env', 'versions/preprod.digests', 'docker-compose.preprod.yml'):
            shutil.copyfile(ROOT/f, self.root/f)
        config.ROOT = self.root

    def tearDown(self):
        config.ROOT = ROOT
        self.tmp.cleanup()

    def valid(self):
        config.validate(self.env)

    def change(self, before, after):
        self.env.write_text(self.env.read_text().replace(before, after))

    def test_valid_and_inherited_version_ignored(self):
        os.environ['SOCLE_API_VERSION'] = 'latest'
        try:
            self.valid()
        finally:
            del os.environ['SOCLE_API_VERSION']

    def test_reject_secret_placeholder(self):
        self.change('WAVY_SESSION_SECRET=ci-fiction-only-wavy_session_secret-0000000000000000', 'WAVY_SESSION_SECRET=CHANGE_ME')
        with self.assertRaises(ValueError): self.valid()

    def test_reject_bad_digest(self):
        p = self.root/'versions/preprod.digests'
        p.write_text(p.read_text().replace('sha256:', 'sha512:', 1))
        with self.assertRaises(ValueError): self.valid()

    def test_reject_cors_wildcard(self):
        self.change('WAVY_CORS_ALLOWED_ORIGIN_PATTERNS=http://localhost:24443', 'WAVY_CORS_ALLOWED_ORIGIN_PATTERNS=*')
        with self.assertRaises(ValueError): self.valid()

    def test_reject_db_port(self):
        p = self.root/'docker-compose.preprod.yml'
        p.write_text(p.read_text().replace('  socle-postgres:\n', '  socle-postgres:\n    ports: ["127.0.0.1:25432:5432"]\n'))
        with self.assertRaises(ValueError): self.valid()

    def test_reject_external_volume(self):
        p = self.root/'docker-compose.preprod.yml'
        p.write_text(p.read_text().replace('  documents-preprod:\n', '  documents-preprod:\n    name: recette-documents\n    external: true\n'))
        with self.assertRaises(ValueError): self.valid()

    def test_literal_secret(self):
        self.change('WAVY_SESSION_SECRET=ci-fiction-only-wavy_session_secret-0000000000000000', "WAVY_SESSION_SECRET='fictional-$-hash#-secret-00000000000000000000'")
        self.valid()

    def test_https_requires_secure_cookie(self):
        self.change('WAVY_ACCESS_MODE=tunnel', 'WAVY_ACCESS_MODE=https')
        self.change('http://localhost:24443', 'https://preprod.test.invalid')
        with self.assertRaises(ValueError): self.valid()
        self.change('WAVY_COOKIE_SECURE=false', 'WAVY_COOKIE_SECURE=true')
        self.valid()

    def test_reject_document_shared_with_factures(self):
        p = self.root/'docker-compose.preprod.yml'
        p.write_text(p.read_text().replace('  wavy-factures-api-preprod:\n', '  wavy-factures-api-preprod:\n    volumes: [documents-preprod:/app/data]\n'))
        with self.assertRaises(ValueError): self.valid()

    def test_reject_build(self):
        p = self.root/'docker-compose.preprod.yml'
        p.write_text(p.read_text().replace('  socle-postgres:\n', '  socle-postgres:\n    build: .\n'))
        with self.assertRaises(ValueError): self.valid()

    def test_reject_profile(self):
        p = self.root/'docker-compose.preprod.yml'
        p.write_text(p.read_text().replace('preprod,secure', 'recette'))
        with self.assertRaises(ValueError): self.valid()

    def test_reject_shared_version(self):
        p = self.root/'docker-compose.preprod.yml'
        p.write_text(p.read_text().replace('${TIERS_API_VERSION:?required}', '${SOCLE_API_VERSION:?required}'))
        with self.assertRaises(ValueError): self.valid()

    def test_reject_dotenv_code_and_duplicates(self):
        for extra in ['BAD=$(touch forbidden)', 'COMPOSE_PROJECT_NAME=wavy-recette']:
            self.env.write_text(fixture()+'\n'+extra+'\n')
            with self.assertRaises(ValueError): self.valid()
        self.assertFalse((self.root/'forbidden').exists())

    def test_reject_world_readable(self):
        self.env.chmod(0o644)
        with self.assertRaises(ValueError): self.valid()

    def test_compose_config_quiet_explicit(self):
        result = subprocess.run(['docker', 'compose', '--env-file', str(self.env), '--env-file', str(ROOT/'versions/preprod.env'), '-p', 'wavy-preprod', '-f', str(ROOT/'docker-compose.preprod.yml'), 'config', '--quiet'], capture_output=True)
        self.assertEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
