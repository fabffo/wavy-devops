#!/usr/bin/env python3
"""Adaptateur Bash, owner/FD réels ; Docker/hostname/curl simulés, aucune cible réelle."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

P=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('fixture',P.parent/'test-storage-runtime.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)

class Runtime(unittest.TestCase):
    def setUp(self):
        self.f=fixture.StorageRuntime();self.f.setUp();self.addCleanup(self.f.doCleanups)
        f=self.f
        target=f.fixture/'preparation/pwa-notes-frais/private-shell';target.mkdir()
        shutil.copyfile(P/'private-runtime.sh',target/'private-runtime.sh')
        self.runtime=target/'private-runtime.sh'
        plan=json.loads(f.plan.read_text());plan['privateProfile']='private-tunnel-v1'
        f.plan.write_text(json.dumps(plan));digest=__import__('hashlib').sha256(json.dumps(plan,sort_keys=True).encode()).hexdigest()
        f.operation.atomic_json(f.fixture/'deployments/preprod-reservation.json',{'run':f.run,'planHash':digest})
        f.operation.atomic_json(f.private/'state.json',{'run':f.run,'profile':'private-tunnel-v1','planHash':digest,'phase':'prepared'})
        curl=f.bin/'curl'
        curl.write_text('#!/usr/bin/python3\nimport os,sys\ncode=403 if "/api/notes-frais" in " ".join(sys.argv) else 404\nprint("HTTP/1.1 "+str(code))\nif os.environ.get("MISSING_MARKER")!="1":print("X-Wavy-Private-Gate: closed")\nprint("\\n"+str(code),end="")\n')
        curl.chmod(0o755)
    def execute(self,override=None):
        f=self.f
        with f.operation.Operation(f.fixture,owner=f.run) as owner:
            env={**f.env,'PWA_RELEASE_RUN':f.run,'PWA_RELEASE_LOCK_FD':str(owner.fd),
                 'PWA_RELEASE_PLAN':str(f.plan),**(override or {})}
            return subprocess.run(['bash',str(self.runtime),'closed'],env=env,pass_fds=(owner.fd,),capture_output=True,text=True)
    def test_owner_inherited_lock_and_all_closure_probes(self):
        result=self.execute();self.assertEqual(result.returncode,0,result.stderr)
    def test_absent_marker_is_not_a_closure_proof(self):
        self.assertNotEqual(self.execute({'MISSING_MARKER':'1'}).returncode,0)
    def test_wrong_owner_or_plan_refused(self):
        self.assertNotEqual(self.execute({'PWA_RELEASE_RUN':'b'*32}).returncode,0)
        self.assertNotEqual(self.execute({'PWA_RELEASE_PLAN':'/tmp/noncanonical.json'}).returncode,0)

if __name__=='__main__':unittest.main()
