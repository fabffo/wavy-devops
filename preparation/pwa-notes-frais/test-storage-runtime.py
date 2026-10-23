#!/usr/bin/env python3
"""Adaptateur Bash stockage avec Docker/hostname/stat simulés ; volumes actifs inaccessibles."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

C = Path(__file__).resolve().parent


class StorageRuntime(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name);self.bin = self.root/'bin';self.bin.mkdir()
        self.docs = self.root/'documents';self.docs.mkdir()
        (self.docs/'contrats').mkdir();(self.docs/'notes-frais').mkdir(mode=0o700)
        (self.docs/'contrats/preserved').write_bytes(b'preserved-contract')
        self.log = self.root/'commands.jsonl'
        docker = '''import json,os,subprocess,sys
from pathlib import Path
args=sys.argv[1:]
with open(os.environ['MOCK_LOG'],'a') as f:f.write(json.dumps(args)+'\\n')
if args[:2]==['context','inspect']:print('unix:///var/run/docker.sock')
elif args[:2]==['volume','inspect']:
    print('wavy-preprod' if 'com.docker.compose.project' in ' '.join(args) else 'documents-preprod')
elif args[0]=='run':
    if '100:101' in args and os.environ.get('MOCK_UNREADABLE')=='1':sys.exit(1)
    script=args[-1].replace('/documents',os.environ['MOCK_DOCUMENTS'])
    sys.exit(subprocess.run(['/bin/bash','-eu','-c',script]).returncode)
elif args[0] not in ('info','compose','image'):sys.exit(90)
'''
        for name, source in {'docker':docker, 'hostname':"print('wavy-preprod')",
                             'stat':"import os,sys; print(os.environ.get('MOCK_OWNER','100:101')+':'+oct(os.stat(sys.argv[-1]).st_mode & 0o777)[2:])"}.items():
            file=self.bin/name;file.write_text('#!'+sys.executable+'\n'+source+'\n');file.chmod(0o755)
        self.env={**os.environ,'PATH':str(self.bin)+':/usr/bin:/bin',
                  'PWA_RELEASE_PLAN':str(C/'release-plan.json'),'PWA_RELEASE_ENV':str(self.root/'unused.env'),
                  'MOCK_DOCUMENTS':str(self.docs),'MOCK_LOG':str(self.log)}
        for name in ('DOCKER_HOST','DOCKER_CONTEXT','MOCK_OWNER','MOCK_UNREADABLE'):
            self.env.pop(name,None)

    def run_storage(self, **env):
        return subprocess.run(['bash',str(C/'scripts/runtime-action.sh'),'storage'],
                              env={**self.env,**env},capture_output=True,text=True)

    def test_storage_is_only_read_with_owner_access(self):
        result=self.run_storage();self.assertEqual(result.returncode,0,result.stderr)
        commands=[json.loads(line) for line in self.log.read_text().splitlines()]
        runs=[args for args in commands if args[0]=='run']
        self.assertEqual(len(runs),2)
        for args in runs:
            self.assertEqual(args[args.index('--network')+1],'none')
            self.assertIn('--read-only',args)
            self.assertIn('readonly',args[args.index('--mount')+1])
            self.assertNotIn('mkdir',args[-1]);self.assertNotIn('chown',args[-1])
        self.assertEqual((self.docs/'contrats/preserved').read_bytes(),b'preserved-contract')

    def test_absent_storage_rejected(self):
        (self.docs/'notes-frais').rmdir()
        self.assertNotEqual(self.run_storage().returncode,0)

    def test_unreadable_storage_rejected(self):
        self.assertNotEqual(self.run_storage(MOCK_UNREADABLE='1').returncode,0)

    def test_wrong_owner_permissions_and_symlink_rejected(self):
        self.assertNotEqual(self.run_storage(MOCK_OWNER='200:200').returncode,0)
        (self.docs/'notes-frais').chmod(0o755)
        self.assertNotEqual(self.run_storage().returncode,0)
        (self.docs/'notes-frais').rmdir();(self.docs/'notes-frais').symlink_to(self.docs/'contrats')
        self.assertNotEqual(self.run_storage().returncode,0)

    def test_edge_probe_requires_explicit_marker_and_all_paths(self):
        envfile=self.root/'unused.env';envfile.write_text('WAVY_PUBLIC_URL=https://fixture.invalid\n');envfile.chmod(0o600)
        curl=self.bin/'curl'
        curl.write_text('#!'+sys.executable+"\nimport os,sys\nmode=os.environ.get('MOCK_EDGE','closed')\nif mode=='down':sys.exit(7)\nprint('HTTP/1.1 404 Not Found')\nif mode=='closed':print('X-Wavy-PWA-Gate: closed')\nprint('\\n404',end='')\n")
        curl.chmod(0o755)
        for mode,expected in [('closed',0),('missing-marker',1),('down',1)]:
            result=subprocess.run(['bash',str(C/'scripts/runtime-action.sh'),'closed'],
                                  env={**self.env,'MOCK_EDGE':mode},capture_output=True,text=True)
            self.assertEqual(result.returncode==0,expected==0,result.stderr)


if __name__=='__main__':unittest.main()
