#!/usr/bin/env python3
"""Barrière privée Unix, fermée au démarrage ; une session, durée maximale 900 s.
Aucun endpoint d'ouverture. Aucun état d'ouverture persistant. Aucun port TCP.
"""
import argparse
import hashlib
import math
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler
import os
from pathlib import Path
import signal
import socketserver
import stat
import threading
import time

COOKIE = 'WAVY_SESSION'
MAX_SECONDS = 900


def session_hash(header):
    try:
        if any(ord(c)<32 or ord(c)==127 for c in header): return None
        # Rejeter les cookies ambigus au lieu de choisir une valeur arbitraire.
        if sum(part.strip().startswith(COOKIE+'=') for part in header.split(';')) != 1:
            return None
        cookies = SimpleCookie(); cookies.load(header)
        value = cookies[COOKIE].value
        if not value or any(ord(c) < 33 for c in value): return None
        return hashlib.sha256(value.encode()).digest()
    except (KeyError, ValueError, CookieError): return None


def private_file(path):
    path = Path(path)
    parent = path.parent.stat()
    if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700 or path.parent.is_symlink():
        raise ValueError('Répertoire privé 0700 requis')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd) as stream:
        s = os.fstat(stream.fileno())
        if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) != 0o600 or s.st_size > 8192:
            raise ValueError('Fichier privé régulier 0600 requis')
        return stream.read()


class Lease:
    def __init__(self, mono=time.monotonic, wall=time.time):
        self.mono, self.wall = mono, wall
        self.close()

    def close(self, *args):
        self.grant = None
        self.not_after = None

    def authorize(self, cookie, seconds, not_after=None):
        digest = session_hash(cookie)
        if digest is None or type(seconds) is not int or not 1 <= seconds <= MAX_SECONDS:
            raise ValueError('Session unique et durée 1..900 secondes requises')
        if not_after is not None and (not math.isfinite(not_after) or not_after<=self.wall()):
            raise ValueError('Échéance absolue expirée/invalide')
        self.not_after=not_after
        self.grant = (digest, self.mono(), self.wall(), seconds)

    def permits(self, header):
        grant = self.grant
        if grant is None: return False
        digest, start, opened, seconds = grant
        # Monotone borne la durée même si l'horloge UTC recule. Toute anomalie ferme.
        if (not 0 <= self.mono()-start < seconds or not 0 <= self.wall()-opened < seconds
                or (self.not_after is not None and self.wall()>=self.not_after)):
            self.close(); return False
        return session_hash(header) == digest


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def handler(lease):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            allowed = self.path == '/check' and lease.permits(self.headers.get('Cookie', ''))
            self.send_response(204 if allowed else 403)
            self.send_header('Cache-Control', 'no-store'); self.end_headers()
        def log_message(self, *args): pass
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--socket-dir', required=True, type=Path)
    parser.add_argument('--session-fd', type=int)
    parser.add_argument('--parent-pid', type=int)
    parser.add_argument('--not-after',type=float)
    parser.add_argument('--seconds', type=int, default=900)
    args = parser.parse_args()
    # Le répertoire de socket est distinct de celui des secrets ; seul l'opérateur
    # peut créer/remplacer son socket, les workers Docker peuvent le traverser.
    info = args.socket_dir.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o755:
        raise ValueError('Répertoire socket appartenant à l’opérateur 0755 requis')
    lease = Lease()
    if args.session_fd is not None:
        if args.parent_pid != os.getppid() or not stat.S_ISFIFO(os.fstat(args.session_fd).st_mode):
            raise ValueError('Pipe du parent requis')
        cookie = os.read(args.session_fd,8193).decode()
        os.close(args.session_fd)
        if len(cookie)>8192: raise ValueError('Session trop longue')
        lease.authorize(cookie,args.seconds,args.not_after)
        del cookie
    socket = args.socket_dir/'gate.sock'
    # Ne jamais remplacer aveuglément un fichier/socket préexistant.
    with Server(str(socket), handler(lease)) as server:
        identity = socket.stat()
        os.chmod(socket, 0o666)  # API lecture seule ; le parent interdit son remplacement.
        signal.signal(signal.SIGUSR1, lease.close)
        timer = threading.Timer(args.seconds, lease.close); timer.daemon=True; timer.start()
        try: server.serve_forever()
        finally:
            lease.close(); timer.cancel()
            if socket.exists() and os.path.samestat(identity,socket.stat()): socket.unlink()

if __name__ == '__main__': main()
