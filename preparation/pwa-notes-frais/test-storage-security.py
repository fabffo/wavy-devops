#!/usr/bin/env python3
"""Régressions stockage : fixtures privées, injections déterministes, Docker local jetable optionnel."""
import hashlib
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

sys.dont_write_bytecode = True
C = Path(__file__).resolve().parent


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


helper = load(C/'scripts/provision_storage.py', 'provision_helper')
auth = load(C/'scripts/storage_authorization.py', 'storage_auth_test')
runtime_tests = load(C/'test-storage-runtime.py', 'storage_runtime_fixtures')


class DirectorySecurity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)/'documents'; self.root.mkdir()
        (self.root/'contrats').mkdir(mode=0o700)
        (self.root/'contrats/document').write_bytes(b'contract-fixture')
        self.before = (self.root/'contrats/document').stat()
        self.deadline = time.time()+60
        # Métadonnées simulées seulement dans les tests sans privilèges.
        self.chown = patch.object(helper.os, 'fchown', side_effect=self.assign)
        self.chown.start(); self.addCleanup(self.chown.stop)
        self.owner = {}
        self.check = patch.object(helper, 'compliant', side_effect=self.compliant)
        self.check.start(); self.addCleanup(self.check.stop)

    def assign(self, fd, uid, gid):
        self.owner[os.fstat(fd).st_ino] = (uid, gid)

    def compliant(self, fd):
        s = os.fstat(fd)
        if self.owner.get(s.st_ino) != (100,101) or s.st_mode & 0o7777 != 0o700:
            raise ValueError('non conforme')

    def provision(self): helper.provision(str(self.root), self.deadline)

    def preserved(self):
        p = self.root/'contrats/document'
        self.assertEqual(p.read_bytes(), b'contract-fixture')
        self.assertEqual((p.stat().st_ino,p.stat().st_mtime_ns,p.stat().st_uid,p.stat().st_gid,p.stat().st_mode),
                         (self.before.st_ino,self.before.st_mtime_ns,self.before.st_uid,self.before.st_gid,self.before.st_mode))

    def test_first_call_idempotence_and_archive(self):
        self.provision(); inode=(self.root/'notes-frais').stat().st_ino
        self.provision();self.assertEqual((self.root/'notes-frais').stat().st_ino,inode)
        self.assertEqual(len(self.owner),1);self.preserved()
        archive=Path(self.tmp.name)/'documents.tar'
        subprocess.run(['tar','--owner=100','--group=101','-cpf',str(archive),'-C',str(self.root),'contrats','notes-frais'],check=True)
        with archive.open('rb') as stream:
            r=subprocess.run([sys.executable,str(C/'scripts/preprod_document_archive.py'),'-'],stdin=stream,capture_output=True)
        self.assertEqual(r.returncode,0,r.stderr)

    def test_existing_wrong_owner_or_mode_not_repaired(self):
        p=self.root/'notes-frais';p.mkdir(mode=0o700)
        with self.assertRaises(ValueError):self.provision()
        self.assertFalse(self.owner)
        self.owner[p.stat().st_ino]=(100,101);p.chmod(0o755)
        with self.assertRaises(ValueError):self.provision()
        self.assertEqual(p.stat().st_mode & 0o777,0o755);self.preserved()

    def test_existing_and_parent_symlinks_refused(self):
        (self.root/'notes-frais').symlink_to(self.root/'contrats')
        with self.assertRaises(OSError):self.provision()
        (self.root/'notes-frais').unlink()
        (self.root/'contrats').rename(self.root/'saved-contracts')
        (self.root/'contrats').symlink_to(self.root/'saved-contracts')
        with self.assertRaises(OSError):self.provision()
        self.assertFalse(self.owner)

    def test_substitution_between_creation_and_chown_directory_or_symlink(self):
        for symlink in (False,True):
            with self.subTest(symlink=symlink):
                def replace(fd, uid, gid):
                    name=next(self.root.glob('.notes-frais.provision-*'))
                    name.rename(self.root/'original')
                    if symlink:name.symlink_to(self.root/'contrats')
                    else:name.mkdir(mode=0o700)
                    # Chown porte sur le FD original, jamais sur le remplacement.
                    self.assign(fd,uid,gid)
                    self.assertEqual(os.fstat(fd).st_ino,(self.root/'original').stat().st_ino)
                with patch.object(helper.os,'fchown',side_effect=replace):
                    with self.assertRaises(ValueError):self.provision()
                self.assertFalse((self.root/'notes-frais').exists());self.preserved()
                for p in self.root.glob('.notes-frais.provision-*'):
                    p.unlink() if p.is_symlink() else p.rmdir()
                (self.root/'original').rmdir()

    def test_concurrent_destination_is_never_overwritten(self):
        original=helper.rename_exclusive
        def competing(parent,old,new):
            (self.root/'notes-frais').mkdir(mode=0o755)
            return original(parent,old,new)
        with patch.object(helper,'rename_exclusive',side_effect=competing):
            with self.assertRaises(FileExistsError):self.provision()
        self.assertEqual((self.root/'notes-frais').stat().st_mode & 0o777,0o755);self.preserved()

    def test_interrupt_and_creation_failure_leave_traces_without_deletion(self):
        with patch.object(helper.os,'mkdir',side_effect=OSError('fixture')):
            with self.assertRaises(OSError):self.provision()
        with patch.object(helper.os,'fchown',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):self.provision()
        traces=list(self.root.glob('.notes-frais.provision-*'))
        self.assertEqual(len(traces),1);self.assertFalse((self.root/'notes-frais').exists())
        # Une reprise peut créer le dossier final mais conserve la trace orpheline.
        self.provision();self.assertTrue(traces[0].exists());self.preserved()

    def test_expiration_before_creation(self):
        self.deadline=time.time()-1
        with self.assertRaises(ValueError):self.provision()
        self.assertEqual(sorted(p.name for p in self.root.iterdir()),['contrats'])

    def test_untrusted_parent_and_symbolic_root_rejected(self):
        self.root.chmod(0o777)
        with self.assertRaises(ValueError):self.provision()
        self.root.chmod(0o755)
        link=Path(self.tmp.name)/'symbolic';link.symlink_to(self.root)
        with self.assertRaises(OSError):helper.provision(str(link),self.deadline)
        self.assertFalse((self.root/'notes-frais').exists());self.preserved()

    def test_legacy_path_reproduction_accepted_replacement(self):
        # Fragment exact de la stratégie précédente, avec chown intercepté au point de course.
        script='''test ! -L "$DOCS/notes-frais"; mkdir -m 700 "$DOCS/notes-frais";
chown() { mv "$DOCS/notes-frais" "$DOCS/original"; mkdir -m 700 "$DOCS/notes-frais"; }
test ! -L "$DOCS/notes-frais"; chown -h 100:101 "$DOCS/notes-frais";
test -d "$DOCS/notes-frais"; test ! -L "$DOCS/notes-frais";
stat() { printf 100:101:700; }; test "$(stat -c %u:%g:%a "$DOCS/notes-frais")" = 100:101:700'''
        r=subprocess.run(['bash','-eu','-c',script],env=dict(os.environ,DOCS=str(self.root)))
        self.assertEqual(r.returncode,0)
        self.assertNotEqual((self.root/'notes-frais').stat().st_ino,(self.root/'original').stat().st_ino)
        self.preserved()


