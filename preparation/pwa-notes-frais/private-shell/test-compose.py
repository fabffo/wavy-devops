#!/usr/bin/env python3
"""Rendu Compose uniquement avec environnement synthétique, sans daemon."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
P=Path(__file__).resolve().parent
ROOT=P.parents[2]
spec=importlib.util.spec_from_file_location('fixture',ROOT/'scripts/test-preprod-config.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)

class Compose(unittest.TestCase):
    def test_private_preflight(self):
        spec=importlib.util.spec_from_file_location("private",P/"validate-private.py")
        private=importlib.util.module_from_spec(spec);spec.loader.exec_module(private)
        with tempfile.TemporaryDirectory() as tmp:
            envfile=Path(tmp)/"fixture.env"
            envfile.write_text(fixture.fixture());envfile.chmod(0o600)
            private.validate(envfile)
            private.validate(envfile,release_candidate=True)

    def test_other_tunnel_port_is_refused(self):
        spec=importlib.util.spec_from_file_location("private_port",P/"validate-private.py")
        private=importlib.util.module_from_spec(spec);spec.loader.exec_module(private)
        with tempfile.TemporaryDirectory() as tmp:
            envfile=Path(tmp)/"fixture.env"
            envfile.write_text(fixture.fixture().replace('24443','24444'));envfile.chmod(0o600)
            with self.assertRaises(ValueError):private.validate(envfile)

    def test_only_three_shell_mounts_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            envfile=Path(tmp)/'test.env'; envfile.write_text(fixture.fixture())
            env={'PATH':os.environ['PATH'],'HOME':os.environ['HOME'],'WAVY_PRIVATE_PWA_DIR':str(P),'WAVY_PRIVATE_PWA_GATE_DIR':str(P/'socket')}
            cmd=['docker','compose','--env-file',str(envfile),'--env-file',str(ROOT/'versions/preprod.env'),'-p','wavy-preprod','-f',str(ROOT/'docker-compose.preprod.yml')]
            base=json.loads(subprocess.check_output(cmd+['config','--format','json'],env=env,text=True))
            candidate=json.loads(subprocess.check_output(cmd+['-f',str(P/'compose.private.yml'),'config','--format','json'],env=env,text=True))
            shell=candidate['services']['wavy-erp-shell-preprod']
            self.assertEqual(shell['ports'],base['services']['wavy-erp-shell-preprod']['ports'])
            self.assertEqual(shell['ports'][0]['host_ip'],'127.0.0.1')
            self.assertEqual(str(shell['ports'][0]['published']),'24443')
            mounts=shell.pop('volumes')
            self.assertEqual(len(mounts),3)
            for mount in mounts:
                self.assertTrue(mount['read_only'])
                self.assertFalse(mount['bind'].get('create_host_path', False))
                self.assertTrue(Path(mount['source']).exists())
            self.assertEqual(candidate,base)

if __name__=='__main__':unittest.main()
