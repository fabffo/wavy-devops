#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import tempfile
import socket
import threading
import unittest

P=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('gate',P/'session-gate.py')
gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)

class Session(unittest.TestCase):
    def test_closed_by_default_and_restart(self):
        self.assertFalse(gate.Lease().permits('WAVY_SESSION=fixture'))
        lease=gate.Lease();lease.authorize('WAVY_SESSION=fixture',60)
        self.assertTrue(lease.permits('WAVY_SESSION=fixture'))
        self.assertFalse(gate.Lease().permits('WAVY_SESSION=fixture'))

    def test_one_session_and_explicit_close(self):
        lease=gate.Lease();lease.authorize('WAVY_SESSION=fixture',60)
        for header in ('','WAVY_SESSION=other','WAVY_SESSION=fixture; WAVY_SESSION=other'):
            self.assertFalse(lease.permits(header))
        self.assertTrue(lease.permits('foo=bar; WAVY_SESSION=fixture'))
        lease.close();self.assertFalse(lease.permits('WAVY_SESSION=fixture'))

    def test_expiration_and_clock_rollback(self):
        for mono,wall in ((61,60),(2,-1),(2,61),(60,60)):
            clock=[0,0];lease=gate.Lease(lambda:clock[0],lambda:clock[1])
            lease.authorize('WAVY_SESSION=fixture',60)
            clock[:]=[mono,wall]
            self.assertFalse(lease.permits('WAVY_SESSION=fixture'))
            clock[:]=[0,0];self.assertFalse(lease.permits('WAVY_SESSION=fixture'))

    def test_http_gate_expires_with_same_process_and_socket(self):
        clock=[0,0];lease=gate.Lease(lambda:clock[0],lambda:clock[1])
        lease.authorize('WAVY_SESSION=fixture',60)
        with tempfile.TemporaryDirectory() as tmp:
            path=str(Path(tmp)/'gate.sock')
            server=gate.Server(path,gate.handler(lease))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            def status(cookie):
                with socket.socket(socket.AF_UNIX) as client:
                    client.connect(path)
                    client.sendall(('GET /check HTTP/1.0\r\nCookie: '+cookie+'\r\n\r\n').encode())
                    return client.recv(4096).split(b' ')[1]
            try:
                self.assertEqual(status('WAVY_SESSION=fixture'),b'204')
                self.assertEqual(status('WAVY_SESSION=other'),b'403')
                clock[:]=[60,60]
                self.assertEqual(status('WAVY_SESSION=fixture'),b'403')
            finally:server.shutdown();server.server_close();thread.join()

    def test_absolute_proof_deadline_is_checked_in_child_lease(self):
        clock=[100,100];lease=gate.Lease(lambda:clock[0],lambda:clock[1])
        lease.authorize('WAVY_SESSION=fixture',900,105)
        self.assertTrue(lease.permits('WAVY_SESSION=fixture'))
        clock[:]=[105,105]
        self.assertFalse(lease.permits('WAVY_SESSION=fixture'))
        with self.assertRaises(ValueError):lease.authorize('WAVY_SESSION=fixture',900,105)

    def test_duration_bounds(self):
        for duration in (0,-1,901,True,1.2):
            with self.assertRaises(ValueError):gate.Lease().authorize('WAVY_SESSION=fixture',duration)

    def test_private_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);root.chmod(0o700)
            path=root/'session';path.write_text('WAVY_SESSION=fixture');path.chmod(0o600)
            self.assertEqual(gate.private_file(path),'WAVY_SESSION=fixture')
            for mode in (0o000,0o644):
                path.chmod(mode)
                with self.assertRaises((ValueError,PermissionError)):gate.private_file(path)
            link=root/'link';link.symlink_to(path)
            with self.assertRaises(OSError):gate.private_file(link)
            root.chmod(0o777)
            with self.assertRaises(ValueError):gate.private_file(path)

if __name__=='__main__':unittest.main()
