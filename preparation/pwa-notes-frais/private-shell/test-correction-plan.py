#!/usr/bin/env python3
"""Contrat local du Compose réel et négatifs en mémoire ; aucune création Docker.
Ces assertions de test ne modifient PAS validate_rendered ni la sécurité runtime.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

P = Path(__file__).resolve().parent
DBS = ('socle', 'tiers', 'contrats', 'factures', 'tresorerie')
IMAGE = 'postgres:16-alpine@sha256:93d55776e04376e19adb2733e3ccebb4392ee7dd86d8ff238503b30fe719c84f'


def assert_structure(data, secret_dir):
    expected = {db: db + '-data' for db in DBS}
    expected['documents'] = 'documents-copy'
    assert set(data['services']) == set(expected)
    assert set(data['volumes']) == set(expected.values())
    actual_names = set()
    for name, volume in data['volumes'].items():
        assert volume['name'] == 'wavy-pwa-restore-correction_' + name
        assert not volume.get('external') and not volume.get('driver_opts')
        actual_names.add(volume['name'])
    assert len(actual_names) == 6
    for name, source in expected.items():
        service = data['services'][name]
        assert service['image'] == IMAGE
        assert service['network_mode'] == 'none' and service['read_only']
        for forbidden in ('ports', 'container_name', 'privileged', 'devices', 'cap_add', 'volumes_from', 'build'):
            assert not service.get(forbidden)
        assert 'no-new-privileges:true' in service['security_opt']
        mounts = service['volumes']
        vols = [m for m in mounts if m['type'] == 'volume']
        assert len(vols) == 1 and vols[0]['source'] == source
        assert vols[0]['target'] == ('/documents' if name == 'documents' else '/var/lib/postgresql/data')
        binds = [m for m in mounts if m['type'] == 'bind']
        assert len(mounts) == 1 + len(binds)
        if name == 'documents':
            assert not binds
        else:
            assert len(binds) == 1
            mount = binds[0]
            assert mount['source'] == str(secret_dir / (name + '.password'))
            assert mount['target'] == '/run/secrets/db-password'
            assert mount['read_only'] and not mount.get('bind', {}).get('create_host_path', False)
            assert set(service['tmpfs']) == {'/tmp', '/var/run/postgresql'}
            assert service['environment']['POSTGRES_PASSWORD_FILE'] == '/run/secrets/db-password'


class CorrectionPlan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.secret_dir = Path(cls.temp.name)
        values = {'RESTORE_SECRET_DIR': str(cls.secret_dir)}
        for db in DBS:
            values['RESTORE_' + db.upper() + '_DB'] = db
            values['RESTORE_' + db.upper() + '_USER'] = 'fixture_operator'
        config = cls.secret_dir / 'fixture.env'
        config.write_text('\n'.join(k + '=' + v for k, v in values.items()))
        # config seulement ; aucune connexion au daemon nécessaire pour créer une ressource.
        cls.rendered = json.loads(subprocess.check_output([
            'docker', 'compose', '--env-file', str(config), '-p', 'wavy-pwa-restore-correction',
            '-f', str(P / 'restore-isolated.compose.yml'), 'config', '--format', 'json'],
            env={'PATH': os.environ['PATH'], 'HOME': os.environ['HOME']}, text=True))

    def test_actual_compose_has_six_distinct_volumes_and_only_expected_mounts(self):
        assert_structure(self.rendered, self.secret_dir)

    def test_alias_or_external_volume_rejected_by_local_contract(self):
        for mutation in ('alias', 'external', 'target'):
            with self.subTest(mutation=mutation):
                d = copy.deepcopy(self.rendered)
                if mutation == 'alias':
                    d['services']['tiers']['volumes'][0]['source'] = 'socle-data'
                elif mutation == 'external':
                    d['volumes']['socle-data']['external'] = True
                else:
                    d['services']['socle']['volumes'][0]['target'] = '/unexpected'
                with self.assertRaises(AssertionError):
                    assert_structure(d, self.secret_dir)

    def test_unexpected_bind_or_secret_creation_rejected_by_local_contract(self):
        for mutation in ('bind', 'writable', 'create', 'secret-path', 'tmpfs'):
            with self.subTest(mutation=mutation):
                d = copy.deepcopy(self.rendered)
                s = d['services']['socle']
                m = next(v for v in s['volumes'] if v['type'] == 'bind')
                if mutation == 'bind':
                    s['volumes'].append({'type': 'bind', 'source': '/var/run/docker.sock', 'target': '/socket'})
                elif mutation == 'writable':
                    m['read_only'] = False
                elif mutation == 'create':
                    m.setdefault('bind', {})['create_host_path'] = True
                elif mutation == 'secret-path':
                    m['source'] = '/active/secret'
                else:
                    s['tmpfs'] = ['/tmp']
                with self.assertRaises(AssertionError):
                    assert_structure(d, self.secret_dir)

    def test_ports_network_privilege_and_digest_changes_rejected_by_local_contract(self):
        for patch in ({'ports': [{'target': 5432, 'published': '5432'}]},
                      {'network_mode': 'host'}, {'privileged': True},
                      {'image': 'postgres:latest'}, {'read_only': False}, {'security_opt': []}):
            with self.subTest(patch=patch):
                d = copy.deepcopy(self.rendered)
                d['services']['factures'].update(patch)
                with self.assertRaises(AssertionError):
                    assert_structure(d, self.secret_dir)

    def test_matrix_has_all_anomalies_and_no_claimed_execution(self):
        d = json.loads((P / 'MATRICE-CORRECTIONS-PREPROD.json').read_text())
        self.assertEqual({r['id'] for r in d['anomalies']}, {'B1', 'B2', 'M1', 'M2', 'M3', 'M4', 'M5', 'R1', 'R2'})
        for row in d['anomalies']:
            self.assertTrue(row['proposedCorrection'] and row['test'] and row['expectedProof'])
            self.assertEqual(row['execution']['status'], 'NON_EXECUTE')
            self.assertIsNone(row['execution']['decision'])
        cases = d['sessionCases']
        self.assertEqual(len({r['id'] for r in cases}), len(cases))
        self.assertEqual({(r['family'], r['axis']) for r in cases},
                         {(f['id'], a) for f in d['sessionFamilies'] for a in d['sessionAxes']})
        for row in cases:
            self.assertEqual(row['status'], 'NON_EXECUTE')
            self.assertIsNone(row['proofSha256'])
            self.assertIsNone(row['returnCode'])

    def test_three_attestations_remain_false_in_all_local_templates(self):
        names = ('rollback-schema-compatible', 'session-isolation-plan', 'isolated-restore-capacity')
        for file, key in [('prerequisites.private.example.json', 'checks'),
                          ('msi-prerequisites-facts.json', 'preprodAttestations'),
                          ('MATRICE-CORRECTIONS-PREPROD.json', 'preprodAttestations')]:
            d = json.loads((P / file).read_text())[key]
            for name in names:
                self.assertIs(d[name], False)


if __name__ == '__main__':
    unittest.main()
