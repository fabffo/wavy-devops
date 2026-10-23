#!/usr/bin/env python3
"""Compose et gardes candidats : valeurs fictives, aucun service ou volume utilisé."""
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
C = Path(__file__).resolve().parent
ROOT = C.parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


config = load(C / 'scripts/preprod_config.py', 'candidate_validator')
fixture = load(ROOT / 'scripts/test-preprod-config.py', 'active_fixture')


def https_fixture():
    return fixture.fixture().replace('WAVY_ACCESS_MODE=tunnel', 'WAVY_ACCESS_MODE=https').replace(
        'WAVY_COOKIE_SECURE=false', 'WAVY_COOKIE_SECURE=true').replace(
        'http://localhost:24443', 'https://preprod.wavy.invalid')


class ComposeValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.env = Path(cls.tmp.name) / 'machine.env'
        cls.env.write_text(https_fixture());cls.env.chmod(0o600)
        cls.plan = config.read_plan(C / 'release-plan.json')
        cls.baseline = config.base.render(cls.env)
        cls.closed = config.render(cls.env, cls.plan, 'closed')
        cls.opened = config.render(cls.env, cls.plan, 'open')

    def test_closed_open_and_inherited_injection(self):
        with contextlib.redirect_stdout(io.StringIO()):
            for mode in ('closed', 'open'):
                config.validate(self.env, self.plan, mode)
            with patch.dict(os.environ, {'PWA_RELEASE_PWA_IMAGE': 'evil:latest',
                                         'WAVY_PWA_CANDIDATE_DIR': '/etc',
                                         'COMPOSE_FILE': '/etc/passwd'}):
                self.assertEqual(config.render(self.env, self.plan), self.closed)

    def test_bind_allowlist_destinations_modes_and_extra_mounts(self):
        shell = 'wavy-erp-shell-preprod'
        api = 'wavy-factures-api-preprod'
        mutations = [lambda d: d['services'][shell]['volumes'][0].update(source='/etc/passwd'),
                     lambda d: d['services'][shell]['volumes'][0].update(target='/etc/nginx/nginx.conf'),
                     lambda d: d['services'][shell]['volumes'][0].update(read_only=False),
                     lambda d: d['services'][shell]['volumes'][0]['bind'].update(create_host_path=True),
                     lambda d: d['services'][shell]['volumes'].append(copy.deepcopy(d['services'][shell]['volumes'][0])),
                     lambda d: d['services'][api]['volumes'][0].update(type='bind'),
                     lambda d: d['services'][api]['volumes'][0].update(read_only=True),
                     lambda d: d['services'][api]['volumes'][0]['volume'].update(subpath='contrats'),
                     lambda d: d['services'][api]['volumes'][0]['volume'].update(nocopy=False),
                     lambda d: d['services'][api]['volumes'][0].update(source='other'),
                     lambda d: d['services']['wavy-pwa-preprod'].update(volumes=[{'type':'bind','source':'/tmp','target':'/data'}])]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                data = copy.deepcopy(self.closed);mutate(data)
                with self.assertRaises(ValueError):config.validate_rendered(data, self.baseline, self.plan)
        with self.assertRaises(ValueError):config.validate_rendered(self.opened, self.baseline, self.plan, 'closed')

    def test_bind_missing_symlink_wrong_permissions_or_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('nginx-pwa-disabled.conf', 'pwa-integration.disabled.json'):
                (root/name).write_bytes((C/name).read_bytes());(root/name).chmod(0o644)
            data = copy.deepcopy(self.closed)
            mounts = data['services']['wavy-erp-shell-preprod']['volumes']
            for mount in mounts:mount['source'] = str(root/Path(mount['source']).name)
            with patch.object(config, 'CANDIDATE', root):
                config.validate_rendered(data, self.baseline, self.plan)
                file = root/'pwa-integration.disabled.json'
                file.chmod(0o666)
                with self.assertRaises(ValueError):config.validate_rendered(data, self.baseline, self.plan)
                file.chmod(0o644);file.write_text('{"enabled":true,"justificatifMaxBytes":10485760}')
                with self.assertRaises(ValueError):config.validate_rendered(data, self.baseline, self.plan)
                file.unlink()
                with self.assertRaises(ValueError):config.validate_rendered(data, self.baseline, self.plan)
                file.symlink_to(C/'pwa-integration.disabled.json')
                with self.assertRaises(ValueError):config.validate_rendered(data, self.baseline, self.plan)

    def test_images_services_networks_dependencies_and_db_guards(self):
        mutations = [lambda d: d['services']['wavy-pwa-preprod'].update(image='evil:latest'),
                     lambda d: d['services']['wavy-pwa-preprod'].update(image='ghcr.io/fabffo/wavy-pwa@sha256:short'),
                     lambda d: d['services']['wavy-pwa-preprod'].update(image='ghcr.io/fabffo/wavy-pwa@sha256:'+'0'*64),
                     lambda d: d['services'].pop('wavy-factures-front-preprod'),
                     lambda d: d['services'].update(extra={}),
                     lambda d: d['services']['wavy-pwa-preprod'].update(networks={'other':None}),
                     lambda d: d['services']['wavy-pwa-preprod'].update(privileged=True),
                     lambda d: d['services']['wavy-pwa-preprod'].update(healthcheck={'disable':True}),
                     lambda d: d['services']['wavy-factures-api-preprod']['environment'].update(SPRING_FLYWAY_CLEAN_DISABLED='false'),
                     lambda d: d['services']['wavy-erp-shell-preprod']['depends_on'].pop('wavy-pwa-preprod'),
                     lambda d: d['volumes']['documents-preprod'].update(external=True)]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                data = copy.deepcopy(self.closed);mutate(data)
                with self.assertRaises(ValueError):config.validate_rendered(data, self.baseline, self.plan)

    def test_invalid_https_cookies_and_cors(self):
        for change in (lambda s: s.replace('WAVY_PUBLIC_HTTP_PORT=24443','WAVY_PUBLIC_HTTP_PORT=24450'),
                       lambda s: s.replace('https://preprod.wavy.invalid','http://preprod.wavy.invalid'),
                       lambda s: s.replace('WAVY_COOKIE_SECURE=true','WAVY_COOKIE_SECURE=false'),
                       lambda s: s.replace('WAVY_ACCESS_MODE=https','WAVY_ACCESS_MODE=tunnel'),
                       lambda s: s.replace('WAVY_CORS_ALLOWED_ORIGIN_PATTERNS=https://preprod.wavy.invalid',
                                          'WAVY_CORS_ALLOWED_ORIGIN_PATTERNS=*')):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp)/'bad.env';path.write_text(change(https_fixture()));path.chmod(0o600)
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ValueError):config.validate(path,self.plan)

    def test_original_general_guards_still_apply_to_base(self):
        base = copy.deepcopy(self.baseline)
        base['services']['wavy-socle-api-preprod']['environment']['SPRING_FLYWAY_CLEAN_DISABLED']='false'
        candidate = copy.deepcopy(self.closed)
        candidate['services']['wavy-socle-api-preprod']['environment']['SPRING_FLYWAY_CLEAN_DISABLED']='false'
        with patch.object(config.base,'render',return_value=base), patch.object(config,'render',return_value=candidate):
            with self.assertRaises(ValueError):config.validate(self.env,self.plan)

    def test_compose_cli_rejects_extra_override_without_secret_output(self):
        result = subprocess.run([sys.executable,str(C/'scripts/preprod_config.py'),'compose',str(self.env),
                                 '-f','SECRET_CANARY.yml','up'],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertNotIn('SECRET_CANARY',result.stdout+result.stderr)


if __name__ == '__main__':unittest.main()
