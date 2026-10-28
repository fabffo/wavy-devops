#!/usr/bin/env python3
"""Exercice réel DB + documents sur fixtures jetables ; jamais de ressource active."""
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
sys.dont_write_bytecode=True
import recette_documents as docs
from recette_pwa import local_daemon, storage_permissions
from release_images import release
ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('document_fixtures',ROOT/'scripts/test-recette-documents.py')
fixtures=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixtures)
TOOL='postgres:16-alpine@sha256:93d55776e04376e19adb2733e3ccebb4392ee7dd86d8ff238503b30fe719c84f'


def run(args, **kwargs):
    return subprocess.run(args,check=True,capture_output=True,timeout=90,**kwargs).stdout


class IsolatedRestore(unittest.TestCase):
    def test_five_databases_documents_hashes_permissions_and_readonly_probe(self):
        local_daemon()
        _,_,images=release(ROOT,'recette')
        for image in (TOOL,images['factures-api']):run(['docker','image','inspect',image])
        prefix='wavy-pwa-restore-test-'+uuid.uuid4().hex[:12]
        postgres=prefix+'-postgres'; volume=prefix+'-documents';app=prefix+'-app'
        created=[];created_volume=False
        self.assertTrue(prefix.startswith('wavy-pwa-restore-test-'))
        with tempfile.TemporaryDirectory(prefix=prefix) as tmp:
            folder=Path(tmp);folder.chmod(0o700)
            try:
                run(['docker','volume','create','--label','wavy.test=recette-pwa-restore',volume]);created_volume=True
                run(['docker','run','-d','--name',postgres,'--pull','never','--network','none',
                     '--tmpfs','/var/lib/postgresql/data','-e','POSTGRES_HOST_AUTH_METHOD=trust',TOOL]);created.append(postgres)
                for attempt in range(60):
                    ready=subprocess.run(['docker','exec',postgres,'pg_isready','-h','127.0.0.1','-U','postgres'],capture_output=True)
                    if ready.returncode==0:break
                    time.sleep(.2)
                self.assertEqual(ready.returncode,0)
                expected=hashlib.sha256(b'private-fixture-document').hexdigest()
                for db in docs.DATABASES:
                    run(['docker','exec',postgres,'createdb','-U','postgres','fixture_'+db])
                    sql=f"CREATE TABLE fixture (tenant bigint,company bigint,note bigint,document_hash text); INSERT INTO fixture VALUES (1,2,3,'{expected}');"
                    run(['docker','exec','-i',postgres,'psql','-v','ON_ERROR_STOP=1','-U','postgres','-d','fixture_'+db],input=sql.encode())
                    dump=run(['docker','exec',postgres,'pg_dump','-U','postgres','-d','fixture_'+db,'-Fc'])
                    file=folder/(db+'.dump');file.write_bytes(dump);file.chmod(0o600)
                fixtures.archive(folder/'justificatifs.tar')
                docs.seal(folder,'fixture-store',100,101);self.assertTrue(docs.verify(folder)['verified'])
                for db in docs.DATABASES:
                    run(['docker','exec',postgres,'createdb','-U','postgres','restored_'+db])
                    run(['docker','exec','-i',postgres,'pg_restore','--exit-on-error','--no-owner','-U','postgres','-d','restored_'+db],input=(folder/(db+'.dump')).read_bytes())
                    restored=run(['docker','exec',postgres,'psql','-At','-U','postgres','-d','restored_'+db,
                                  '-c','SELECT tenant,company,note,document_hash FROM fixture'])
                    self.assertEqual(restored.decode().strip(),'1|2|3|'+expected)
                script='test -z "$(ls -A /restore)"; tar -xpf - -C /restore; stat -c "%u:%g:%a" /restore; sha256sum /restore/'+fixtures.DOCUMENT
                output=run(['docker','run','--rm','-i','--pull','never','--network','none','--mount',f'type=volume,source={volume},target=/restore',
                            '--entrypoint','sh',TOOL,'-ec',script],input=(folder/'justificatifs.tar').read_bytes())
                self.assertIn(b'100:101:700',output);self.assertIn(expected.encode(),output)
                run(['docker','run','-d','--name',app,'--pull','never','--network','none','--read-only','--user','100:101',
                     '--mount',f'type=volume,source={volume},target=/app/justificatifs','--entrypoint','sh',images['factures-api'],'-c','sleep 90']);created.append(app)
                storage_permissions(app,require_capacity=False)
                run(['docker','run','--rm','--pull','never','--network','none','--mount',f'type=volume,source={volume},target=/restore',
                     '--entrypoint','sh',TOOL,'-ec','chmod 0644 /restore/'+fixtures.DOCUMENT])
                with self.assertRaisesRegex(ValueError,'Stockage privé'):
                    storage_permissions(app,require_capacity=False)
            finally:
                for name in reversed(created):run(['docker','rm','-f',name])
                if created_volume:run(['docker','volume','rm',volume])


if __name__=='__main__':unittest.main()
