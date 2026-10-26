#!/usr/bin/env python3
"""Contrats hors ligne, sans VM, compte ni mutation des bases existantes."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

P=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('candidate',P/'wavy_deploy.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class HttpsPreparation(unittest.TestCase):
    def test_exact_origins_and_shared_cohort(self):
        plans=[m.plan(e) for e in m.TARGETS]
        self.assertEqual(len({p['origin'] for p in plans}),3)
        self.assertEqual(plans[0]['images'],plans[1]['images'])
        self.assertEqual(plans[0]['images'],plans[2]['images'])
        self.assertTrue(all('@sha256:' in v for v in plans[0]['images'].values()))

    def test_cors_is_single_exact_origin(self):
        for e in m.TARGETS:
            origin=m.plan(e)['origin'];settings=m.gateway_settings(origin)
            self.assertEqual([v for k,v in settings.items() if k.endswith('.allowed-origins')],[origin])
            self.assertFalse(settings['spring.cloud.gateway.server.webflux.x-forwarded.enabled'])
            self.assertIn('PreserveHostHeader',settings['spring.cloud.gateway.server.webflux.default-filters'])

    def test_no_broad_proxy_trust(self):
        for bad in ('0.0.0.0/0','10.0.0.0/8','172.21.0.1/16','8.8.8.0/24','169.254.0.0/16','127.0.0.0/24','::/0'):
            with self.assertRaises(ValueError):m.proxy_regex(bad)
        import re
        regex=m.proxy_regex('172.21.0.0/16')
        self.assertIsNotNone(re.fullmatch(regex,'172.21.0.12'))
        self.assertIsNone(re.fullmatch(regex,'172.22.0.12'))
        self.assertIsNone(re.fullmatch(regex,'172.21.0.999'))

    def test_closed_pwa_and_notes_all_methods(self):
        self.assertIn('location ^~ /pwa/',m.CLOSED)
        self.assertEqual(m.CLOSED.count('if ($request_method !~ ^(GET|HEAD)$)'),2)
        self.assertIn('location ^~ /api/pwa/',m.CLOSED)
        self.assertNotIn('gate.sock',m.CLOSED)

    def test_shell_keeps_modules_and_canonical_https(self):
        text=m.shell_config('recettelocal.wavyservices.fr')
        for module in ('socle','tiers','contrats','factures','tresorerie'):
            self.assertIn('location /modules/'+module+'/',text)
        self.assertIn('location /api/',text)
        self.assertIn('X-Forwarded-Proto https',text)
        self.assertIn('X-Forwarded-Host recettelocal.wavyservices.fr',text)
        self.assertIn('$wavy_origin_denied',text)
        self.assertIn('return 421',text)
        self.assertNotIn('$scheme',text)

    def test_render_never_changes_base_or_creates_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'render';before=(m.ROOT/'docker-compose.recette.yml').read_bytes()
            result=m.render('recettelocal',out,'172.21.0.0/16')
            self.assertFalse(result['mutationsExecuted'])
            text=(out/'compose.https.yml').read_text()
            self.assertIn('ports: !override ["127.0.0.1:24207:80"]',text)
            self.assertEqual(text.count('ports: !override []'),12)
            self.assertEqual(text.count('    healthcheck:'),6)
            self.assertIn('--header=Host: recettelocal.wavyservices.fr',text)
            self.assertIn('SERVER_SERVLET_SESSION_COOKIE_SECURE: "true"',text)
            self.assertIn('WAVY_BOOTSTRAP_ENABLED: "false"',text)
            self.assertNotIn('SPRING_FLYWAY_ENABLED: "false"',text)
            self.assertEqual(before,(m.ROOT/'docker-compose.recette.yml').read_bytes())
            self.assertEqual((out.stat().st_mode&0o777),0o700)
            with self.assertRaises(ValueError):m.render('recettelocal',out,'172.21.0.0/16')

    def test_remote_render_refused_before_local_qualification(self):
        with tempfile.TemporaryDirectory() as tmp:
            for e in ('recette','preprod'):
                with self.assertRaises(ValueError):m.render(e,Path(tmp)/e,'172.21.0.0/16')
                self.assertFalse((Path(tmp)/e).exists())

    def test_mutations_fail_before_docker_or_ssh(self):
        for e in m.TARGETS:
            for action in ('deploy','resume','rollback'):
                with patch.object(m,'run',side_effect=AssertionError('No command')),patch('sys.argv',['candidate',e,action]):
                    self.assertEqual(m.main(),1)

    def test_caddy_no_public_acme_or_untrusted_forwarded(self):
        text=(P/'Caddyfile.candidate').read_text()
        self.assertIn('tls internal',text)
        self.assertIn('bind 127.0.0.1',text)
        self.assertIn('not header Origin https://{args[0]}',text)
        self.assertIn('header_up -Forwarded',text)
        self.assertNotIn('trusted_proxies',text)
        self.assertNotIn('tls_insecure_skip_verify',text)
        self.assertIn('header_up X-Forwarded-For {http.request.remote.host}',text)

    def test_wrong_digest_or_architecture_refused(self):
        with patch.object(m,'run',return_value=json.dumps([{'RepoDigests':[],'Os':'linux','Architecture':'amd64'}]).encode()):
            with self.assertRaises(ValueError):m.check_images('recettelocal')

if __name__=='__main__':unittest.main()
