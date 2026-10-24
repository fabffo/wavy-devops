#!/usr/bin/env python3
"""Régressions de la revue finale, conservées comme exigences de fermeture."""
import importlib.util
from pathlib import Path
import unittest
import shutil
import tempfile
from unittest.mock import patch

P=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('fixture',P/'test-private.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)

class ClosureRequirements(unittest.TestCase):
    def test_notes_matrix_parameter_must_not_bypass_write_gate(self):
        fixture.Private.run_fixture(self, extra_closed_checks=''.join(
            f"check 403 POST '{path}' ''\n" for path in (
                '/api/notes-frais;v=1/1/justificatif',
                '/api/notes-frais%3bv=1/1/justificatif',
                '/api/notes-frais%253bv=1/1/justificatif',
                '/api/notes-frais%252f1/justificatif')))

    def test_corrupt_marker_must_stay_closed(self):
        fixture.Private.run_fixture(self, invalid_marker="printf 'invalid-json' > /run/wavy-private-pwa/open")

    def test_unreadable_marker_must_stay_closed(self):
        fixture.Private.run_fixture(self, invalid_marker="touch /run/wavy-private-pwa/open; chmod 000 /run/wavy-private-pwa/open")

    def test_expired_authorization_must_stay_closed(self):
        fixture.Private.run_fixture(self, invalid_marker='''printf '%s' '{"notAfter":"2000-01-01T00:00:00Z"}' > /run/wavy-private-pwa/open''')

    def test_symlink_marker_must_stay_closed(self):
        fixture.Private.run_fixture(self, invalid_marker="ln -s /etc/nginx/nginx.conf /run/wavy-private-pwa/open")

class PreflightRequirements(unittest.TestCase):
    def test_world_writable_control_must_be_rejected(self):
        spec=importlib.util.spec_from_file_location('preflight',P/'validate-private.py')
        preflight=importlib.util.module_from_spec(spec);spec.loader.exec_module(preflight)
        spec=importlib.util.spec_from_file_location('envfixture',P.parents[2]/'scripts/test-preprod-config.py')
        envfixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(envfixture)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in ('shell.conf.template','routes.conf','compose.private.yml'):
                shutil.copyfile(P/name,root/name)
            (root/'control').mkdir(mode=0o700)
            (root/'socket').mkdir(mode=0o755)
            envfile=root/'fixture.env'
            envfile.write_text(envfixture.fixture());envfile.chmod(0o600)
            with patch.object(preflight,'P',root):
                preflight.validate(envfile)
                (root/'control').chmod(0o777)
                with self.assertRaises(ValueError): preflight.validate(envfile)

if __name__=='__main__':unittest.main()
