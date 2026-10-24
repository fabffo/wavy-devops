#!/usr/bin/env python3
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

P=Path(__file__).resolve().parent
class Isolation(unittest.TestCase):
    def test_compose_cannot_reference_active_resources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);envfile=root/'fixture.env'
            values={'RESTORE_SECRET_DIR':str(root)}
            for db in ('socle','tiers','contrats','factures','tresorerie'):
                values['RESTORE_'+db.upper()+'_DB']=db
                values['RESTORE_'+db.upper()+'_USER']='restore_user'
                (root/(db+'.password')).write_text('fixture-only')
            envfile.write_text('\n'.join(k+'='+v for k,v in values.items()))
            data=json.loads(subprocess.check_output(['docker','compose','--env-file',str(envfile),'-p','wavy-pwa-restore-fixture','-f',str(P/'restore-isolated.compose.yml'),'config','--format','json'],env={'PATH':os.environ['PATH'],'HOME':os.environ['HOME']},text=True))
            self.assertEqual(len(data['services']),6)
            for service in data['services'].values():
                self.assertEqual(service['network_mode'],'none')
                self.assertFalse(service.get('ports'))
                self.assertNotIn('container_name',service)
                for mount in service['volumes']:
                    if mount['type']=='volume':self.assertNotIn('preprod',mount['source'])
                    else:self.assertTrue(mount['read_only'])
            for volume in data['volumes'].values():
                self.assertFalse(volume.get('external'))
                self.assertTrue(volume['name'].startswith('wavy-pwa-restore-fixture_'))

if __name__=='__main__':unittest.main()
