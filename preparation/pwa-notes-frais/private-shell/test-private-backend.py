#!/usr/bin/env python3
"""Tests Unix locaux/arguments simulés ; aucun Docker ni volume réel."""
import importlib.util
import multiprocessing
import os
from pathlib import Path
import signal
import socket
import tempfile
import time
import unittest
from unittest.mock import patch

P=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('backend',P/'private-backend.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def open_in_parent(directory,reply):
    root=Path(directory);b=m.Backend(root/'unused.env',root/'state',root/'socket',root/'secret/cookie',30)
    def probe():reply.send(b.child.pid)
    b.session_probe=probe
    b.test_window({'notAfter':time.time()+60})


class Backend(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/'state').mkdir(mode=0o700);(self.root/'socket').mkdir(mode=0o755)
        (self.root/'secret').mkdir(mode=0o700)
        cookie=self.root/'secret/cookie';cookie.write_text('WAVY_SESSION=fixture');cookie.chmod(0o600)
        self.b=m.Backend(self.root/'unused.env',self.root/'state',self.root/'socket',cookie,1)
        self.b.run_id='a'*32
    def test_close_unlinks_socket_even_when_docker_is_broken(self):
        server=socket.socket(socket.AF_UNIX);server.bind(str(self.root/'socket/gate.sock'))
        self.addCleanup(server.close)
        with patch.object(self.b,'command',side_effect=ValueError('Docker unavailable')) as command,patch.object(self.b,'route'):
            self.b.close();command.assert_not_called()
        self.assertFalse((self.root/'socket/gate.sock').exists())
        self.assertFalse(m.shared.operation.read_private(self.root/'state/edge.json')['closureBlocked'])
    def test_failed_closure_probe_keeps_latch(self):
        with patch.object(self.b,'route',side_effect=ValueError('probe')):
            with self.assertRaises(ValueError):self.b.close()
        self.assertTrue(m.shared.operation.read_private(self.root/'state/edge.json')['closureBlocked'])
    def test_real_child_window_expires_and_closes(self):
        self.b.session_probe=lambda:None
        self.b.test_window({'notAfter':time.time()+60})
        self.assertIsNone(self.b.child);self.assertIsNone(self.b.cookie)
        self.assertFalse((self.root/'socket/gate.sock').exists())
    def test_parent_sigkill_kills_gate_without_docker(self):
        ctx=multiprocessing.get_context('fork');reader,writer=ctx.Pipe(False)
        parent=ctx.Process(target=open_in_parent,args=(self.root,writer));parent.start();writer.close()
        self.addCleanup(reader.close)
        try:
            self.assertTrue(reader.poll(10));pid=reader.recv()
            parent.kill();parent.join(5);self.assertFalse(parent.is_alive())
            closed=False
            for attempt in range(50):
                with socket.socket(socket.AF_UNIX) as client:
                    try:client.connect(str(self.root/'socket/gate.sock'))
                    except OSError:closed=True;break
                time.sleep(.05)
            self.assertTrue(closed,'gate enfant toujours vivant après SIGKILL parent')
            self.b.close_socket()
        finally:
            if parent.is_alive():parent.kill();parent.join(5)
    def test_child_argv_has_no_secret_and_pipe_is_inherited_without_global_lock(self):
        self.b.session_probe=lambda:None
        # Le test réel précédent couvre le démarrage ; on inspecte le contrat Popen ici.
        import subprocess
        original=subprocess.Popen;calls=[]
        def capture(args,**kwargs):
            calls.append((args,kwargs.get('pass_fds')))
            return original(args,**kwargs)
        with patch.object(m.subprocess,'Popen',side_effect=capture):self.b.test_window({'notAfter':time.time()+60})
        self.assertNotIn('fixture',str(calls[0][0]));self.assertEqual(len(calls[0][1]),1)
    def test_closed_rollback_uses_private_bind_and_never_no_start(self):
        plan=m.shared.config.read_plan(P.parent/'release-plan.json')
        cmd=['docker','compose'];clean={}
        with patch.object(m.config,'validate'),patch.object(self.b,'compose',return_value=(cmd,clean)),patch.object(self.b,'command') as command:
            self.b.deploy('erp-shell',plan,'rollback')
            args=command.call_args.args[0]
            self.assertIn('--no-build',args);self.assertIn('--pull',args);self.assertIn('never',args)
            self.assertIn('-d',args);self.assertNotIn('--no-start',args)
    def test_snapshot_refuses_unreproducible_shell_mounts_or_public_port(self):
        plan=m.shared.config.read_plan(P.parent/'release-plan.json')
        actual={'HostConfig':{'PortBindings':{'80/tcp':[{'HostIp':'127.0.0.1','HostPort':'24443'}]}},
                'Mounts':[],'Config':{'Env':[]}}
        baseline={'services':{'wavy-erp-shell-preprod':{'environment':{}}}}
        with patch.object(self.b,'container',return_value=actual),patch.object(m.config.base,'render',return_value=baseline),patch.object(m.shared.DockerBackend,'snapshot',return_value=plan):
            self.assertIn('privateSnapshot',self.b.snapshot(plan))
            actual['Mounts']=[{'Type':'bind','RW':False,'Source':'/unreviewed','Destination':'/etc/nginx/nginx.conf'}]
            with self.assertRaisesRegex(ValueError,'Montage'):self.b.snapshot(plan)
            actual['Mounts']=[]
            actual['HostConfig']['PortBindings']['80/tcp'][0]['HostIp']='0.0.0.0'
            with self.assertRaisesRegex(ValueError,'Publication'):self.b.snapshot(plan)

    def test_expired_proof_deadline_never_starts_child(self):
        with patch.object(m.subprocess,'Popen') as child:
            with self.assertRaises(ValueError):self.b.test_window({'notAfter':time.time()-1})
            child.assert_not_called()

    def test_canceled_window_never_starts_child(self):
        self.b.stop_requested=True
        with patch.object(m.subprocess,'Popen') as child:
            with self.assertRaises(InterruptedError):self.b.test_window({'notAfter':time.time()+60})
            child.assert_not_called()

    def test_missing_gate_directory_is_tolerated_only_for_explicit_early_abandon(self):
        (self.root/'socket').rmdir()
        with self.assertRaises(FileNotFoundError):self.b.close_socket()
        self.b.close_socket(missing_ok=True)
        (self.root/'socket').symlink_to(self.root/'state')
        with self.assertRaises(ValueError):self.b.close_socket(missing_ok=True)

    def test_incomplete_isolated_cleanup_prevents_reservation_release(self):
        self.b.isolated_cleanup_guard()
        attempt=self.root/'state/restore-attempt.json'
        m.shared.write_json(attempt,{'phase':'creating'})
        with self.assertRaises(ValueError):self.b.isolated_cleanup_guard()
        m.shared.write_json(attempt,{'phase':'cleaned'})
        report=self.root/'state/schema-validation.json'
        m.shared.write_json(report,{'cleanup':False})
        with self.assertRaises(ValueError):self.b.isolated_cleanup_guard()
        m.shared.write_json(report,{'cleanup':True})
        self.b.isolated_cleanup_guard()

    def test_schema_report_hash_run_images_and_source_are_verified(self):
        schema=m.load(P/'isolated-validator.py','fixture_schema')
        report={'status':'passed','cleanup':True,'run':self.b.run_id,'backup':{'directory':'fixture'},
                'project':'wavy-pwa-restore-'+self.b.run_id+'-1234abcd',
                'planHash':'b'*64,'runnerSourceSha256':schema.digest(P/'IsolatedSchemaValidator.java'),'images':{}}
        path=self.root/'state/schema-validation.json'
        m.shared.write_json(path,report)
        attempt={'run':self.b.run_id,'backup':report['backup'],'project':report['project'],'phase':'cleaned'}
        m.shared.write_json(self.root/'state/restore-attempt.json',attempt)
        proof={'backup':report['backup'],'planHash':report['planHash'],'project':report['project'],
               'schemaValidation':{'reportSha256':schema.digest(path),'images':{}}}
        self.b.verify_schema(proof)
        for key,value in (('phase','creating'),('phase','docker-cleaned'),('run','foreign'),('backup',{}),('project','foreign')):
            m.shared.write_json(self.root/'state/restore-attempt.json',dict(attempt,**{key:value}))
            with self.assertRaises(ValueError):self.b.verify_schema(proof)
        m.shared.write_json(self.root/'state/restore-attempt.json',attempt)
        for key,value in (('run','foreign'),('status','failed'),('cleanup',False),('planHash','wrong'),
                          ('runnerSourceSha256','changed'),('images',{'foreign':{}})):
            altered=dict(report,**{key:value});m.shared.write_json(path,altered)
            candidate=dict(proof,schemaValidation=dict(proof['schemaValidation'],reportSha256=schema.digest(path)))
            with self.assertRaises(ValueError):self.b.verify_schema(candidate)
        m.shared.write_json(path,report)
        proof['schemaValidation']['reportSha256']='f'*64
        with self.assertRaises(ValueError):self.b.verify_schema(proof)

    def test_invalid_duration_and_newline_cookie_rejected(self):
        self.assertIsNone(m.gate.session_hash('WAVY_SESSION=fixture\nInjected: yes'))
        with self.assertRaises(ValueError):m.Backend(self.root/'unused',self.root/'state',self.root/'socket',seconds=901)

if __name__=='__main__':unittest.main()
