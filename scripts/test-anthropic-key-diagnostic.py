#!/usr/bin/env python3
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('key_diag', Path(__file__).with_name('diagnose-anthropic-key.py'))
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)


class KeyDiagnostic(unittest.TestCase):
    def test_exact_bytes_comparison_changes_for_whitespace_and_challenge(self):
        challenge = '1' * 64
        base = diag.response_for(b'fixture-private-key', challenge)
        self.assertTrue(diag.hmac.compare_digest(base, diag.response_for(b'fixture-private-key', challenge)))
        for key in (b'fixture-private-key ', b'fixture-private-key\r\n', b'fixture-old-key'):
            self.assertFalse(diag.hmac.compare_digest(base, diag.response_for(key, challenge)))
        self.assertFalse(diag.hmac.compare_digest(base, diag.response_for(b'fixture-private-key', '2' * 64)))
        with self.assertRaises(ValueError):
            diag.response_for(b'fixture-private-key', 'bad challenge')

    def test_invisible_characters_quotes_and_literal_escapes_are_detected(self):
        for value, field in [(' key', 'leadingWhitespace'), ('key\t', 'trailingWhitespace'),
                             ('key\r\n', 'carriageReturnOrNewline'), ('key\ufeff', 'invisibleOrControl'),
                             ('key\u00a0', 'nonAscii'), (r'key\n', 'literalEscapedWhitespace'),
                             ('"key"', 'quoteAtBoundary'), ('${KEY}', 'unresolvedInterpolation')]:
            self.assertTrue(diag.key_hygiene(value)[field])
        self.assertTrue(diag.key_hygiene('')['blank'])
        self.assertFalse(diag.key_hygiene('sk-ant-api-fixture')['whitespaceAnywhere'])

    def fixture(self, process_key='fixture-private-key'):
        wanted = {'WAVY_AI_PROVIDER': 'anthropic', 'WAVY_AI_MODEL': 'claude-test', 'WAVY_AI_API_KEY': 'fixture-private-key'}
        configured = [key+'='+value for key, value in wanted.items()]
        environment = [v for v in configured if not v.startswith('WAVY_AI_API_KEY=')] + ['WAVY_AI_API_KEY='+process_key]
        calls = []
        def run(args, **kwargs):
            calls.append(args)
            if args[:2] == ['docker', 'inspect']:
                return json.dumps([{'State': {'Running': True}, 'Config': {'Env': configured},
                                    'Image': 'sha256:'+'a'*64, 'Mounts': []}]).encode()
            if args[-1] == '/proc/1/comm':
                return b'java\n'
            if args[-1] == '/proc/1/environ':
                return '\0'.join(environment).encode()
            if 'unzip' in args:
                return b'https://api.anthropic.com/v1 /messages x-api-key anthropic-version 2023-06-01'
            raise AssertionError('Unexpected command')
        return wanted, run, calls

    def test_report_has_no_secret_or_fingerprint_and_detects_stale_process(self):
        wanted, run, calls = self.fixture('fixture-private-key\r\n')
        with patch.object(diag, 'local_guard'), patch.object(diag, 'run', side_effect=run), patch.object(diag, 'intended_environment', return_value=wanted), patch.object(diag, 'dotenv_shape', return_value={'available': True}):
            report, key, eligible = diag.audit(Path('/fixture'), 'recette')
        self.assertFalse(report['dockerConfigEqualsProcessKey'])
        self.assertFalse(report['intendedConfiguration']['sameKeyAsProcess'])
        self.assertTrue(report['keyHygiene']['carriageReturnOrNewline'])
        self.assertTrue(report['requestContract']['reviewedConstantsPresent'])
        self.assertNotIn('fixture-private-key', json.dumps(report))
        self.assertNotIn(diag.hashlib.sha256(key).hexdigest(), json.dumps(report))
        self.assertTrue(eligible)
        self.assertTrue(all(args[:2] in (['docker', 'inspect'], ['docker', 'exec']) for args in calls))
        self.assertFalse(any('up' in args or 'restart' in args for args in calls))

    def test_exact_intended_key_is_not_normalized(self):
        wanted, run, _ = self.fixture()
        with patch.object(diag, 'local_guard'), patch.object(diag, 'run', side_effect=run), patch.object(diag, 'intended_environment', return_value=wanted), patch.object(diag, 'dotenv_shape', return_value={'available': True}):
            report, _, _ = diag.audit(Path('/fixture'), 'msi')
        self.assertTrue(report['intendedConfiguration']['sameKeyAsProcess'])
        self.assertTrue(report['dockerConfigEqualsProcessKey'])
        def non_java(args, **kwargs):
            return b'sh\n' if args[-1] == '/proc/1/comm' else run(args, **kwargs)
        with patch.object(diag, 'local_guard'), patch.object(diag, 'run', side_effect=non_java):
            with self.assertRaises(ValueError): diag.audit(Path('/fixture'), 'msi')

    def test_remote_docker_refused_before_any_inspection(self):
        with patch.dict(os.environ, {'DOCKER_HOST': 'ssh://not-allowed'}), patch.object(diag, 'run') as run:
            with self.assertRaises(ValueError): diag.local_guard()
            run.assert_not_called()

    def test_command_errors_never_expose_raw_output(self):
        result = subprocess.CompletedProcess([], 1, b'fixture-private-key', b'fixture-private-key')
        with patch.object(diag.subprocess, 'run', return_value=result):
            with self.assertRaises(ValueError) as error: diag.run(['docker', 'inspect', 'fixture'])
        self.assertNotIn('fixture-private-key', str(error.exception))

    def test_no_terminal_proof_falls_back_to_stdout(self):
        output = io.StringIO()
        with patch.dict(os.environ, {'TERM': 'dumb'}), contextlib.redirect_stdout(output):
            with self.assertRaises(ValueError): diag.interactive_compare(b'fixture-private-key', 'msi')
        self.assertEqual(output.getvalue(), '')

    def test_main_exception_is_redacted(self):
        with patch.object(diag.sys, 'argv', ['diagnostic', '--environment', 'msi']), patch.object(diag, 'audit', side_effect=ValueError('fixture-private-key')), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(diag.main(), 1)
        self.assertNotIn('fixture-private-key', output.getvalue())
        for equal in (True, False):
            with patch.object(diag.sys, 'argv', ['diagnostic', '--environment', 'msi', '--compare']), patch.object(diag, 'audit', return_value=({}, b'fixture-private-key', True)), patch.object(diag, 'interactive_compare', return_value={'sameKeyAsPeer': equal}), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(diag.main(), 0)
            self.assertEqual(output.getvalue(), ('Clés identiques' if equal else 'Clés différentes')+'\n')
        with patch.object(diag.sys, 'argv', ['diagnostic', '--environment', 'recette', '--challenge', '1'*64]), patch.object(diag, 'audit', return_value=({}, b'fixture-private-key', True)), patch.object(diag, 'interactive_compare', return_value={}), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(diag.main(), 0)
        self.assertEqual(output.getvalue(), '')

    def test_env_duplicates_are_not_silently_ignored(self):
        _, duplicates = diag.parse_env(['WAVY_AI_API_KEY=first-fixture', 'WAVY_AI_API_KEY=second-fixture'])
        self.assertIn('WAVY_AI_API_KEY', duplicates)

    def test_compose_serialization_is_decoded_without_stripping_key(self):
        import release_images
        config = {'services': {'wavy-factures-api-recette': {'environment': {
            'WAVY_AI_API_KEY': ' fixture-$$literal\r\n'}}}}
        with patch.object(release_images, 'recette_compose', return_value=config):
            values = diag.intended_environment(Path('/fixture'), 'recette')
        self.assertTrue(values['WAVY_AI_API_KEY'] == ' fixture-$literal\r\n')

    def test_temporary_remote_proof_never_reaches_report_or_stdout(self):
        from unittest.mock import MagicMock
        terminal = MagicMock()
        terminal.__enter__.return_value = terminal
        terminal.isatty.return_value = True
        challenge = '1' * 64
        response = diag.response_for(b'fixture-private-key', challenge)
        with patch.dict(os.environ, {'TERM': 'xterm'}), patch('builtins.open', return_value=terminal), patch.object(diag, 'read_hidden', return_value=''), contextlib.redirect_stdout(io.StringIO()) as output:
            report = diag.interactive_compare(b'fixture-private-key', 'recette', challenge)
        self.assertEqual(output.getvalue(), '')
        self.assertNotIn(response, json.dumps(report))
        writes = ''.join(call.args[0] for call in terminal.write.call_args_list)
        self.assertIn('\x1b[?1049h', writes)
        self.assertTrue(writes.endswith('\x1b[?1049l'))
        self.assertNotIn('fixture-private-key', writes)


if __name__ == '__main__':
    unittest.main()
