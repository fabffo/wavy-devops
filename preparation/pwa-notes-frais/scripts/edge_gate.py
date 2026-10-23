#!/usr/bin/env python3
"""Barrière HTTP d'autorisation locale, indépendante de Docker et du Shell. Fermée par défaut."""
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('operation', ROOT/'scripts/preprod_operation.py')
operation = importlib.util.module_from_spec(spec); spec.loader.exec_module(operation)


class Gate:
    def __init__(self, path): self.path = Path(path)

    def read(self):
        try:
            data = operation.read_private(self.path)
            if not isinstance(data, dict): raise ValueError()
            if data.get('mode') not in ('closed', 'open'): raise ValueError()
            return data
        except (OSError, ValueError, KeyError): return {'mode':'closed', 'notesReadonly':True}

    def permits(self, route):
        data = self.read()
        if route == '/notes-write': return data.get('notesReadonly') is False
        if route != '/check' or data.get('mode') != 'open': return False
        try:
            # Aucun cache : chaque sous-requête relit une échéance absolue.
            current = datetime.now(timezone.utc)
            return (datetime.fromisoformat(data['openedAt']) <= current < datetime.fromisoformat(data['notAfter'])
                    and bool(data['run']) and data.get('closureBlocked') is False)
        except (ValueError, KeyError, TypeError): return False

    def close(self, run, readonly=False):
        operation.atomic_json(self.path, {'mode':'closed','run':run,'notesReadonly':readonly,
                                         'closureBlocked':True})

    def confirm_closed(self):
        data = self.read()
        if data['mode'] != 'closed': raise ValueError('Barrière non fermée')
        data['closureBlocked'] = False
        operation.atomic_json(self.path, data)

    def allow_notes(self, run):
        data = self.read()
        if data.get('mode') != 'closed' or data.get('run') != run or data.get('closureBlocked') is not False:
            raise ValueError('Fermeture confirmée requise avant reprise Notes de frais')
        data['notesReadonly'] = False
        operation.atomic_json(self.path, data)

    def open(self, run, expiry):
        data = self.read()
        if data.get('mode') != 'closed' or data.get('run') != run or data.get('closureBlocked') is not False:
            raise ValueError('Fermeture non confirmée : activation interdite')
        current = datetime.now(timezone.utc)
        if datetime.fromisoformat(expiry) <= current:
            raise ValueError('Preuve expirée avant ouverture edge')
        operation.atomic_json(self.path, {'mode':'open','run':run,'notAfter':expiry,'openedAt':current.isoformat(),
                                         'notesReadonly':False,'closureBlocked':False})


def handler(gate):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            permitted = gate.permits(self.path)
            self.send_response(204 if permitted else 403)
            self.send_header('Cache-Control','no-store')
            self.end_headers()
        def log_message(self,*args): pass  # Jamais chemin, session ou query dans les logs.
    return Handler


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,default=ROOT/'deployments/pwa-release/edge.json')
    args = parser.parse_args()
    # Service de lecture seul : aucune route HTTP ne peut ouvrir/modifier la barrière.
    ThreadingHTTPServer(('127.0.0.1',24444),handler(Gate(args.state))).serve_forever()
