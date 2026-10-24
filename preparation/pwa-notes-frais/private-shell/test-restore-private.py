#!/usr/bin/env python3
"""Contrats des copies isolées et archives factices ; aucune restauration DB/volume."""
import copy
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

P=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('restore_private',P/'restore-private.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class Restore(unittest.TestCase):
    def test_document_hashes_require_two_roots_and_exact_notes_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'fixture.tar'
            for mode,valid in ((0o700,True),(0o755,False)):
                with tarfile.open(path,'w') as out:
                    for name in ('contrats','notes-frais'):
                        entry=tarfile.TarInfo(name);entry.type=tarfile.DIRTYPE;entry.uid=100;entry.gid=101
                        entry.mode=mode if name=='notes-frais' else 0o700;out.addfile(entry)
                    entry=tarfile.TarInfo('notes-frais/fixture');entry.size=3;entry.uid=100;entry.gid=101;entry.mode=0o600
                    out.addfile(entry,io.BytesIO(b'abc'))
                if valid:self.assertEqual(len(m.document_hashes(path)),1)
                else:
                    with self.assertRaises(ValueError):m.document_hashes(path)
    def test_rendered_isolation_refuses_public_ports_active_or_driver_volumes(self):
        fixture={'services':{},'volumes':{'copy':{'name':'wavy-pwa-restore-fixture_copy'}}}
        for name in (*m.DATABASES,'documents'):
            fixture['services'][name]={'network_mode':'none','read_only':True,
                'image':'postgres:16-alpine@sha256:93d55776e04376e19adb2733e3ccebb4392ee7dd86d8ff238503b30fe719c84f',
                'volumes':[{'type':'volume','source':'copy'}]}
        m.validate_rendered(fixture,'wavy-pwa-restore-fixture')
        mutations=[lambda d:d['services']['socle'].update(ports=[80]),
                   lambda d:d['services']['socle'].update(network_mode='host'),
                   lambda d:d['volumes']['copy'].update(name='wavy-preprod_documents-preprod'),
                   lambda d:d['volumes']['copy'].update(external=True),
                   lambda d:d['volumes']['copy'].update(driver_opts={'device':'/real/active'}),
                   lambda d:d['services']['socle'].update(image='postgres:latest'),
                   lambda d:d['services']['socle'].update(privileged=True)]
        for mutate in mutations:
            data=copy.deepcopy(fixture);mutate(data)
            with self.assertRaises(ValueError):m.validate_rendered(data,'wavy-pwa-restore-fixture')
    def test_restore_refuses_without_inherited_reservation_before_any_command(self):
        with patch.dict(os.environ,{},clear=True),patch.object(m,'command') as command:
            with self.assertRaises(KeyError):m.restore(Path('unused'),Path('unused'))
            command.assert_not_called()
    def test_cli_release_is_inactive_without_flag(self):
        result=subprocess.run(['python3','-B',str(P/'release-private.py'),'reserve'],capture_output=True,text=True)
        self.assertEqual(result.returncode,2)
        self.assertIn('inactif',result.stderr)

if __name__=='__main__':unittest.main()
