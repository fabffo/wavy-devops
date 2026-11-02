#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('factures_diagnostic', Path(__file__).with_name('diagnose-recette-factures.py'))
diag = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)


class FacturesDiagnostic(unittest.TestCase):
    def test_no_secret_even_in_wrong_fields(self):
        secret = 'sk-private-fixture-only'
        summary = diag.ai_summary(dict.fromkeys(diag.AI_KEYS, secret))
        self.assertNotIn(secret, json.dumps(summary))
        self.assertTrue(summary['present']['WAVY_AI_API_KEY'])
        self.assertFalse(diag.ai_summary({'WAVY_AI_API_KEY': '  '})['present']['WAVY_AI_API_KEY'])

    def test_image_and_ai_mismatch_detected_without_writing_or_provider_call(self):
        secret = 'private-fixture'
        wanted = {'WAVY_AI_PROVIDER':'anthropic', 'WAVY_AI_MODEL':'claude-test', 'WAVY_AI_API_KEY':secret}
        images = {c:'ghcr.io/fabffo/wavy-'+c+':0.2.0-abcdef0@sha256:'+'a'*64 for c in ('factures-front','factures-api')}
        calls=[]
        def inspect(args):
            calls.append(args)
            if args[0]=='inspect':
                return [{'Image':'sha256:'+'b'*64,'State':{'Running':True},'Config':{'Env':['WAVY_AI_PROVIDER=anthropic','WAVY_AI_MODEL=claude-old','WAVY_AI_API_KEY=wrong-private-fixture']}}]
            return [{'RepoDigests':[],'Config':{'Labels':{'org.opencontainers.image.revision':'old'}}}]
        with patch.object(diag, 'release', return_value=({}, {}, images)), patch.object(diag, 'recette_compose', return_value={'services':{'wavy-factures-api-recette':{'environment':wanted}}}) as compose, patch.object(diag, 'docker_json', side_effect=inspect), patch.object(diag, 'provider_statuses', return_value={'available':False,'httpStatuses':[]}):
            report=diag.inspect_report(Path('/fixture'))
        self.assertFalse(report['images']['factures-front']['expectedDigestInActiveImage'])
        self.assertFalse(report['aiMatchesRendered']['WAVY_AI_API_KEY'])
        self.assertFalse(report['aiMatchesRendered']['WAVY_AI_MODEL'])
        self.assertNotIn(secret,json.dumps(report))
        self.assertNotIn('wrong-private-fixture',json.dumps(report))
        self.assertTrue(all(args[0] in ('inspect','image') for args in calls))
        compose.assert_called_once_with(Path('/fixture'), ['config','--format','json'], capture=True)

    def test_remote_context_refused_before_inspect(self):
        with patch.dict(diag.os.environ, {'DOCKER_HOST':'ssh://forbidden'}), patch.object(diag,'docker_json') as docker, patch('builtins.print') as output:
            self.assertEqual(diag.main(),1)
            docker.assert_not_called()
            self.assertNotIn('ssh://forbidden',str(output.call_args))

    def test_active_digest_revision_and_artifact_override_are_reported_without_key(self):
        values = {'WAVY_AI_PROVIDER': 'anthropic', 'WAVY_AI_MODEL': 'claude-test', 'WAVY_AI_API_KEY': 'private-fixture'}
        images = {c: 'ghcr.io/fabffo/wavy-'+c+':0.2.0-abcdef0@sha256:'+'a'*64
                  for c in ('factures-front', 'factures-api')}
        def inspect(args):
            if args[0] == 'inspect':
                return [{'Image': 'sha256:'+'b'*64, 'State': {'Running': True},
                         'Config': {'Env': [key+'='+value for key, value in values.items()]},
                         'Mounts': [{'Destination': '/app/app.jar'}]}]
            return [{'RepoDigests': [image.split(':0.2.0')[0]+'@sha256:'+'a'*64 for image in images.values()],
                     'Config': {'Labels': {'org.opencontainers.image.revision': 'abcdef0',
                                          'org.opencontainers.image.version': '0.2.0'}}}]
        with patch.object(diag, 'release', return_value=({}, {}, images)), patch.object(diag, 'recette_compose', return_value={'services': {'wavy-factures-api-recette': {'environment': values}}}), patch.object(diag, 'docker_json', side_effect=inspect), patch.object(diag, 'provider_statuses', return_value={'available': True, 'httpStatuses': []}):
            report = diag.inspect_report(Path('/fixture'))
        actual = report['images']['factures-api']
        self.assertEqual(actual['activeRevision'], 'abcdef0')
        self.assertEqual(actual['activeVersion'], '0.2.0')
        self.assertTrue(actual['expectedDigestInActiveImage'])
        self.assertTrue(actual['expectedRevisionInActiveImage'])
        self.assertTrue(actual['artifactOverridePresent'])
        self.assertTrue(report['aiMatchesRendered']['WAVY_AI_API_KEY'])
        self.assertEqual(len(actual['activeRepoDigests']), 1)
        self.assertNotIn('private-fixture', json.dumps(report))

    def test_log_projection_exposes_only_http_status(self):
        import subprocess
        log='secret-fixture document.pdf Erreur Anthropic extraction facture vente: statusHttp=401, model=claude-fixture, erreur=secret-fixture'
        with patch.object(diag.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'',log)) as run:
            report=diag.provider_statuses()
        self.assertEqual(report,{'available':True,'httpStatuses':['401']})
        self.assertNotIn('secret-fixture',json.dumps(report))
        self.assertEqual(run.call_args.args[0][:2],['docker','logs'])

    def test_docker_errors_never_echo_secret(self):
        import subprocess
        with patch.object(diag.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'private-fixture','private-fixture')):
            with self.assertRaisesRegex(ValueError,'masquée') as error:diag.docker_json(['inspect','fixture'])
        self.assertNotIn('private-fixture',str(error.exception))


if __name__=='__main__':unittest.main()
