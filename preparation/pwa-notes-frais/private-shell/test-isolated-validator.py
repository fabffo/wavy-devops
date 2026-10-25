#!/usr/bin/env python3
"""Actual synthetic Docker/PG/JVM tests opt-in; unit guards always local, no PREPROD."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
import threading
import unittest
from unittest.mock import patch

P = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('validator_test_subject', P / 'isolated-validator.py')
v = importlib.util.module_from_spec(spec); spec.loader.exec_module(v)


def container_data(project):
    return {'Id': 'a'*64, 'Config': {'Image': v.PG_IMAGE, 'Labels': {
        'com.docker.compose.project': project, 'com.docker.compose.service': 'factures'}},
        'HostConfig': {'NetworkMode': 'none', 'ReadonlyRootfs': True},
        'State': {'Running': True}, 'Mounts': []}


class Guards(unittest.TestCase):
    def test_network_foreign_project_mount_and_privilege_refused(self):
        project='wavy-pwa-restore-fixture'
        good=container_data(project);v.guard_container(good,project)
        for mutation in ('network','project','service','image','volume','bind','privileged','ports','rootfs'):
            with self.subTest(mutation=mutation):
                d=copy.deepcopy(good)
                if mutation=='network':d['HostConfig']['NetworkMode']='wavy-preprod'
                elif mutation=='project':d['Config']['Labels']['com.docker.compose.project']='wavy-preprod'
                elif mutation=='service':d['Config']['Labels']['com.docker.compose.service']='socle'
                elif mutation=='image':d['Config']['Image']='postgres:latest'
                elif mutation=='volume':d['Mounts']=[{'Type':'volume','Name':'active','Destination':'/var/lib/postgresql/data'}]
                elif mutation=='bind':d['Mounts']=[{'Type':'bind','RW':False,'Destination':'/var/run/docker.sock'}]
                elif mutation=='privileged':d['HostConfig']['Privileged']=True
                elif mutation=='ports':d['HostConfig']['PortBindings']={'5432/tcp':[{}]}
                else:d['HostConfig']['ReadonlyRootfs']=False
                with self.assertRaises(ValueError):v.guard_container(d,project)

    def test_unreviewed_jpa_and_flyway_config_refused(self):
        v.configuration_guard({'SPRING_JPA_HIBERNATE_DDL_AUTO':'validate'})
        for env in ({'SPRING_JPA_HIBERNATE_DDL_AUTO':'update'}, {'SPRING_FLYWAY_SCHEMAS':'other'},
                    {'SPRING_JPA_PROPERTIES_HIBERNATE_PHYSICAL_NAMING_STRATEGY':'other'},
                    {'SPRING_APPLICATION_JSON':'{}'}, {'JAVA_TOOL_OPTIONS':'-Doverride=true'},
                    {'SPRING_PROFILES_INCLUDE':'test'}, {'SPRING_CONFIG_ADDITIONAL_LOCATION':'/unreviewed'}):
            with self.assertRaises(ValueError):v.configuration_guard(env)

    def cycle(self, error=None, cleanup_error=False, mutate=False):
        root=Path(self.temp.name);project='wavy-pwa-restore-fixture';commands=[]
        def command(args, **kw):
            commands.append(args)
            if 'inspect' in args:return json.dumps([container_data(project)]).encode()
            if args[-3:]==['ps','-q','factures']:return b'fixture'
            if args[:3]==['docker','rm','-f'] and cleanup_error:raise ValueError('cleanup')
            return b''
        def launch(*args):
            if error:raise error
            return {'passed':True}
        report=root/'report.json'
        with (patch.object(v,'restricted_role',return_value=('role','not-a-secret')),
             patch.object(v,'prepare_image',return_value={}),patch.object(v,'launch',side_effect=launch),
             patch.object(v,'snapshot',side_effect=['before','changed' if mutate else 'before','before'])):
            try:result=v.validate_copies(['docker','compose'],project,root,report,{'run':'fixture'},command)
            finally:self.last_report=json.loads(report.read_text());self.commands=commands
        return result

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)

    def test_success_report_preserved_before_copy_cleanup(self):
        self.assertEqual(self.cycle()['status'],'passed')
        self.assertTrue(self.last_report['cleanup'])
        self.assertEqual(len(self.last_report['images']),2)

    def test_failure_and_interrupt_remove_children_and_preserve_failure_report(self):
        for error in (ValueError('schema mismatch'),InterruptedError('signal'),KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__):
                with self.assertRaises(type(error)):self.cycle(error)
                self.assertEqual(self.last_report['status'],'failed')
                self.assertTrue(self.last_report['cleanup'])
                self.assertTrue(any(a[:3]==['docker','rm','-f'] for a in self.commands))

    def test_cleanup_failure_records_remaining_container_and_no_pass(self):
        with self.assertRaises(ValueError):self.cycle(ValueError('validation'),True)
        self.assertFalse(self.last_report['cleanup'])
        self.assertTrue(self.last_report['containers'])
        self.assertEqual(self.last_report['status'],'cleanup-failed')

    def test_insufficient_budget_records_failure_before_any_docker_command(self):
        evidence=Path(self.temp.name)/'budget.json'
        with patch.object(v,'execute') as command:
            with self.assertRaises(ValueError):
                v.validate_copies([], 'wavy-pwa-restore-fixture',self.temp.name,evidence,{},command,timeout_seconds=0)
            command.assert_not_called()
        report=json.loads(evidence.read_text())
        self.assertEqual(report['failure']['stage'],'budget')
        self.assertEqual(report['status'],'failed')
        self.assertTrue(report['cleanup'])

    def test_previous_evidence_is_retained_byte_for_byte_on_failed_retry(self):
        path=Path(self.temp.name)/'report.json'
        previous=b'{"status":"passed","synthetic":true}\n'
        path.write_bytes(previous);path.chmod(0o600)
        expected=v.digest(path)
        with self.assertRaises(ValueError):self.cycle(ValueError('retry failed'))
        archive=path.parent/'schema-validation-history'/(expected+'.json')
        self.assertEqual(archive.read_bytes(),previous)
        self.assertEqual(v.digest(archive),expected)
        self.assertEqual(self.last_report['status'],'failed')

    def test_mutation_is_refused(self):
        with self.assertRaises(ValueError):self.cycle(mutate=True)
        self.assertEqual(self.last_report['status'],'failed')


@unittest.skipUnless(os.environ.get('WAVY_LOCAL_JPA_TESTS')=='1', 'Explicit isolated local Docker fixtures opt-in')
class RealPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if socket.gethostname().split('.')[0]=='wavy-preprod' or os.environ.get('DOCKER_HOST') or os.environ.get('DOCKER_CONTEXT'):
            raise RuntimeError('MSI local fixtures only')
        endpoint=v.execute(['docker','context','inspect','--format','{{.Endpoints.docker.Host}}']).strip()
        if endpoint!=b'unix:///var/run/docker.sock':raise RuntimeError('Local daemon required')
        cls.tmp=tempfile.TemporaryDirectory(prefix='wavy-jpa-tests-');cls.addClassCleanup(cls.tmp.cleanup)
        cls.root=Path(cls.tmp.name);cls.project='wavy-pwa-restore-local-'+secrets.token_hex(8)
        cls.pg=cls.project+'-pg';cls.password=secrets.token_hex(32)
        cls.addClassCleanup(lambda:v.execute(['docker','rm','-f',cls.pg]))
        v.execute(['docker','run','--pull','never','-d','--name',cls.pg,'--network','none','--read-only',
                   '--label','com.docker.compose.project='+cls.project,'--label','com.docker.compose.service=factures',
                   '--tmpfs','/var/lib/postgresql/data:rw,size=512m','--tmpfs','/var/run/postgresql','--tmpfs','/tmp',
                   '-e','POSTGRES_USER=restore_operator','-e','POSTGRES_DB=seed',
                   '-e','POSTGRES_PASSWORD='+cls.password,v.PG_IMAGE])
        for attempt in range(100):
            r=subprocess.run(['docker','exec',cls.pg,'pg_isready','-U','restore_operator','-d','seed'],capture_output=True)
            if r.returncode==0:break
            time.sleep(.1)
        else:raise RuntimeError('Local fixture did not start')
        cls.folders={}
        for key,pair in v.IMAGES.items():
            folder=cls.root/key;v.prepare_image(*pair,folder);cls.folders[key]=folder
        fixture=cls.folders['new']/'Fixture.java'
        fixture.write_text('''import org.flywaydb.core.Flyway; public class Fixture {
 public static void main(String[] a) throws Exception { String p=new java.io.BufferedReader(new java.io.InputStreamReader(System.in)).readLine();
 Flyway.configure().dataSource("jdbc:postgresql://127.0.0.1:5432/seed","restore_operator",p).locations("classpath:db/migration/common").load().migrate(); }}''')
        v.execute(['javac','--release','17','-cp',str(cls.folders['new']/'BOOT-INF/lib/*'),'-d',str(cls.folders['new']),str(fixture)])
        fixture_name=cls.project+'-seed';cls.addClassCleanup(lambda:subprocess.run(['docker','rm','-f',fixture_name],capture_output=True))
        v.execute(['docker','run','--pull','never','--rm','--name',fixture_name,'-i','--network','container:'+cls.pg,'--read-only',
                   '--tmpfs','/tmp','--mount','type=bind,source='+str(cls.folders['new'])+',target=/work,readonly',
                   '--entrypoint','java',v.IMAGES['new'][0],'-cp','/work:/work/BOOT-INF/classes:/work/BOOT-INF/lib/*','Fixture'],input=(cls.password+'\n').encode())

    def sql(self,sql,database='factures'):
        return v.admin_sql(self.pg,database,sql)

    def setUp(self):
        self.sql('CREATE DATABASE factures TEMPLATE seed;', 'seed')
        self.addCleanup(lambda:self.sql('DROP DATABASE IF EXISTS factures WITH (FORCE);','seed'))
        self.role,self.password=v.restricted_role(self.pg,'factures')

    def launch(self, version='new',password=None):
        name=self.project+'-v-'+secrets.token_hex(4)
        self.addCleanup(lambda:subprocess.run(['docker','rm','-f',name],capture_output=True))
        return v.launch(self.pg,self.project,v.IMAGES[version][0],self.folders[version],
                        'factures',self.role,password or self.password,name)

    def test_complete_control_cycle_keeps_evidence_and_removes_validator_containers(self):
        staging=self.root/('cycle-'+secrets.token_hex(4));staging.mkdir()
        evidence=staging/'evidence.json'
        def command(args,**kwargs):
            if args[:1]==['fixture-compose']:
                self.assertEqual(args[1:],['ps','-q','factures'])
                return self.pg.encode()
            return v.execute(args,**kwargs)
        report=v.validate_copies(['fixture-compose'],self.project,staging,evidence,
                                  {'run':'synthetic-local','planHash':'a'*64,'backup':{'manifestSha256':'b'*64}},command)
        self.assertEqual(report['status'],'passed')
        saved=json.loads(evidence.read_text())
        self.assertTrue(saved['cleanup'])
        self.assertEqual(saved['containers'],[])
        self.assertEqual(saved['beforeHash'],saved['afterHash'])
        self.assertFalse(v.execute(['docker','ps','-aq','--filter','label=wavy.validator.project='+self.project]).strip())

    def test_five_synthetic_database_dumps_restore_with_equal_contents(self):
        # One networkless fixture PG server, five independent DB pairs; not a real backup lot.
        for db in ('socle','tiers','contrats','factures','tresorerie'):
            source='fixture_'+db+'_source';copy_name='fixture_'+db+'_copy'
            self.sql('CREATE DATABASE '+source+';', 'seed')
            self.addCleanup(lambda name=source:self.sql('DROP DATABASE '+name+' WITH (FORCE);','seed'))
            self.sql('CREATE DATABASE '+copy_name+';', 'seed')
            self.addCleanup(lambda name=copy_name:self.sql('DROP DATABASE '+name+' WITH (FORCE);','seed'))
            self.sql("CREATE TABLE fixture_integrity(id integer PRIMARY KEY, tag text NOT NULL); INSERT INTO fixture_integrity VALUES (1,'"+db+"');",source)
            dump=v.execute(['docker','exec',self.pg,'pg_dump','-U','restore_operator','-d',source,'-Fc'])
            v.execute(['docker','exec','-i',self.pg,'pg_restore','-U','restore_operator','-d',copy_name,
                       '--no-owner','--no-acl','--single-transaction','--exit-on-error'],input=dump)
            self.assertEqual(v.snapshot(self.pg,source),v.snapshot(self.pg,copy_name))
            self.sql("UPDATE fixture_integrity SET tag='altered';",copy_name)
            self.assertNotEqual(v.snapshot(self.pg,source),v.snapshot(self.pg,copy_name))

    def test_positive_both_images_and_database_invariant(self):
        before=v.snapshot(self.pg,'factures')
        for version in ('old','new'):
            self.assertTrue(self.launch(version)['passed'])
            self.assertEqual(v.snapshot(self.pg,'factures'),before)

    def test_jpa_missing_column_refused(self):
        self.sql('ALTER TABLE note_frais DROP COLUMN libelle;')
        with self.assertRaises(v.ValidationRefused) as refused:self.launch()
        self.assertEqual(refused.exception.stage,'jpa')

    def test_flyway_checksum_refused(self):
        self.sql('UPDATE flyway_schema_history SET checksum=checksum+1 WHERE version=\'20\';')
        with self.assertRaises(v.ValidationRefused) as refused:self.launch()
        self.assertEqual(refused.exception.stage,'flyway')

    def test_flyway_pending_refused(self):
        self.sql('DELETE FROM flyway_schema_history WHERE version=\'20\';')
        with self.assertRaises(ValueError):self.launch()

    def test_flyway_future_history_refused(self):
        self.sql("INSERT INTO flyway_schema_history(installed_rank,version,description,type,script,checksum,installed_by,execution_time,success) VALUES (999,'999','synthetic','SQL','V999__synthetic.sql',0,'fixture',0,true);")
        with self.assertRaises(ValueError):self.launch()

    def test_real_validator_termination_preserves_failure_and_cleans_container(self):
        staging=self.root/('interrupt-'+secrets.token_hex(4));staging.mkdir()
        evidence=staging/'evidence.json';killers=[];terminated=[]
        def terminate(name):
            for attempt in range(100):
                check=subprocess.run(['docker','inspect','-f','{{.State.Running}}',name],capture_output=True)
                if check.returncode==0 and check.stdout.strip()==b'true':
                    terminated.append(v.execute(['docker','kill','--signal','TERM',name]));return
                time.sleep(.05)
        def command(args,**kwargs):
            if args[:1]==['fixture-compose']:return self.pg.encode()
            if args[:4]==['docker','start','-a','-i']:
                thread=threading.Thread(target=terminate,args=(args[4],));thread.start();killers.append(thread)
            return v.execute(args,**kwargs)
        try:
            with self.assertRaises(ValueError):
                v.validate_copies(['fixture-compose'],self.project,staging,evidence,
                                  {'run':'synthetic-interrupt','planHash':'a'*64,'backup':{}},command)
        finally:
            for thread in killers:thread.join(10)
        self.assertTrue(terminated)
        saved=json.loads(evidence.read_text())
        self.assertEqual(saved['status'],'failed')
        self.assertTrue(saved['cleanup'])
        self.assertFalse(saved['containers'])
        self.assertFalse(v.execute(['docker','ps','-aq','--filter','label=wavy.validator.project='+self.project]).strip())

    def test_flyway_missing_history_refused(self):
        self.sql('DROP TABLE flyway_schema_history;')
        with self.assertRaises(ValueError):self.launch()

    def test_incompatible_sql_type_refused(self):
        self.sql('ALTER TABLE note_frais ALTER COLUMN libelle TYPE bigint USING NULL;')
        with self.assertRaises(ValueError):self.launch()

    def test_elevated_role_and_wrong_password_refused(self):
        with self.assertRaises(ValueError):self.launch(password='0'*64)
        self.sql('ALTER ROLE '+self.role+' SUPERUSER;')
        with self.assertRaises(ValueError):self.launch()

    def test_other_database_refused_by_copy_hba(self):
        name=self.project+'-foreign-'+secrets.token_hex(4)
        self.addCleanup(lambda:subprocess.run(['docker','rm','-f',name],capture_output=True))
        with self.assertRaises(ValueError):
            v.launch(self.pg,self.project,v.IMAGES['new'][0],self.folders['new'],
                     'postgres',self.role,self.password,name)
        rows=self.sql("SELECT database::text,user_name::text,auth_method FROM pg_hba_file_rules WHERE type='host';")
        self.assertIn(('factures|'+self.role+'|scram-sha-256').encode(),rows.replace(b'{',b'').replace(b'}',b''))
        self.assertIn(b'reject',rows)

    def test_write_grant_refused(self):
        self.sql('GRANT INSERT ON note_frais TO '+self.role+';')
        with self.assertRaises(ValueError):self.launch()

    def test_validator_tcp_access_has_no_external_route(self):
        # Namespace has only loopback; command does not attempt any PREPROD address.
        self.assertEqual(v.execute(['docker','exec',self.pg,'cat','/proc/net/route']).splitlines()[1:],[])
        d=json.loads(v.execute(['docker','inspect',self.pg]))[0]
        v.guard_container(d,self.project)
        d['HostConfig']['NetworkMode']='wavy-preprod'
        with self.assertRaises(ValueError):v.guard_container(d,self.project)


if __name__=='__main__':unittest.main()
