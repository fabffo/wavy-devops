#!/usr/bin/env python3
"""Contrats Docker du backend : toutes les réponses Docker sont simulées."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode=True
C=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('runtime_backend',C/'scripts/release_pwa_preprod.py')
release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)


class Backend(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.plan=json.loads((C/'release-plan.json').read_text())
        self.backend=release.DockerBackend(Path(self.tmp.name)/'unused.env',Path(self.tmp.name))

    def image(self,component):
        expected=self.plan['images'][component]
        return {'RepoDigests':[expected['reference']], 'Config':{'Labels':expected['ociLabels']},
                'Os':'linux','Architecture':'amd64','Id':'sha256:fixture'}

    def test_images_require_complete_digest_oci_and_host_platform(self):
        def lookup(ref):
            return self.image(next(c for c,i in self.plan['images'].items() if i['reference']==ref))
        with patch.object(self.backend,'command',return_value=b'linux/amd64\n'), patch.object(self.backend,'image',side_effect=lookup):
            self.backend.images(self.plan)
        mutations=[lambda d:d.update(RepoDigests=[]),
                   lambda d:d.update(Architecture='arm64'),
                   lambda d:d['Config']['Labels'].update({'org.opencontainers.image.source':'wrong'}),
                   lambda d:d['Config']['Labels'].update({'org.opencontainers.image.version':'9.9.9'}),
                   lambda d:d['Config']['Labels'].update({'org.opencontainers.image.revision':'abcdef0'})]
        for mutate in mutations:
            image=copy.deepcopy(self.image('factures-api'));mutate(image)
            with patch.object(self.backend,'command',return_value=b'linux/amd64'), patch.object(self.backend,'image',return_value=image):
                with self.assertRaises(ValueError):self.backend.images(self.plan)
        with patch.object(self.backend,'command',return_value=b'linux/arm64'):
            with self.assertRaises(ValueError):self.backend.images(self.plan)

    def test_deploy_pins_no_build_no_pull_and_rollback_shell_never_starts(self):
        with patch.object(release.config,'validate'), patch.object(self.backend,'command') as command:
            self.backend.deploy('factures-api',self.plan,'closed')
            args=command.call_args.args[0]
            self.assertEqual(args[-8:],['up','-d','--no-deps','--no-build','--force-recreate','--pull','never','wavy-factures-api-preprod'])
            clean=command.call_args.args[1]
            for c,i in self.plan['images'].items():
                self.assertEqual(clean['PWA_RELEASE_'+c.upper().replace('-','_')+'_IMAGE'],i['reference'])
            self.backend.deploy('erp-shell',self.plan,'stopped')
            args=command.call_args.args[0]
            self.assertIn('--no-start',args);self.assertNotIn('-d',args)

    def test_close_is_independent_of_failed_docker_stop_kill(self):
        self.backend.run_id = 'a'*32
        def command(args, *unused, **kwargs):
            if args[0] == 'docker': raise ValueError('Daemon unavailable: stop/kill impossible')
            return b''
        with patch.object(self.backend,'route') as probe, patch.object(self.backend,'command',side_effect=command) as calls:
            self.backend.close()
            probe.assert_called_once_with('closed')
            self.assertFalse(calls.called)
        self.assertFalse(self.backend.gate.permits('/check'))
        self.assertFalse(self.backend.gate.read()['closureBlocked'])
        with patch.object(self.backend,'route',side_effect=ValueError('No edge confirmation')):
            with self.assertRaises(ValueError):self.backend.close()
        self.assertTrue(self.backend.gate.read()['closureBlocked'])
        with self.assertRaises(ValueError):self.backend.open_edge('2099-01-01T00:00:00+00:00')

    def test_observed_rejects_tag_unhealthy_or_different_image(self):
        ref=self.plan['images']['pwa']['reference']
        good={'Config':{'Image':ref},'Image':'sha256:fixture','Id':'container-fixture',
              'State':{'Running':True,'Health':{'Status':'healthy'}}}
        with patch.object(self.backend,'container',return_value=good),patch.object(self.backend,'image',return_value={'Id':'sha256:fixture'}):
            self.backend.observed('pwa',self.plan)
        for mutate in (lambda d:d['Config'].update(Image='some:tag'),lambda d:d.update(Image='other'),
                       lambda d:d['State']['Health'].update(Status='unhealthy')):
            actual=copy.deepcopy(good);mutate(actual)
            with patch.object(self.backend,'container',return_value=actual),patch.object(self.backend,'image',return_value={'Id':'sha256:fixture'}):
                with self.assertRaises(ValueError):self.backend.observed('pwa',self.plan)

    def test_flyway_errors_in_stderr_are_caught_without_logging(self):
        with patch.object(self.backend,'helper'),patch.object(self.backend,'container',return_value={'State':{'StartedAt':'fixture'}}), \
             patch.object(self.backend,'command',return_value=b'FlywayValidateException SECRET_CANARY'):
            with self.assertRaises(ValueError) as result:self.backend.healthy('factures-api')
            self.assertNotIn('SECRET_CANARY',str(result.exception))


if __name__=='__main__':unittest.main()
