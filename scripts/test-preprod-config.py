#!/usr/bin/env python3
"""Tests statiques isolés : aucun daemon Docker ni service démarré."""
import contextlib
import io
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
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

    def set_ai(self, values):
        lines = self.env.read_text().splitlines()
        self.env.write_text('\n'.join(
            line.split('=', 1)[0]+'='+values[line.split('=', 1)[0]]
            if line.split('=', 1)[0] in values else line for line in lines)+'\n')

    def enable_ai(self):
        self.set_ai({'WAVY_AI_PROVIDER': 'anthropic',
                     'WAVY_AI_MODEL': 'claude-sonnet-4-5-20250929',
                     'WAVY_AI_API_KEY': 'fictional-ai-key-only'})

    def test_ai_optional_and_defaults_ignore_shell(self):
        self.env.write_text('\n'.join(line for line in self.env.read_text().splitlines()
                                      if not line.startswith('WAVY_AI_'))+'\n')
        with patch.dict(os.environ, {key: 'inherited-invalid' for key in config.AI_DEFAULTS}):
            self.valid()
            env = config.render(self.env)['services']['wavy-factures-api-preprod']['environment']
        for key, value in config.AI_DEFAULTS.items():
            self.assertEqual(env[key], value)

    def test_ai_alignment_and_no_secret_output(self):
        self.enable_ai()
        for enabled in ('false', 'true'):
            self.set_ai({'WAVY_AI_ACHAT_AUTO_CREATION_ENABLED': enabled})
            output = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                self.valid()
            self.assertNotIn('fictional-ai-key-only', output.getvalue())
        for confidence in ('0', '1', '0.90'):
            self.set_ai({'WAVY_AI_ACHAT_MINIMUM_CONFIDENCE': confidence})
            self.valid()

    def test_ai_partial_credentials_and_auto_without_ai_rejected(self):
        original = self.env.read_text()
        for key in ('WAVY_AI_PROVIDER', 'WAVY_AI_MODEL', 'WAVY_AI_API_KEY',
                    'WAVY_AI_ACHAT_AUTO_CREATION_ENABLED'):
            self.env.write_text(original)
            self.set_ai({key: 'true' if key.endswith('ENABLED') else 'fictional-ai-key-only'})
            with patch.object(config, 'render') as render:
                with self.assertRaises(ValueError) as error: self.valid()
                self.assertNotIn('fictional-ai-key-only', str(error.exception))
                render.assert_not_called()

    def test_ai_whitespace_credentials_rejected(self):
        self.set_ai({'WAVY_AI_PROVIDER': "'   '"})
        with self.assertRaisesRegex(ValueError, 'requis ensemble'): self.valid()

    def test_ai_compose_failure_masks_secret(self):
        self.enable_ai()
        failure = subprocess.CompletedProcess([], 1, b'fictional-ai-key-only',
                                              b'fictional-ai-key-only')
        with patch.object(config.subprocess, 'run', return_value=failure):
            with self.assertRaises(ValueError) as error: self.valid()
        self.assertNotIn('fictional-ai-key-only', str(error.exception))

    def test_ai_invalid_parameters_rejected_before_compose(self):
        original = self.env.read_text()
        cases = {
            'WAVY_AI_TIMEOUT_SECONDS': ('', '0', '-1', '1.5', 'NaN', 'bad'),
            'WAVY_AI_MAX_FILE_SIZE_MB': ('', '0', '-10', '1.5', 'Infinity', 'bad'),
            'WAVY_AI_ACHAT_AUTO_CREATION_ENABLED': ('', 'TRUE', '1', 'yes'),
            'WAVY_AI_ACHAT_MINIMUM_CONFIDENCE': ('', '-0.1', '1.01', 'NaN', 'Infinity', 'bad'),
        }
        for key, values in cases.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    self.env.write_text(original)
                    self.set_ai({key: value})
                    with patch.object(config, 'render') as render:
                        with self.assertRaisesRegex(ValueError, key): self.valid()
                        render.assert_not_called()

    def test_ai_propagation_and_isolation_enforced(self):
        self.enable_ai()
        p = self.root/'docker-compose.preprod.yml'
        original = p.read_text()
        for key in config.AI_DEFAULTS:
            with self.subTest(key=key):
                p.write_text(original.replace('"${'+key+':-'+config.AI_DEFAULTS[key]+'}"', '"wrong"'))
                with self.assertRaisesRegex(ValueError, key) as error: self.valid()
                self.assertNotIn('fictional-ai-key-only', str(error.exception))
        p.write_text(original.replace('x-backend-environment: &backend-environment\n',
                                     'x-backend-environment: &backend-environment\n  WAVY_AI_PROVIDER: anthropic\n'))
        with self.assertRaisesRegex(ValueError, 'réservés à Factures'): self.valid()

    def test_reject_secret_placeholder(self):
        self.change('WAVY_SESSION_SECRET=ci-fiction-only-wavy_session_secret-0000000000000000', 'WAVY_SESSION_SECRET=CHANGE_ME')
        with self.assertRaises(ValueError): self.valid()

    def test_platform_admin_absent_defaults_to_false(self):
        key = 'WAVY_BOOTSTRAP_PLATFORM_ADMIN_ENABLED'
        self.change(key+'=false\n', '')
        # Une variable héritée ne doit pas activer le privilège à la place du dotenv.
        with patch.dict(os.environ, {key: 'true'}):
            self.valid()
            services = config.render(self.env)['services']
        self.assertEqual(services['wavy-socle-api-preprod']['environment'][key], 'false')

    def test_platform_admin_false_and_true_reach_socle(self):
        key = 'WAVY_BOOTSTRAP_PLATFORM_ADMIN_ENABLED'
        original = self.env.read_text()
        for bootstrap in ('false', 'true'):
            for platform in ('false', 'true'):
                with self.subTest(bootstrap=bootstrap, platform=platform):
                    self.env.write_text(original.replace('WAVY_BOOTSTRAP_ENABLED=false',
                                                        'WAVY_BOOTSTRAP_ENABLED='+bootstrap)
                                       .replace(key+'=false', key+'='+platform))
                    with patch.dict(os.environ, {key: 'true' if platform == 'false' else 'false'}):
                        self.valid()
                        services = config.render(self.env)['services']
                    self.assertEqual(services['wavy-socle-api-preprod']['environment'][key], platform)
                    self.assertEqual([name for name, svc in services.items()
                                      if key in svc.get('environment', {})], ['wavy-socle-api-preprod'])

    def test_platform_admin_rejects_non_boolean_values(self):
        key = 'WAVY_BOOTSTRAP_PLATFORM_ADMIN_ENABLED'
        original = self.env.read_text()
        for value in ('', 'TRUE', 'False', '1', '0', 'yes', 'no', 'invalid', "' true '"):
            with self.subTest(value=value):
                self.env.write_text(original.replace(key+'=false', key+'='+value))
                with patch.object(config, 'render') as render:
                    with self.assertRaisesRegex(ValueError, key): self.valid()
                    render.assert_not_called()

    def test_platform_admin_must_reach_socle_unchanged(self):
        key = 'WAVY_BOOTSTRAP_PLATFORM_ADMIN_ENABLED'
        p = self.root/'docker-compose.preprod.yml'
        original = p.read_text()
        line = f'      {key}: "${{{key}:-false}}"\n'
        for replacement in ('', f'      {key}: "true"\n'):
            with self.subTest(replacement=replacement):
                p.write_text(original.replace(line, replacement))
                with self.assertRaisesRegex(ValueError, key): self.valid()

    def test_platform_admin_cannot_be_sent_to_other_services(self):
        key = 'WAVY_BOOTSTRAP_PLATFORM_ADMIN_ENABLED'
        p = self.root/'docker-compose.preprod.yml'
        p.write_text(p.read_text().replace('x-backend-environment: &backend-environment\n',
                                          f'x-backend-environment: &backend-environment\n  {key}: "false"\n'))
        with self.assertRaisesRegex(ValueError, 'réservé au Socle'): self.valid()

    def test_bootstrap_names_required_when_enabled(self):
        self.change('WAVY_BOOTSTRAP_ENABLED=false', 'WAVY_BOOTSTRAP_ENABLED=true')
        original = self.env.read_text()
        for key in ('WAVY_BOOTSTRAP_ADMIN_FIRST_NAME', 'WAVY_BOOTSTRAP_ADMIN_LAST_NAME'):
            line = key+'=ci-fiction-only-'+key.lower()+'-0000000000000000\n'
            for value in (None, '', "'   '", 'CHANGE_ME'):
                with self.subTest(key=key, value=value):
                    replacement = '' if value is None else key+'='+value+'\n'
                    self.env.write_text(original.replace(line, replacement))
                    with self.assertRaisesRegex(ValueError, key): self.valid()
        self.env.write_text(original)
        self.valid()

    def test_bootstrap_names_optional_when_disabled(self):
        original = self.env.read_text()
        for value in (None, ''):
            with self.subTest(value=value):
                text = original
                for key in ('WAVY_BOOTSTRAP_ADMIN_FIRST_NAME', 'WAVY_BOOTSTRAP_ADMIN_LAST_NAME'):
                    line = key+'=ci-fiction-only-'+key.lower()+'-0000000000000000\n'
                    text = text.replace(line, '' if value is None else key+'=\n')
                self.env.write_text(text)
                self.valid()

    def test_bootstrap_names_placeholders_rejected_when_disabled(self):
        original = self.env.read_text()
        for key in ('WAVY_BOOTSTRAP_ADMIN_FIRST_NAME', 'WAVY_BOOTSTRAP_ADMIN_LAST_NAME'):
            with self.subTest(key=key):
                self.env.write_text(original.replace('ci-fiction-only-'+key.lower()+'-0000000000000000', 'CHANGE_ME'))
                with self.assertRaisesRegex(ValueError, key): self.valid()

    def test_bootstrap_names_from_dotenv_ignore_inherited_values(self):
        self.change('WAVY_BOOTSTRAP_ENABLED=false', 'WAVY_BOOTSTRAP_ENABLED=true')
        names = {'WAVY_BOOTSTRAP_ADMIN_FIRST_NAME': 'CI Prénom fictif',
                 'WAVY_BOOTSTRAP_ADMIN_LAST_NAME': 'CI Nom fictif'}
        for key, value in names.items():
            self.change('ci-fiction-only-'+key.lower()+'-0000000000000000', "'"+value+"'")
        with patch.dict(os.environ, {key: 'inherited-fiction-only' for key in names}):
            self.valid()
            env = config.render(self.env)['services']['wavy-socle-api-preprod']['environment']
        for key, value in names.items():
            self.assertEqual(env[key], value)

    def test_bootstrap_names_must_reach_socle(self):
        self.change('WAVY_BOOTSTRAP_ENABLED=false', 'WAVY_BOOTSTRAP_ENABLED=true')
        p = self.root/'docker-compose.preprod.yml'
        original = p.read_text()
        for key in ('WAVY_BOOTSTRAP_ADMIN_FIRST_NAME', 'WAVY_BOOTSTRAP_ADMIN_LAST_NAME'):
            for replacement in (f'      {key}: "wrong"\n', ''):
                with self.subTest(key=key, replacement=replacement):
                    p.write_text(original.replace(f'      {key}: "${{{key}:-}}"\n', replacement))
                    with self.assertRaisesRegex(ValueError, key): self.valid()

    def test_tiers_credentials_required_on_both_ends(self):
        for key in ('WAVY_TIERS_SERVICE_USERNAME', 'WAVY_TIERS_SERVICE_PASSWORD'):
            with self.subTest(key=key):
                original = self.env.read_text()
                self.change('ci-fiction-only-'+key.lower()+'-0000000000000000', '')
                with self.assertRaisesRegex(ValueError, key): self.valid()
                self.env.write_text(original)
        self.valid()

    def test_tiers_credentials_reject_placeholder_and_short_password(self):
        for value in ('CHANGE_ME', 'short'):
            with self.subTest(value=value):
                original = self.env.read_text()
                self.change('ci-fiction-only-wavy_tiers_service_password-0000000000000000', value)
                with self.assertRaises(ValueError): self.valid()
                self.env.write_text(original)

    def test_tiers_credentials_must_reach_both_services(self):
        p = self.root/'docker-compose.preprod.yml'
        p.write_text(p.read_text().replace('WAVY_TIERS_SERVICE_PASSWORD: "${WAVY_TIERS_SERVICE_PASSWORD:?required}"', 'WAVY_TIERS_SERVICE_PASSWORD: "wrong"'))
        with self.assertRaisesRegex(ValueError, 'Credential interservice incohérent'): self.valid()

    def test_reject_wrong_interservice_route(self):
        p = self.root/'docker-compose.preprod.yml'
        p.write_text(p.read_text().replace('WAVY_FACTURES_API_URL: "http://wavy-factures-api-preprod:8083"',
                                           'WAVY_FACTURES_API_URL: "http://wavy-factures-api-recette:8083"'))
        with self.assertRaisesRegex(ValueError, 'URL interservice incorrecte'): self.valid()

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