class AuthorizationSecurity(unittest.TestCase):
    def setUp(self):
        self.fixture=runtime_tests.StorageRuntime();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        t=self.fixture;self.root=t.fixture;self.directory=t.private;self.plan=t.plan
        self.run=t.run
        state=auth.operation.read_private(self.directory/'state.json')
        state['prerequisites']={'checkedAt':datetime.now(timezone.utc).isoformat()}
        state['storagePreconditions']={'run':self.run,'checkedAt':time.time(),'closed':True,'preflight':True,'snapshotHash':auth.digest(state['previous']),'attempt':uuid.uuid4().hex}
        auth.operation.atomic_json(self.directory/'state.json',state)
        auth.operation.atomic_json(self.directory/'edge.json',{'mode':'closed','run':self.run,'closureBlocked':False})
        self.lock=auth.operation.Operation(self.root,owner=self.run)
        self.lock.__enter__();self.addCleanup(self.lock.__exit__)

    def ticket(self):
        fd=auth.issue(self.directory,self.root/'deployments/preprod-reservation.json',self.run,json.loads(self.plan.read_text()))
        self.addCleanup(os.close,fd);return fd

    def consume(self,fd):return auth.consume(self.root,self.plan,self.run,self.lock.fd,fd)

    def direct(self,fd=None):
        t=self.fixture
        env={**t.env,'PWA_RELEASE_PLAN':str(self.plan),'PWA_RELEASE_RUN':self.run,'PWA_RELEASE_LOCK_FD':str(self.lock.fd)}
        fds=[self.lock.fd]
        if fd is not None:env['PWA_STORAGE_AUTH_FD']=str(fd);fds.append(fd)
        return subprocess.run(['bash',str(t.runtime),'provision-storage'],env=env,pass_fds=fds,capture_output=True,text=True)

    def test_direct_with_locked_fd_and_reservation_without_authorization_refused(self):
        env={**self.fixture.env,'PWA_RELEASE_PLAN':str(self.plan),'PWA_RELEASE_RUN':self.run}
        env.pop('PWA_RELEASE_LOCK_FD',None);env.pop('PWA_STORAGE_AUTH_FD',None)
        without_fd=subprocess.run(['bash',str(self.fixture.runtime),'provision-storage'],env=env,capture_output=True)
        self.assertNotEqual(without_fd.returncode,0)
        self.assertNotEqual(self.direct().returncode,0)
        self.assertFalse(self.fixture.log.exists() and '"run"' in self.fixture.log.read_text())

    def test_legacy_preparing_predicate_was_insufficient(self):
        state=auth.operation.read_private(self.directory/'state.json')
        state.pop('storagePreconditions');auth.operation.atomic_json(self.directory/'state.json',state)
        # Ancien prédicat : preparing + snapshot suffisait, sans attestation des précontrôles.
        self.assertTrue(state['phase']=='preparing' and state['previous'] is not None)
        self.assertNotEqual(self.direct().returncode,0)
        with self.assertRaises(ValueError):self.ticket()

    def test_legacy_direct_reproduction_and_current_refusal(self):
        t=self.fixture;(t.docs/'notes-frais').rmdir()
        state=auth.operation.read_private(self.directory/'state.json');state.pop('storagePreconditions')
        auth.operation.atomic_json(self.directory/'state.json',state)
        # Ancien contrôle exact : FD partagé + état preparing et snapshot, sans capacité.
        legacy=self.root/'legacy-storage.sh'
        legacy.write_text('source "$1"\npreprod_host_guard\npreprod_backup_operation_lock\n'+r'''python3 - "$DEVOPS_ROOT" "$PWA_RELEASE_RUN" "$PWA_RELEASE_PLAN" <<'LEGACY'
import hashlib,importlib.util,json,os,sys
from pathlib import Path
root,run,plan=Path(sys.argv[1]),sys.argv[2],Path(sys.argv[3])
spec=importlib.util.spec_from_file_location('op',root/'scripts/preprod_operation.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
assert os.path.samestat(os.fstat(9),(root/'deployments/preprod.lock').stat())
r=m.read_private(root/'deployments/preprod-reservation.json');s=m.read_private(plan.parent/'state.json')
h=hashlib.sha256(json.dumps(json.loads(plan.read_text()),sort_keys=True).encode()).hexdigest()
assert r['run']==s['run']==run and r['planHash']==s['planHash']==h
assert s['phase']=='preparing' and s['previous'] is not None
LEGACY
mkdir -m 700 "$MOCK_DOCUMENTS/notes-frais"
''')
        r=subprocess.run(['bash','-eu',str(legacy),str(t.runtime.parent/'_runtime.sh')],
            env={**t.env,'PWA_RELEASE_PLAN':str(self.plan),'PWA_RELEASE_RUN':self.run,'PWA_RELEASE_LOCK_FD':str(self.lock.fd)},
            pass_fds=(self.lock.fd,),capture_output=True)
        self.assertEqual(r.returncode,0,r.stderr);self.assertTrue((t.docs/'notes-frais').is_dir())
        (t.docs/'notes-frais').rmdir()
        self.assertNotEqual(self.direct().returncode,0);self.assertFalse((t.docs/'notes-frais').exists())

    def test_valid_ticket_consumed_once_even_with_new_pipe(self):
        fd=self.ticket();self.assertGreaterEqual(fd,10);token=os.read(fd,32);readers=[]
        for unused in range(2):
            reader,writer=os.pipe();os.write(writer,token);os.close(writer)
            readers.append(reader);self.addCleanup(os.close,reader)
        self.assertGreater(self.consume(readers[0]),time.time())
        with self.assertRaises((ValueError,KeyError)):self.consume(readers[1])
        self.assertTrue(auth.operation.read_private(self.directory/'storage-authorization.json')['consumed'])

    def test_expired_ticket_and_invalidated_state_reservation_gate_plan(self):
        state_path=self.directory/'state.json';original_state=state_path.read_bytes()
        state=json.loads(original_state)
        state['prerequisites']['checkedAt']=datetime.fromtimestamp(time.time()-86400+2,timezone.utc).isoformat()
        auth.operation.atomic_json(state_path,state)
        fd=self.ticket();limited=auth.operation.read_private(self.directory/'storage-authorization.json')
        self.assertLessEqual(limited['expiresAt'],time.time()+2)
        with patch.object(auth.time,'time',return_value=limited['expiresAt']+1):
            with self.assertRaises(ValueError):self.consume(fd)
        state_path.write_bytes(original_state)
        fd=self.ticket();p=self.directory/'storage-authorization.json'
        proof=auth.operation.read_private(p);proof['issuedAt']=time.time()-61;proof['expiresAt']=time.time()-1
        auth.operation.atomic_json(p,proof)
        with self.assertRaises(ValueError):self.consume(fd)
        for name in ('state.json','edge.json','../preprod-reservation.json','runtime-plan.json'):
            with self.subTest(name=name):
                path=self.directory/name;original=path.read_bytes();fd=self.ticket()
                data=json.loads(original);data['invalidated']=True
                if name=='edge.json':data['closureBlocked']=True
                path.write_text(json.dumps(data))
                try:
                    with self.assertRaises(ValueError):self.consume(fd)
                finally:path.write_bytes(original)

    def test_wrong_action_token_and_missing_lock_refused(self):
        fd=self.ticket();p=self.directory/'storage-authorization.json'
        proof=auth.operation.read_private(p);proof['action']='storage';auth.operation.atomic_json(p,proof)
        with self.assertRaises(ValueError):self.consume(fd)
        self.ticket();reader,writer=os.pipe();os.write(writer,b'x'*32);os.close(writer)
        try:
            with self.assertRaises(ValueError):self.consume(reader)
        finally:os.close(reader)
        fd=self.ticket()
        with open(os.devnull) as other:
            with self.assertRaises(ValueError):auth.consume(self.root,self.plan,self.run,other.fileno(),fd)

    def test_missing_reservation_refuses_even_issued_capability(self):
        fd=self.ticket();(self.root/'deployments/preprod-reservation.json').unlink()
        self.assertNotEqual(self.direct(fd).returncode,0)
        self.assertFalse(self.fixture.log.exists() and '"run"' in self.fixture.log.read_text())

    def test_direct_authorized_invocation_consumes_before_docker(self):
        # Mauvais volume : refus APRÈS consommation, aucun docker run et aucune réutilisation.
        for key in ('MOCK_PROJECT','MOCK_VOLUME_LABEL','MOCK_VOLUME_NAME'):
            fd=self.ticket();self.fixture.env[key]='wrong'
            result=self.direct(fd);self.assertNotEqual(result.returncode,0)
            self.assertTrue(auth.operation.read_private(self.directory/'storage-authorization.json')['consumed'])
            with self.assertRaises((ValueError,KeyError)):self.consume(fd)
            del self.fixture.env[key]
        commands=[json.loads(line) for line in self.fixture.log.read_text().splitlines()]
        self.assertFalse(any(command[0]=='run' for command in commands))


