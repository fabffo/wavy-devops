#!/usr/bin/env python3
"""Contrôle des artefacts Angular locaux déjà construits ; aucun build."""
import json
from pathlib import Path
import re
import unittest

class Assets(unittest.TestCase):
    def test_local_dist_prefix_and_worker(self):
        root=Path('/home/ffo/projets/wavy-pwa/dist/wavy-pwa/browser')
        if not root.is_dir(): self.skipTest('dist PWA local absent')
        index=(root/'index.html').read_text()
        self.assertIn('<base href="/pwa/">',index)
        for url in re.findall(r'(?:src|href)="([^"]+)"',index):
            if url=='/pwa/': continue
            self.assertFalse(url.startswith(('http:', 'https:', '/')),url)
            self.assertTrue((root/url).is_file(),url)
        manifest=json.loads((root/'manifest.webmanifest').read_text())
        self.assertEqual(manifest['scope'],'/pwa/')
        self.assertTrue(manifest['start_url'].startswith('/pwa/'))
        for icon in manifest['icons']: self.assertTrue((root/icon['src']).is_file())
        ngsw=json.loads((root/'ngsw.json').read_text())
        self.assertEqual(ngsw['index'],'/pwa/index.html')
        self.assertEqual(ngsw['dataGroups'],[])
        for url in ngsw['hashTable']:
            self.assertTrue(url.startswith('/pwa/'),url)
            self.assertTrue((root/url.removeprefix('/pwa/')).is_file(),url)
        self.assertTrue((root/'ngsw-worker.js').is_file())
        for js in root.glob('main-*.js'):
            self.assertNotIn('http://localhost:8088/api',js.read_text())

if __name__=='__main__':unittest.main()
