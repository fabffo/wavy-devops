#!/usr/bin/env python3
"""Serveur LOCAL de fixtures pour Playwright ; aucun proxy vers une API réelle."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
import mimetypes
ROOT=Path(__file__).resolve().parents[3]
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url=unquote(urlsplit(self.path).path)
        if '..' in Path(url).parts: self.send_error(400);return
        if url=='/pwa-integration.json':
            self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b'{"enabled":true}');return
        if url.startswith('/api/'):
            self.send_error(503,'API réelle interdite dans les fixtures');return
        if url.startswith('/pwa/'):
            repo='wavy-pwa';relative=url[len('/pwa/'):];base='/pwa/'
        elif url.startswith('/modules/factures/'):
            repo='wavy-factures-front';relative=url[len('/modules/factures/'):];base='/modules/factures/'
        else: repo='wavy-erp-shell';relative=url.lstrip('/');base='/'
        folder=ROOT/repo/'dist'/repo/'browser';target=folder/relative
        if not target.is_file():
            if Path(relative).suffix: self.send_error(404);return
            target=folder/'index.html'
        if not target.is_file(): self.send_error(503,'Build local absent');return
        content=target.read_bytes()
        if target.suffix=='.html':content=content.replace(b'<base href="/">',f'<base href="{base}">'.encode())
        self.send_response(200);self.send_header('Content-Type',mimetypes.guess_type(target)[0] or 'application/octet-stream');self.end_headers();self.wfile.write(content)
    def log_message(self,*args): pass
ThreadingHTTPServer(('127.0.0.1',14327),Handler).serve_forever()