@unittest.skipUnless(os.environ.get('WAVY_TEST_LOCAL_DOCKER') == '1', 'Docker local jetable explicitement sélectionné')
class LocalDockerSecurity(unittest.TestCase):
    def test_real_metadata_subpath_and_substitutions(self):
        env={k:v for k,v in os.environ.items() if k not in ('DOCKER_HOST','DOCKER_CONTEXT')}
        endpoint=subprocess.check_output(['docker','context','inspect','--format','{{.Endpoints.docker.Host}}'],env=env,text=True).strip()
        self.assertTrue(endpoint.startswith('unix://'))
        image='python:3.12-alpine@sha256:b658b05ce9c4eb97ec6fc19424818a1f31993659c2b505a532f470e83807815d'
        subprocess.run(['docker','image','inspect',image],env=env,check=True,capture_output=True)
        volume='wavy-storage-security-test-'+uuid.uuid4().hex
        base=['docker','run','--rm','--pull','never','--network','none','--read-only',
              '--security-opt','no-new-privileges:true','--cap-drop','ALL','--cap-add','CHOWN','--cap-add','DAC_OVERRIDE',
              '--mount','type=volume,source='+volume+',target=/documents',
              '--mount','type=bind,source='+str(C/'scripts/provision_storage.py')+',target=/provision_storage.py,readonly',
              '--entrypoint','python3',image,'-B']
        subprocess.run(['docker','volume','create',volume],env=env,check=True,capture_output=True)
        script = r'''import os,sys,time,stat,tempfile
sys.path.insert(0,'/')
import provision_storage as h
os.mkdir('/documents/contrats',0o700)
with open('/documents/contrats/document','wb') as f:f.write(b'fixture-contract')
os.chown('/documents/contrats',100,101);os.chown('/documents/contrats/document',100,101)
original=os.stat('/documents/contrats/document')
for unused in range(2):
 h.provision(deadline=time.time()+60)
 s=os.stat('/documents/notes-frais')
 assert (s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode))==(100,101,0o700)
assert open('/documents/contrats/document','rb').read()==b'fixture-contract'
assert os.stat('/documents/contrats/document').st_ino==original.st_ino
real=h.os.fchown
for symlink in (False,True):
 root=tempfile.mkdtemp(dir='/documents');os.mkdir(root+'/contrats',0o700)
 def replace(fd,uid,gid):
  name=next(n for n in os.listdir(root) if n.startswith('.notes-frais.provision-'))
  os.rename(root+'/'+name,root+'/original')
  if symlink:os.symlink(root+'/contrats',root+'/'+name)
  else:os.mkdir(root+'/'+name,0o755)
  real(fd,uid,gid)
  assert os.fstat(fd).st_ino==os.stat(root+'/original').st_ino
 h.os.fchown=replace
 try:
  try:h.provision(root,time.time()+60)
  except ValueError:pass
  else:raise AssertionError('substitution accepted')
 finally:h.os.fchown=real
 assert os.stat(root+'/contrats').st_uid==0
 assert not os.path.exists(root+'/notes-frais')
'''
        try:
            subprocess.run(base+['-c',script],env=env,check=True,capture_output=True)
            subprocess.run(['docker','run','--rm','--pull','never','--network','none','--read-only','--user','100:101',
                '--mount','type=volume,source='+volume+',target=/documents,volume-subpath=notes-frais,readonly',
                '--entrypoint','python3',image,'-B','-c','import os; assert os.access("/documents",os.R_OK|os.X_OK)'],
                env=env,check=True,capture_output=True)
        finally:
            subprocess.run(['docker','volume','rm',volume],env=env,check=True,capture_output=True)


if __name__=='__main__':unittest.main()
