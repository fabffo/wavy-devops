#!/usr/bin/env python3
"""Bounded MSI functional profile of local_auth, sharing lock/recovery and gate.
No remote operations, builds, migration writes or global database restores.
"""
import copy
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tarfile
import tempfile
import time


class Campaign:
 scope='HTTPS_FUNCTIONAL_61_SOCLE_18_TIERS_6_NOTES_9_FILES_4_AI'
 def __init__(self, auth):
  self.a=auth;self.gate=None;self.results=[]
  self.private=auth.REPO/'preparation/pwa-notes-frais/private-shell'
 def check(self,label,condition,**details):
  self.results.append({'control':label,'passed':bool(condition),**details})
  self.a.save(self.a.R/'functional-results.json',{'checks':self.results})
  if not condition:raise self.a.Refused('FUNCTIONAL_'+label)
 def snapshot_guard(self,obj,base,name):
  a=self.a
  if name!='wavy-contrats-api-recette':return a.snapshot_guard(obj,base)
  mounts=obj.get('Mounts',[]);volumes=base.get('volumes',[])
  if len(mounts)!=1 or len(volumes)!=1:raise a.Refused('CONTRATS_MOUNT_COUNT')
  mount=mounts[0];volume=volumes[0]
  if (mount.get('Type'),mount.get('Name'),mount.get('Destination'),mount.get('RW'))!=('volume','wavy-recette_contrats-pieces-jointes-recette','/app/data/contrats/pieces-jointes',True):raise a.Refused('CONTRATS_MOUNT_SCOPE')
  if volume.get('source')!='contrats-pieces-jointes-recette' or volume.get('target')!=mount['Destination'] or volume.get('read_only',False):raise a.Refused('CONTRATS_MOUNT_MANIFEST')
  stripped=copy.deepcopy(obj);stripped['Mounts']=[]
  config=copy.deepcopy(base);config['volumes']=[]
  a.snapshot_guard(stripped,config)
 def baseline(self,db,ids=()):
  a=self.a
  if not ids:return a.baseline(db)
  metadata=json.loads(a.sql(db,"SELECT json_object_agg(table_name,cols) FROM (SELECT table_name,json_agg(column_name) cols FROM information_schema.columns WHERE table_schema='public' GROUP BY table_name) t;"))
  answer={};csv=','.join(map(str,ids))
  for table,cols in metadata.items():
   if not re.fullmatch('[a-z_]+',table):raise a.Refused('TABLE_NAME')
   condition='true'
   if db=='socle' and table=='tenant':condition='t.id NOT IN ('+csv+')'
   elif 'tenant_id' in cols:condition='t.tenant_id NOT IN ('+csv+')'
   elif db=='tiers' and 'tiers_id' in cols:condition='t.tiers_id NOT IN (SELECT id FROM tiers WHERE tenant_id IN ('+csv+'))'
   elif db=='factures' and 'note_frais_id' in cols:condition='t.note_frais_id NOT IN (SELECT id FROM note_frais WHERE tenant_id IN ('+csv+'))'
   answer[table]=json.loads(a.sql(db,"SELECT json_build_object('count',count(*),'hash',md5(coalesce(string_agg(md5(row_to_json(t)::text),'' ORDER BY row_to_json(t)::text),''))) FROM public."+table+' t WHERE '+condition+';'))
  return answer
 def docs(self):
  a=self.a;s=a.state();folder=s.get('storageFolder');raw=a.run(['docker','cp','wavy-contrats-api-recette:/app/data/contrats/pieces-jointes/.','-'])
  rows=[];owned=[]
  with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
   for item in archive:
    if folder and folder in Path(item.name).parts:
     if item.isfile():owned.append({'path':item.name,'sha256':hashlib.sha256(archive.extractfile(item).read()).hexdigest()})
     if item.issym() or item.islnk():raise a.Refused('FIXTURE_DOCUMENT_SYMLINK')
     continue
    if item.isfile():rows.append((item.name,item.size,item.mode,item.uid,item.gid,hashlib.sha256(archive.extractfile(item).read()).hexdigest()))
    elif item.issym() or item.islnk():rows.append((item.name,'link',item.linkname))
  return {'originalFiles':len(rows),'originalSha256':a.canonical(sorted(rows)),'owned':owned}
 def helper(self,script,readonly=False):
  a=self.a;ref=a.m.plan('recettelocal')['images']['factures-api']
  a.run(['docker','volume','inspect','wavy-recette_contrats-pieces-jointes-recette'])
  mount='type=volume,source=wavy-recette_contrats-pieces-jointes-recette,target=/storage,volume-nocopy'+(',readonly' if readonly else '')
  return a.run(['docker','run','--rm','--pull','never','--network','none','--user','0:0','--mount',mount,'--entrypoint','/bin/sh',ref,'-ec',script])
 def close_gate(self):
  a=self.a;s=a.state();pid=s.get('gatePid')
  if s.get('gateSocketDir',str(a.R/'gate')) not in (str(a.R/'gate'),str(a.R/'runtime/gate')):raise a.Refused('GATE_DIRECTORY_SCOPE')
  if pid and Path('/proc/'+str(pid)).exists() and Path('/proc/'+str(pid)+'/stat').read_text().split()[2]!='Z':
   cmd=Path('/proc/'+str(pid)+'/cmdline').read_bytes()
   if str(self.private/'session-gate.py').encode() not in cmd or str(Path(s.get('gateSocketDir',str(a.R/'gate')))).encode() not in cmd:raise a.Refused('GATE_PROCESS_OWNERSHIP')
   os.kill(pid,signal.SIGTERM)
   if self.gate:self.gate.wait(timeout=10)
   else:
    for _ in range(50):
     if not Path('/proc/'+str(pid)).exists() or Path('/proc/'+str(pid)+'/stat').read_text().split()[2]=='Z':break
     time.sleep(.1)
    else:raise a.Refused('GATE_STOP_FAILED')
  socket=Path(s.get('gateSocketDir',str(a.R/'gate')))/'gate.sock'
  if socket.exists():
   if not socket.is_socket():raise a.Refused('GATE_SOCKET_OWNERSHIP')
   socket.unlink()
  if s:s.pop('gatePid',None);a.persist(s)
  self.gate=None
 def open_gate(self,session,seconds=900):
  a=self.a;self.close_gate();s=a.state();s.setdefault('counts',{}).setdefault('gateOpenings',0)
  if s['counts']['gateOpenings']>=6:raise a.Refused('GATE_OPENING_BUDGET')
  s['counts']['gateOpenings']+=1;a.persist(s)
  read,write=os.pipe()
  try:
   proc=subprocess.Popen([sys.executable,'-B',str(self.private/'session-gate.py'),'--socket-dir',str(a.R/'gate'),'--session-fd',str(read),'--parent-pid',str(os.getpid()),'--seconds',str(seconds)],pass_fds=(read,),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   self.gate=proc;os.close(read);read=None
   s=a.state();s['gatePid']=proc.pid;a.persist(s);os.write(write,session['cookie'].encode())
  finally:
   if read is not None:os.close(read)
   os.close(write)
  for _ in range(50):
   if (a.R/'gate/gate.sock').is_socket():return
   if proc.poll() is not None:raise a.Refused('GATE_START_FAILED')
   time.sleep(.1)
  raise a.Refused('GATE_SOCKET_TIMEOUT')
 def prepare(self):
  a=self.a;a.prepare_runtime();s=a.state();out=a.R/'runtime'
  gate=a.R/'gate';gate.mkdir(mode=0o755);gate.chmod(0o755)
  # Reuse private routes and gate. Canonical HTTPS replaces every internal scheme.
  routes=(self.private/'routes.conf').read_text().replace('wavy-pwa-preprod','wavy-pwa-recette')
  canonical='proxy_set_header Host recettelocal.wavyservices.fr; proxy_set_header X-Forwarded-Host recettelocal.wavyservices.fr; proxy_set_header X-Forwarded-Proto https; proxy_set_header X-Forwarded-Port 443; proxy_set_header X-Forwarded-For $http_x_forwarded_for; proxy_set_header Forwarded "";'
  routes=re.sub(r'proxy_set_header Host \$host;\s*proxy_set_header X-Forwarded-Proto \$scheme;\s*proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;',canonical,routes)
  for loc in ('location = /api/notes-frais {','location ^~ /api/notes-frais/ {','location = /api/pwa {','location ^~ /api/pwa/ {'):
   routes=routes.replace(loc,loc+'\n  if ($wavy_origin_denied) { return 403; }')
  routes+='''
location = /api/factures/achats/extraction-ia {
 if ($wavy_origin_denied) { return 403; }
 auth_request /__private_pwa_session;
 error_page 401 403 500 502 503 504 = /__private_notes_closed;
 client_max_body_size 11m;
 proxy_read_timeout 75s;
 proxy_pass $private_api_origin;
 '''+canonical+'''
}
location = /api/factures/achats/ia/creer { return 403; }
location = /api/notes-frais/transformer-facture-achat { return 403; }
location ~ ^/api/notes-frais/[0-9]+/transformer-factures-achats$ { return 403; }
'''
  (out/'routes.conf').write_text(routes)
  shell=(out/'shell.conf.template').read_text().replace('include /etc/nginx/wavy-https/closed.conf;','include /etc/nginx/wavy-https/routes.conf;')
  (out/'shell.conf.template').write_text(shell)
  overlay={'services':{}}
  # Protect optional APIs too: a later module selection reuses this runtime.
  for c in ('socle','tiers','contrats','factures','tresorerie'):
   overlay['services']['wavy-'+c+'-api-recette']={'environment':{'SPRING_JPA_HIBERNATE_DDL_AUTO':'validate','SPRING_SQL_INIT_MODE':'never'}}
  overlay['services']['wavy-factures-api-recette']['environment'].update(WAVY_FACTURES_STOCKAGE_JUSTIFICATIFS='/app/justificatifs',WAVY_AI_ACHAT_AUTO_CREATION_ENABLED='false',WAVY_AI_TIMEOUT_SECONDS='60')
  overlay['services']['wavy-factures-api-recette']['volumes']=[{'type':'volume','source':'contrats-pieces-jointes-recette','target':'/app/justificatifs','volume':{'subpath':s['storageFolder'],'nocopy':True}}]
  overlay['services']['wavy-erp-shell-recette']={'volumes':[{'type':'bind','source':str(gate),'target':'/run/wavy-private-pwa-gate','read_only':True,'bind':{'create_host_path':False}}]}
  a.save(out/'functional.overlay.json',overlay)
  merged=json.loads(a.run(a.compose(out/'compose.https.yml')+['-f',str(out/'functional.overlay.json'),'config','--format','json']))
  # Complete candidate, including inherited environment: keep secrets private.
  a.save(a.R/'candidate-runtime.private.json',merged)
  s=a.state();s.update(storageAttempted=True);a.persist(s)
  folder=s['storageFolder']
  if not re.fullmatch('notes-frais-functional-[a-f0-9]{12}',folder):raise a.Refused('STORAGE_FOLDER')
  self.helper('test ! -e /storage/'+folder+'; test ! -L /storage/'+folder+'; mkdir /storage/'+folder+'; chown 100:101 /storage/'+folder+'; chmod 0700 /storage/'+folder)
  s=a.state();s['storageCreated']=True;a.persist(s)
  self.check('storage-owner-mode',self.helper('stat -c "%u:%g:%a" /storage/'+folder,True).decode().strip()=='100:101:700')
  for name in a.SERVICES:
   conf=merged['services'][name]
   self.check('candidate-image-'+name,conf['image']==a.m.plan('recettelocal')['images'][name.removeprefix('wavy-').removesuffix('-recette')])
   self.check('candidate-unpublished-'+name,name=='wavy-erp-shell-recette' or not conf.get('ports'))
  env=merged['services']['wavy-factures-api-recette']['environment']
  self.check('AI-autocreation-disabled',str(env['WAVY_AI_ACHAT_AUTO_CREATION_ENABLED']).lower()=='false' and not env.get('SPRING_APPLICATION_JSON') and not merged['services']['wavy-factures-api-recette'].get('command'))
 def command(self):
  return ['docker','compose','-p','wavy-recette','-f',str(self.a.R/'candidate-runtime.private.json')]
 def start(self):
  a=self.a;s=a.state();s.update(servicesAttempted=True,phase='starting');a.persist(s)
  a.run(self.command()+['up','-d','--no-deps','--no-build','--pull','never','--force-recreate',*a.SERVICES],timeout=180)
  for name in a.SERVICES:
   # PWA image has no HEALTHCHECK: prove its HTTP listener inside the container.
   for _ in range(90):
    obj=a.inspect(name);health=obj['State'].get('Health',{}).get('Status')
    if health=='healthy':break
    if health is None and obj['State']['Running']:
     try:a.run(['docker','exec',name,'wget','-q','-O','/dev/null','http://127.0.0.1/']);break
     except a.Refused:pass
    if health=='unhealthy' or not obj['State']['Running']:raise a.Refused('SERVICE_HEALTH_'+name)
    time.sleep(1)
   else:raise a.Refused('HEALTH_TIMEOUT_'+name)
   ref=a.m.plan('recettelocal')['images'][name.removeprefix('wavy-').removesuffix('-recette')]
   if obj['Image']!=json.loads(a.run(['docker','image','inspect',ref]))[0]['Id']:raise a.Refused('RUNTIME_IMAGE_MISMATCH')
  s=a.state();s.update(phase='services-ready',servicesReady=True);a.persist(s);a.emit('services',healthy=len(a.SERVICES),buildOrPull=False)
 def provision(self):
  a=self.a;a.provision();s=a.state();user=s['users']['A-owner']
  # One extra association, never alter the role catalogue or original users.
  result=a.sql('socle',"INSERT INTO utilisateur_role(tenant_id,utilisateur_id,role_id,date_creation,date_modification) SELECT "+str(user['tenant'])+','+str(user['id'])+",id,now(),now() FROM role WHERE code='ADMIN_TENANT' RETURNING id;",True)
  if not result.isdigit():raise a.Refused('ADMIN_TENANT_ROLE')
  s=a.state();s['adminAssociationId']=int(result);a.persist(s)
 def execute(self):
  a=self.a
  pre=json.loads((a.R/'preflight-result.json').read_text())
  self.check('five-API-readonly-compatibility',pre['passed'] and pre['originalRowsMatch'])
  self.check('preflight-baseline-still-current',json.loads((a.R/'original-baseline.json').read_text())==a.state()['baseline'])
  for db in ('socle','tiers','factures'):a.backup(db)
  s=a.state();s['storageFolder']='notes-frais-functional-'+a.AUTH_MARKER;a.persist(s)
  documents=self.docs();a.save(a.R/'documents-before.json',documents)
  self.prepare();self.start();self.provision();a.activate_caddy()
  self.client=a.Client()
  self.check('PWA-closed-before-opening',self.client.request('GET','/pwa/')['status']==404)
  self.carriers()
  self.chrome()
  self.notes_and_ai()
  s=a.state();s.update(httpPassed=all(x['passed'] for x in self.results),httpChecks=len(self.results),phase='tested');a.persist(s)
 def carriers(self):
  a=self.a;c=self.client
  for alias,company in [('A-owner','A1'),('A-owner','A2'),('A-peer','A1'),('B-owner','B1'),('B-owner','B2'),('B-peer','B1')]:
   s=a.state();key=alias+'__'+company
   session=c.login(alias)
   if session['companyId']!=s['companies'][company]:c.switch(session,company,True)
   result=c.request('POST','/api/tiers',session,data={'typeTiers':'PERSONNE_PHYSIQUE','naturePersonne':'SALARIE_INTERNE','roles':['SALARIE','PORTEUR_CARTE'],'nom':'TEST SYNTHETIQUE','prenom':'QA PORTEUR '+company,'actif':True,'pieceRapprochementAutorisee':False})
   self.check('carrier-real-api',result['status'] in (200,201),status=result['status'])
   data=result['json'];s=a.state();record={'id':data['id'],'tenant':s['users'][alias]['tenant'],'company':company,'companyId':s['companies'][company],'alias':alias}
   s.setdefault('carriers',{})[key]=record;a.persist(s)
   self.check('carrier-context',data['tenantId']==record['tenant'] and data['societeInterneId']==record['companyId'])
   link=a.sql('socle','INSERT INTO utilisateur_tiers(tenant_id,utilisateur_id,tiers_id,societe_interne_id,type_liaison,principal,actif,statut_association,date_creation,date_modification) VALUES('+','.join([str(record['tenant']),str(s['users'][alias]['id']),str(data['id']),str(record['companyId']),a.q('PORTEUR_CARTE'),a.q(company==s['users'][alias]['companies'][0]),'true',a.q('ACTIVE'),'now()','now()'])+') RETURNING id;',True)
   s=a.state();s['carriers'][key]['associationId']=int(link);a.persist(s)
   c.request('DELETE','/api/auth/session',session)
  a.emit('carriers',created=6,roles=12,socleAssociations=6)
 def chrome(self):
  a=self.a;s=a.state();u=s['users']['A-owner'];output=a.R/'browser';output.mkdir(mode=0o700)
  a.save(output/'input.private.json',{'email':u['email'],'password':u['password'],'companyIds':[s['companies']['A1'],s['companies']['A2']]})
  try:self.windows_node(a.PTH/'chrome-navigation.cjs',[output/'input.private.json',output],timeout=180)
  finally:
   if (output/'chrome-navigation-results.json').exists():
    result=json.loads((output/'chrome-navigation-results.json').read_text());s=a.state();s['counts']['requests']+=result['requestCount'];s['counts']['logins']+=result['loginCount'];a.persist(s)
  result=json.loads((output/'chrome-navigation-results.json').read_text())
  self.check('Chrome-five-modules-company-logout',result['passed'],browser=result['browser'],assertions=len(result['checks']))
 def windows_node(self,script,paths,timeout=180,options=()):
  a=self.a
  def win(p):return a.run(['wslpath','-w',str(p)]).decode().strip()
  env=os.environ.copy();env['WSLENV']='WAVY_PLAYWRIGHT_CORE';env['WAVY_PLAYWRIGHT_CORE']=win(a.REPO.parent/'wavy-erp-shell/node_modules/playwright-core')
  proc=subprocess.run(['/mnt/c/Users/FabriceFOUGERY/AppData/Local/hermes/node/node.exe',win(script),*[win(x) for x in paths],*options],env=env,capture_output=True,timeout=timeout)
  (a.R/'browser-execution.private.log').write_bytes(proc.stdout+proc.stderr);(a.R/'browser-execution.private.log').chmod(0o600)
  if proc.returncode:raise a.Refused('CHROME_EXECUTION_FAILED')
 def notes_and_ai(self):
  a=self.a;c=self.client;plan=json.loads((a.PTH/'PLAN-FONCTIONNEL-LOCAL.json').read_text());files=plan['fixtures']['fixtures'];root=Path(plan['fixturesDirectory'])
  for f in files:self.check('fixture-integrity-'+f['file'],a.m.digest(root/f['file'])==f['sha256'])
  outsider=c.login('B-peer')
  keys=list(a.state()['carriers'])
  for index,key in enumerate(keys):
   carrier=a.state()['carriers'][key];session=c.login(carrier['alias'])
   if session['companyId']!=carrier['companyId']:c.switch(session,carrier['company'],True)
   seconds=30 if index==5 else 900;opened=time.monotonic();self.open_gate(session,seconds)
   self.check('PWA-open-only-approved-session',c.request('GET','/pwa/',session)['status']==200 and c.request('GET','/pwa/',outsider)['status']==404)
   self.check('notes-writes-other-session-refused',c.request('POST','/api/notes-frais',outsider,data={})['status']==403)
   f=files[index%3];file=root/f['file'];expected=f['expected'];label='QA FUNCTIONAL '+a.AUTH_MARKER+' '+str(index)
   data={'salarieTiersId':carrier['id'],'categorieAchat':'FRAIS_GENERAUX','dateDepense':'2026-10-25','numeroPiece':label,'libelle':label,'devise':'EUR','montantHt':float(expected['ht']),'montantTva':float(expected['tva']),'montantTtc':float(expected['ttc']),'tauxTva':20,'modePaiement':'CARTE_ENTREPRISE','origineNoteFrais':'SCAN_PWA','marchandNomExtrait':'TEST SYNTHETIQUE','lignes':[]}
   if index==2:
    output=a.R/'browser-notes';output.mkdir(mode=0o700)
    winfile=a.run(['wslpath','-w',str(file)]).decode().strip()
    a.save(output/'input.private.json',{'cookie':session['cookie'],'file':winfile,'label':label,'tenant':carrier['tenant'],'company':carrier['companyId']})
    try:self.windows_node(a.PTH/'chrome-notes.cjs',[output/'input.private.json',output],timeout=150)
    finally:
     self.import_browser_notes()
    report=json.loads((output/'chrome-notes-results.json').read_text());self.check('Chrome-PWA-create-detail-modify',report['passed'],assertions=len(report['checks']));note_id=report['noteIds'][0]
   else:
    response=self.multipart('POST','/api/notes-frais',session,file,f['mime'],data)
    self.check('note-create-'+f['mime'],response['status']==200,status=response['status'])
    note_id=response['json']['id'];s=a.state();s.setdefault('noteIds',[]).append(note_id);a.persist(s)
   self.check('note-own-identity',c.request('GET','/api/notes-frais/'+str(note_id),session)['status']==200)
   self.check('notes-list-and-summary',c.request('GET','/api/notes-frais',session)['status']==200 and c.request('GET','/api/notes-frais/synthese-mensuelle?annee=2026',session)['status']==200)
   if index in (0,3):
    data['libelle']+=' MODIFIEE'
    changed=self.multipart('PUT','/api/notes-frais/'+str(note_id),session,file,f['mime'],data)
    self.check('note-modified-with-attachment',changed['status']==200 and changed['json']['libelle']==data['libelle'])
   content=c.request('GET','/api/notes-frais/'+str(note_id)+'/justificatif/contenu',session)
   self.check('attachment-byte-integrity-'+f['mime'],content['status']==200 and content['bodyHash']==f['sha256'])
   self.check('attachment-response-security',content['headers'].get('x-content-type-options')==['nosniff'] and 'no-store' in ','.join(content['headers'].get('cache-control',[])))
   if index<3:
    self.restart_factures()
    again=c.request('GET','/api/notes-frais/'+str(note_id)+'/justificatif/contenu',session)
    self.check('attachment-persistence-after-restart-'+f['mime'],again['status']==200 and again['bodyHash']==f['sha256'])
   if index==0:
    for kind,blob,mime in [('mime',file,'application/pdf'),('corrupt',a.R/'corrupt.jpg','image/jpeg'),('oversize',a.R/'oversize.jpg','image/jpeg')]:
     if kind=='corrupt':blob.write_bytes(b'not an image')
     if kind=='oversize':
      with blob.open('wb') as stream:stream.truncate(10485761)
     before=self.docs()['owned'];bad=self.multipart('POST','/api/notes-frais/'+str(note_id)+'/justificatif',session,blob,mime,count_file=False)
     self.check('reject-'+kind+'-without-file',bad['status'] in (400,413,415,422) and before==self.docs()['owned'],status=bad['status'])
    self.ai(session,files,root)
   deletion=c.request('DELETE','/api/notes-frais/'+str(note_id),session)
   self.check('note-delete-real-api',deletion['status']==204)
   self.check('deleted-note-not-readable',c.request('GET','/api/notes-frais/'+str(note_id),session)['status'] in (403,404))
   if index==5:
    remaining=seconds-(time.monotonic()-opened)
    if remaining>0:time.sleep(min(remaining+.2,30))
    self.check('PWA-gate-natural-expiry',c.request('GET','/pwa/',session)['status']==404)
    self.check('notes-write-gate-natural-expiry',c.request('POST','/api/notes-frais',session,data={})['status']==403)
   self.close_gate();c.request('DELETE','/api/auth/session',session)
  c.request('DELETE','/api/auth/session',outsider)
  self.check('final-original-data-and-no-invoices',all(self.baseline(db,list(a.state()['tenants'].values()))==a.state()['baseline'][db] for db in a.DATABASES))
  a.emit('functional',checks=len(self.results),notesCreated=len(a.state().get('noteIds',[])),counts=a.state()['counts'])
 def restart_factures(self,overlay=None):
  a=self.a
  if overlay:
   a.run(self.command()+['-f',str(overlay),'up','-d','--no-deps','--no-build','--pull','never','--force-recreate','wavy-factures-api-recette'],timeout=120)
  else:a.run(['docker','restart','wavy-factures-api-recette'],timeout=90)
  for _ in range(90):
   obj=a.inspect('wavy-factures-api-recette')
   if obj['State'].get('Health',{}).get('Status')=='healthy':return
   if not obj['State']['Running']:raise a.Refused('FACTURES_RESTART_FAILED')
   time.sleep(1)
  raise a.Refused('FACTURES_RESTART_TIMEOUT')
 def import_browser_notes(self):
  a=self.a;path=a.R/'browser-notes/chrome-notes-results.json'
  if not path.exists():return
  report=json.loads(path.read_text());s=a.state()
  for note_id in report['noteIds']:
   if note_id not in s.setdefault('noteIds',[]):s['noteIds'].append(note_id)
  previous=s.get('browserNotesRequests',0);s['counts']['requests']+=report['requests']-previous;s['browserNotesRequests']=report['requests']
  previous=s.get('browserFileVersions',0);s['counts']['files']=s['counts'].get('files',0)+report['fileVersions']-previous;s['browserFileVersions']=report['fileVersions'];a.persist(s)
 def multipart(self,method,path,session,file,mime,data=None,count_file=True):
  a=self.a;s=a.state();s['counts']['requests']+=1
  if s['counts']['requests']>500:raise a.Refused('REQUEST_BUDGET')
  ai=path=='/api/factures/achats/extraction-ia'
  if ai:
   s['counts']['aiAttempts']=s['counts'].get('aiAttempts',0)+1
   if s['counts']['aiAttempts']>4:raise a.Refused('AI_CALL_BUDGET')
  elif count_file:
   s['counts']['files']=s['counts'].get('files',0)+1
   if s['counts']['files']>9:raise a.Refused('FILE_VERSION_BUDGET')
  a.persist(s)
  def opt(k,v):return k+' = '+json.dumps(v)+'\n'
  def win(p):return a.run(['wslpath','-w',str(p)]).decode().strip()
  config=opt('url',a.ORIGIN+path)+opt('resolve','recettelocal.wavyservices.fr:443:127.0.0.1')+opt('request',method)+opt('dump-header','-')+opt('output','-')
  for h in ('Origin: '+a.ORIGIN,'Cookie: '+session['cookie']):config+=opt('header',h)
  config+=opt('form','fichier=@'+win(file)+';type='+mime)
  if data is not None:
   part=a.R/'multipart.private.json';a.save(part,data);config+=opt('form','demande=@'+win(part)+';type=application/json')
  if ai:config+=opt('form','categorieAchat=FRAIS_GENERAUX')
  raw=a.run(['curl.exe','--silent','--show-error','--ssl-revoke-best-effort','--max-time','80' if ai else '20','--config','-'],input=config.encode(),timeout=85 if ai else 25)
  while True:
   block,sep,body=raw.partition(b'\r\n\r\n')
   if not sep:raise a.Refused('MULTIPART_RESPONSE')
   status=int(block.splitlines()[0].split()[1])
   if status>=200:break
   raw=body
  try:payload=json.loads(body)
  except (ValueError,UnicodeError):payload=None
  return {'status':status,'json':payload}
 def observe(self,label,condition,**details):
  self.results.append({'control':label,'passed':bool(condition),**details});self.a.save(self.a.R/'functional-results.json',{'checks':self.results})
 def ai(self,session,files,root):
  a=self.a;ids=list(a.state()['tenants'].values());csv=','.join(map(str,ids))
  before={table:a.sql('factures','SELECT count(*) FROM '+table+';') for table in ('facture_achat','note_frais_facture_achat')}
  for file in files:
   response=self.multipart('POST','/api/factures/achats/extraction-ia',session,root/file['file'],file['mime'],count_file=False)
   body=response['json'] or {};data=body.get('donnees') or {};expected=file['expected']
   self.check('AI-no-invoice-created',before=={table:a.sql('factures','SELECT count(*) FROM '+table+';') for table in before} and not body.get('factureCreee',False))
   amounts=all(abs(float(data.get(k,-999))-float(expected[e]))<.02 for k,e in [('montantHt','ht'),('montantTva','tva'),('montantTtc','ttc')])
   self.observe('AI-real-extraction-'+file['mime'],response['status']==200 and amounts,status=response['status'],expectedTTC=expected['ttc'],observedTTC=data.get('montantTtc'),errorCodes=[v.get('code') for v in body.get('erreurs',[])])
  # A genuine backend misconfiguration response, with no provider traffic or retry.
  missing=a.R/'AI-disabled.private.json';a.save(missing,{'services':{'wavy-factures-api-recette':{'environment':{'WAVY_AI_API_KEY':''}}}})
  self.restart_factures(missing)
  # Reserve no fourth billable call: the unconfigured backend must fail locally.
  response=self.multipart('POST','/api/factures/achats/extraction-ia',session,root/files[0]['file'],files[0]['mime'],count_file=False)
  body=response['json'] or {};self.observe('AI-unconfigured-error',not body.get('donnees') and bool(body.get('erreurs') or body.get('erreursBloquantes')),status=response['status'])
  a.run(self.command()+['up','-d','--no-deps','--no-build','--pull','never','--force-recreate','wavy-factures-api-recette'],timeout=120)
  self.restart_factures()
 def cleanup_data(self):
  a=self.a;s=a.state()
  if s.get('dataCleaned'):return
  self.import_browser_notes();s=a.state()
  if any(a.inspect(n)['State']['Running'] for n in a.SERVICES):raise a.Refused('WRITER_STILL_RUNNING')
  codes=[s.get('prefix','')+'_'+x for x in ('A','B')]
  ids=json.loads(a.sql('socle',"SELECT coalesce(json_agg(id),'[]'::json) FROM tenant WHERE code IN ("+','.join(map(a.q,codes))+');')) if s.get('prefix') else []
  if ids and len(ids)!=2:raise a.Refused('TENANT_OWNERSHIP')
  before={db:self.baseline(db,ids) for db in a.DATABASES}
  a.save(a.R/'before-cleanup-data-proof.json',{'matches':before==s['baseline'],'fingerprints':before})
  if before!=s['baseline']:raise a.Refused('ORIGINAL_DATA_DRIFT_BEFORE_CLEANUP')
  if ids:
   csv=','.join(map(str,ids));users=json.loads(a.sql('socle',"SELECT coalesce(json_agg(email),'[]'::json) FROM utilisateur WHERE tenant_id IN ("+csv+');'))
   if sorted(users)!=sorted(u['email'] for u in s['users'].values()):raise a.Refused('FIXTURE_USER_OWNERSHIP')
   invoices=int(a.sql('factures','SELECT count(*) FROM facture_achat WHERE tenant_id IN ('+csv+');'))
   if invoices:raise a.Refused('UNAUTHORIZED_INVOICE_PRESERVE_EVIDENCE')
   note_ids=json.loads(a.sql('factures',"SELECT coalesce(json_agg(id),'[]'::json) FROM note_frais WHERE tenant_id IN ("+csv+');'))
   if not set(note_ids).issubset(set(s.get('noteIds',[]))):raise a.Refused('UNOWNED_NOTE')
   if note_ids:
    owned=','.join(map(str,note_ids));self.sql_write('factures','DELETE FROM ligne_note_frais WHERE note_frais_id IN ('+owned+');DELETE FROM note_frais WHERE tenant_id IN ('+csv+') AND id IN ('+owned+');')
   carriers=json.loads(a.sql('tiers',"SELECT coalesce(json_agg(id),'[]'::json) FROM tiers WHERE tenant_id IN ("+csv+');'))
   if not set(carriers).issubset({v['id'] for v in s.get('carriers',{}).values()}):raise a.Refused('UNOWNED_CARRIER')
   if carriers:
    owned=','.join(map(str,carriers));self.sql_write('tiers','DELETE FROM tiers_roles WHERE tiers_id IN ('+owned+');DELETE FROM tiers WHERE tenant_id IN ('+csv+') AND id IN ('+owned+');')
   a.sql('socle',''.join('DELETE FROM '+table+' WHERE tenant_id IN ('+csv+');' for table in ('utilisateur_tiers','utilisateur_role','utilisateur_societe','compteur','utilisateur','societe_interne'))+'DELETE FROM tenant WHERE id IN ('+csv+');',True)
  if s.get('storageCreated') and not s.get('storageCleaned'):
   before_doc=json.loads((a.R/'documents-before.json').read_text());current=self.docs()
   if (before_doc['originalFiles'],before_doc['originalSha256'])!=(current['originalFiles'],current['originalSha256']):raise a.Refused('ORIGINAL_DOCUMENT_DRIFT')
   if len(current['owned'])>9:raise a.Refused('FILE_BUDGET_EXCEEDED')
   folder=s['storageFolder']
   if not re.fullmatch('notes-frais-functional-[a-f0-9]{12}',folder):raise a.Refused('STORAGE_SCOPE')
   self.helper('test -d /storage/'+folder+'; test ! -L /storage/'+folder+'; test -z "$(find /storage/'+folder+' -type l -print)"; find /storage/'+folder+' -mindepth 1 -depth -delete')
   after_doc=self.docs();a.save(a.R/'documents-after-cleanup.json',after_doc)
   if after_doc['owned'] or (before_doc['originalFiles'],before_doc['originalSha256'])!=(after_doc['originalFiles'],after_doc['originalSha256']):raise a.Refused('DOCUMENT_CLEANUP_FAILED')
   s=a.state();s['storageCleaned']=True;a.persist(s)
  after={db:self.baseline(db) for db in a.DATABASES}
  a.save(a.R/'after-cleanup-data-proof.json',{'matches':after==s['baseline'],'fingerprints':after})
  if after!=s['baseline']:raise a.Refused('ORIGINAL_DATA_DRIFT_AFTER_CLEANUP')
  s=a.state();s.update(dataCleaned=True,originalRowsMatch=True,cleanedRows=61 if s.get('carriers') and len(s['carriers'])==6 else (55 if s.get('adminAssociationId') else (54 if ids else 0)),checkedTables=sum(len(v) for v in after.values()));a.persist(s)
  a.emit('cleanup',originalRowsMatch=True,tables=s['checkedTables'],storageCleaned=s.get('storageCleaned',False))
 def sql_write(self,db,text):
  a=self.a
  if db not in ('tiers','factures') or any(a.inspect(n)['State']['Running'] for n in a.SERVICES):raise a.Refused('CLEANUP_SQL_SCOPE')
  return a.run(['docker','exec','-i',db+'-db-recette','sh','-c','exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'],input=('BEGIN;SET LOCAL statement_timeout=30000;'+text+'COMMIT;').encode()).decode().strip()


class AnonymousCampaign(Campaign):
 """Three-service, anonymous GET diagnostic. No fixture or business mutation code."""
 scope='HTTPS_ANONYMOUS_3_SERVICES_NO_FIXTURES'
 authorization_document='DIAGNOSTIC-CHROME-PERIMETRE.txt'
 components=('socle-api','gateway','erp-shell')
 def execute(self):
  a=self.a
  def deadline(signum,frame):raise a.Refused('ANONYMOUS_DIAGNOSTIC_DEADLINE')
  previous=signal.signal(signal.SIGALRM,deadline);signal.alarm(180)
  try:
   # Reuse the proven baseline and Socle artifact; never bootstrap business data.
   prior=json.loads((a.REPO/'preparation/https-msi/RESULTATS-FONCTIONNELS-LOCAUX.json').read_text())
   baseline=json.loads((Path(prior['runDirectory'])/'original-baseline.json').read_text())
   self.check('original-baseline-still-current',baseline==a.state()['baseline'])
   a.migration_check();a.backup();a.prepare_runtime()
   out=a.R/'runtime'
   extra={'services':{'wavy-erp-shell-recette':{'environment':{key+'_FRONT_UPSTREAM':'http://127.0.0.1:9/' for key in ('SOCLE','TIERS','CONTRATS','FACTURES','TRESORERIE')}},'wavy-socle-api-recette':{'environment':{'SPRING_JPA_HIBERNATE_DDL_AUTO':'validate','SPRING_SQL_INIT_MODE':'never','WAVY_BOOTSTRAP_ENABLED':'false'}}}}
   a.save(out/'anonymous.overlay.json',extra)
   merged=json.loads(a.run(a.compose(out/'compose.https.yml')+['-f',str(out/'anonymous.overlay.json'),'config','--format','json']))
   a.save(a.R/'candidate-runtime.private.json',merged)
   for name in a.SERVICES:
    conf=merged['services'][name]
    self.check('pinned-image-'+name,conf['image']==a.m.plan('recettelocal')['images'][name.removeprefix('wavy-').removesuffix('-recette')])
   self.start();a.activate_caddy()
   def session_headers():
    cmd=['curl.exe','--silent','--show-error','--ssl-revoke-best-effort','--max-time','8','--http1.1','--resolve','recettelocal.wavyservices.fr:443:127.0.0.1','--dump-header','-','--output','NUL',a.ORIGIN+'/api/auth/session']
    response=subprocess.run(cmd,capture_output=True,timeout=12)
    lines=response.stdout.decode(errors='replace').splitlines()
    status=next((int(x.split()[1]) for x in reversed(lines) if x.startswith('HTTP/')),None)
    challenge=any(x.lower().startswith('www-authenticate: basic') for x in lines)
    return {'status':status,'httpBasicChallenge':challenge,'curlExit':response.returncode,'method':'GET','credentialsSent':False}
   headers=session_headers();a.save(a.R/'session-headers.json',headers);a.emit('anonymous-session-headers',**headers)
   self.check('session-401-preserved-without-Basic-challenge',headers['status']==401 and not headers['httpBasicChallenge'],observed=headers)
   output=a.R/'browser';output.mkdir(mode=0o700)
   # windows_node accepts file paths only. The option is deliberately not converted.
   env=os.environ.copy();env['WSLENV']='WAVY_PLAYWRIGHT_CORE'
   win=lambda p:a.run(['wslpath','-w',str(p)]).decode().strip()
   env['WAVY_PLAYWRIGHT_CORE']=win(a.REPO.parent/'wavy-erp-shell/node_modules/playwright-core')
   proc=subprocess.run(['/mnt/c/Users/FabriceFOUGERY/AppData/Local/hermes/node/node.exe',win(a.PTH/'chrome-probe.cjs'),win(output),'--expect-login'],env=env,capture_output=True,timeout=60)
   log=a.R/'browser-execution.private.log';log.write_bytes(proc.stdout+proc.stderr);log.chmod(0o600)
   report=json.loads((output/'chrome-diagnostics.json').read_text())
   s=a.state();s['counts']['requests']=len(report['responses'])+len(report['failedRequests']);a.persist(s)
   self.check('Chrome-real-prelogin',proc.returncode==0 and report.get('failure') is None,stage=report['stage'])
   self.check('anonymous-real-session-401',any(x['url']==a.ORIGIN+'/api/auth/session' and x['status']==401 for x in report['responses']))
   self.check('no-JavaScript-or-network-failure',not report['javascriptErrors'] and not report['failedRequests'] and not report['blockedRequests'])
   s=a.state();s.update(httpPassed=True,httpChecks=len(self.results),phase='tested');a.persist(s)
  finally:signal.alarm(0);signal.signal(signal.SIGALRM,previous)
 def cleanup_data(self):
  a=self.a;s=a.state()
  if s.get('dataCleaned'):return
  if any(a.inspect(name)['State']['Running'] for name in a.SERVICES):raise a.Refused('WRITER_STILL_RUNNING')
  after={db:a.baseline(db) for db in a.DATABASES}
  a.save(a.R/'after-data-proof.json',{'matches':after==s['baseline'],'fingerprints':after})
  if after!=s['baseline']:raise a.Refused('ORIGINAL_DATA_DRIFT_NO_AUTOMATIC_RESTORE')
  s.update(dataCleaned=True,originalRowsMatch=True,cleanedRows=0,checkedTables=sum(len(v) for v in after.values()));a.persist(s)
  a.emit('anonymous-cleanup',tables=s['checkedTables'],originalRowsMatch=True,fixtureRows=0)


class ManualCampaign(AnonymousCampaign):
 """Persistent, read-only ERP handoff; close only through explicit operator action."""
 scope='HTTPS_MANUAL_12_SERVICES_READONLY_NO_FIXTURES'
 authorization_document='SESSION-MANUELLE-LOCALE.txt'
 components=('socle-api','tiers-api','contrats-api','factures-api','tresorerie-api',
  'gateway','socle-front','tiers-front','contrats-front','factures-front','tresorerie-front','erp-shell')
 def execute(self):
  a=self.a
  # Reuse prior immutable five-API compatibility evidence on identical DB contents.
  report=json.loads((a.PTH/'RESULTATS-FONCTIONNELS-LOCAUX.json').read_text())
  previous=Path(report['runDirectory']);compat=previous/'migration-jpa-results.json'
  self.check('five-API-evidence-integrity',a.m.digest(compat)==report['evidenceSha256']['migration-jpa-results.json'])
  self.check('five-API-compatibility',all(x['passed'] for x in json.loads(compat.read_text()).values()))
  self.check('same-images',a.m.plan('recettelocal')['images']==json.loads((a.PTH/'PLAN-FONCTIONNEL-LOCAL.json').read_text())['images'])
  old_baseline=json.loads((previous/'original-baseline.json').read_text())
  if getattr(self,'cycle_mode',False):
   self.check('same-migration-history',all(a.state()['baseline'][db].get('flyway_schema_history')==old_baseline[db].get('flyway_schema_history') for db in a.DATABASES))
  else:self.check('same-original-tables',a.state()['baseline']==old_baseline)
  a.migration_check()
  for db in ('socle','tiers','factures'):
   if db in a.DATABASES:a.backup(db)
  a.prepare_runtime();out=a.R/'runtime'
  overlay={'services':{}}
  # Protect optional APIs too: a later module selection reuses this runtime.
  for c in ('socle','tiers','contrats','factures','tresorerie'):
   overlay['services']['wavy-'+c+'-api-recette']={'environment':{'SPRING_JPA_HIBERNATE_DDL_AUTO':'validate','SPRING_SQL_INIT_MODE':'never'}}
  overlay['services']['wavy-socle-api-recette']['environment']['WAVY_BOOTSTRAP_ENABLED']='false'
  overlay['services']['wavy-factures-api-recette']['environment'].update(WAVY_AI_ACHAT_AUTO_CREATION_ENABLED='false',WAVY_AI_API_KEY='')
  a.save(out/'manual.overlay.json',overlay)
  shell=(out/'shell.conf.template').read_text()
  business_guard='''map "$request_method:$uri" $wavy_manual_write_denied {
 default 1;
 ~^(GET|HEAD|OPTIONS): 0;
 "POST:/api/auth/session" 0;
 "DELETE:/api/auth/session" 0;
 "POST:/api/auth/session/societe" 0;
}
'''
  needle='server_name recettelocal.wavyservices.fr;'
  if shell.count(needle)!=1:raise a.Refused('MANUAL_SHELL_SCOPE')
  shell=business_guard+shell.replace(needle,needle+'\n  if ($wavy_manual_write_denied) { return 403; }')
  (out/'shell.conf.template').write_text(shell)
  merged=json.loads(a.run(a.compose(out/'compose.https.yml')+['-f',str(out/'manual.overlay.json'),'config','--format','json']))
  a.save(a.R/'candidate-runtime.private.json',merged)
  self.start()
  current={db:a.baseline(db) for db in a.DATABASES}
  self.check('startup-original-rows-unchanged',current==a.state()['baseline'])
  a.save(a.R/'startup-data-proof.json',{'matches':current==a.state()['baseline'],'fingerprints':current})
  s=a.state();s.update(originalRowsMatch=True,checkedTables=sum(len(v) for v in current.values()));a.persist(s)
  a.activate_caddy()
  output=a.R/'browser';output.mkdir(mode=0o700)
  self.windows_node(a.PTH/'chrome-probe.cjs',[output],timeout=60,options=['--expect-login'])
  browser=json.loads((output/'chrome-diagnostics.json').read_text())
  self.check('Chrome-login-form-real-HTTPS',browser['failure'] is None and browser['dom']['emailInputs']==1)
  self.check('Gateway-Socle-anonymous-401',any(x['url']==a.ORIGIN+'/api/auth/session' and x['status']==401 for x in browser['responses']))
  # No authenticated call: offline verification of the known RECETTE seed account.
  self.provide_existing_credentials()
  s=a.state();s.update(httpPassed=True,httpChecks=len(self.results),phase='manual-ready',keepOpen=True,autoCleanup=False,businessReadOnly=True,credentialsProvided=True);s['counts']['requests']=len(browser['responses']);a.persist(s)
  a.emit('manual-ready',origin=a.ORIGIN,services=len(a.SERVICES),fixtureRows=0,automatedLogins=0,autoCleanup=False)
 def provide_existing_credentials(self):
  a=self.a
  users=json.loads(a.sql('socle',"SELECT json_agg(json_build_object('id',id,'email',email,'encoded',mot_de_passe_hash)) FROM utilisateur WHERE id=2 AND actif;"))
  if not users or len(users)!=1:raise a.Refused('EXISTING_TEST_ACCOUNT_REQUIRED')
  u=users[0]
  if u['email'] not in (a.REPO/'dev/recette/01_socle_recette.sql').read_text():raise a.Refused('TEST_ACCOUNT_NOT_FROM_RECETTE_SEED')
  encoded=u['encoded']
  if not encoded or encoded.startswith(('$2','{bcrypt}')):raise a.Refused('EXISTING_TEST_SECRET_NOT_AVAILABLE_NO_RESET')
  password=encoded[6:] if encoded.startswith('{noop}') else encoded
  if password.startswith('{'):raise a.Refused('UNSUPPORTED_CREDENTIAL_FORMAT')
  # Same immutable Socle artifact extracted by migration_check. No login/DB update.
  folder=a.R/'socle-crypto';java=folder/'VerifyExisting.java'
  java.write_text('''public class VerifyExisting { public static void main(String[]a)throws Exception {var r=new java.io.BufferedReader(new java.io.InputStreamReader(System.in));var decoder=java.util.Base64.getDecoder();String password=new String(decoder.decode(r.readLine()),java.nio.charset.StandardCharsets.UTF_8),encoded=new String(decoder.decode(r.readLine()),java.nio.charset.StandardCharsets.UTF_8);var encoder=new fr.wavy.socle_multitenant.configuration.MotDePasseCompatiblePasswordEncoder();if(!encoder.matches(password,encoded))System.exit(1);System.out.println("MATCH_OK");}}''')
  cp=str(folder/'BOOT-INF/classes')+':'+str(folder/'BOOT-INF/lib/*')
  a.run(['javac','--release','17','-cp',cp,'-d',str(folder),str(java)])
  import base64
  checked=a.run(['java','-cp',str(folder)+':'+cp,'VerifyExisting'],input=base64.b64encode(password.encode())+b'\n'+base64.b64encode(encoded.encode())+b'\n')
  if b'MATCH_OK' not in checked:raise a.Refused('EXISTING_TEST_SECRET_CHECK_FAILED')
  a.save(a.R/'identifiants.private.json',{'URL':a.ORIGIN,'Email':u['email'],'Mot de passe':password,'Compte':'Compte RECETTE existant du seed local ; aucun reset ni création','Session':'ERP en lecture seule métier ; PWA et IA fermées'})
  self.check('existing-credential-verified-offline-no-login',True)


class ModuleCampaign(ManualCampaign):
 """Cold initialization of the same HTTPS runtime, limited to selected modules."""
 scope='HTTPS_LOCAL_CYCLE_READONLY_NO_FIXTURES'
 authorization_document='WAVY-LOCAL-CYCLE.txt'
 allowKnownNetworkMembers=True
 cycle_mode=True
 def __init__(self,a):
  super().__init__(a)
  self.components=tuple(a.CYCLE_COMPONENTS);self.databases=tuple(a.CYCLE_DATABASES)
  if not set(self.components).issubset(a.m.COMPONENTS) or not set(self.databases).issubset(('socle','tiers','contrats','factures','tresorerie')):raise a.Refused('CYCLE_SCOPE')
 def start(self):
  a=self.a;path=a.R/'runtime/shell.conf.template'
  conf=json.loads((a.R/'candidate-runtime.private.json').read_text())['services']['wavy-erp-shell-recette']['environment']
  path.write_text(a.m.lazy_module_routes(path.read_text(),conf));super().start()
 def provide_existing_credentials(self):
  self.check('no-credential-or-fixture-creation',True)
 def execute(self):
  super().execute()
  s=self.a.state();s['credentialsProvided']=False;s['managedComponents']=list(self.components);self.a.persist(s)


class LocalCycle:
 """Internal implementation of ./wavy local; no second public command or Compose."""
 SCOPES={'HTTPS_MANUAL_12_SERVICES_READONLY_NO_FIXTURES','HTTPS_LOCAL_CYCLE_READONLY_NO_FIXTURES'}
 def __init__(self,a):
  self.a=a;self.m=a.m;self.directory=None;self.session={};self.ledger={};self.scope=None;self.components=()
  pointer=a.REPO/'deployments/recette-https-reservation.json'
  if not pointer.exists():return
  a.private_file(pointer);owner=json.loads(pointer.read_text())
  if owner.get('scope') not in self.SCOPES:raise a.Refused('Session locale réservée à une autre opération')
  root=Path(owner['runDirectory'])
  if root.resolve()!=root or root.is_symlink() or root.is_relative_to(a.REPO) or root.stat().st_uid!=os.getuid() or root.stat().st_mode&0o777!=0o700:raise a.Refused('PRIVATE_RUN_DIRECTORY')
  for name in ('authorization.json','state.private.json','candidate-runtime.private.json'):a.private_file(root/name)
  receipt=json.loads((root/'authorization.json').read_text());session=json.loads((root/'state.private.json').read_text())
  document='SESSION-MANUELLE-LOCALE.txt' if owner['scope'].startswith('HTTPS_MANUAL_') else 'WAVY-LOCAL-CYCLE.txt'
  if receipt.get('approved') is not True or receipt.get('scope')!=owner['scope'] or receipt.get('runDirectory')!=str(root) or receipt.get('authorizationDocumentSha256')!=self.m.digest(a.PTH/document):raise a.Refused('LOCAL_OWNER_APPROVAL')
  if receipt.get('planSha256')!=self.m.plan('recettelocal')['planSha256']:raise a.Refused('LOCAL_PLAN_CHANGED')
  if session.get('cleanupComplete'):raise a.Refused('Session déjà restaurée')
  if any(self.m.digest(Path(name))!=value for name,value in session['inputHashes'].items()):raise a.Refused('ACTIVE_INPUT_CHANGED')
  self.directory=root;self.scope=owner['scope'];self.session=session
  self.components=tuple(session.get('managedComponents', receipt.get('cycleComponents',ManualCampaign.components)))
  if not set(self.components).issubset(self.m.COMPONENTS):raise a.Refused('CYCLE_COMPONENT_SCOPE')
  self.config=json.loads((root/'candidate-runtime.private.json').read_text())
  path=root/'local-cycle.private.json'
  if path.exists():a.private_file(path);self.ledger=json.loads(path.read_text())
  a.R=root;a.SCOPE=self.scope;a.COMPONENTS=self.components;a.SERVICES=tuple(self.name(c) for c in self.components);a.DATABASES=tuple(session['baseline'])
  a.AUTH_MARKER=receipt['fixtureMarker'];a.AUTHORIZATION_DOCUMENT=document
  if self.scope.startswith('HTTPS_LOCAL_CYCLE'):
   a.CYCLE_COMPONENTS=self.components;a.CYCLE_DATABASES=a.DATABASES;a.PROFILE=ModuleCampaign(a)
  else:a.PROFILE=ManualCampaign(a)
 def name(self,node):return node.removesuffix('-postgres')+'-db-recette' if node.endswith('-postgres') else 'wavy-'+node+'-recette'
 def inspect(self,node):
  try:obj=self.a.inspect(self.name(node))
  except self.a.Refused:return None
  if obj['Config'].get('Labels',{}).get('com.docker.compose.project')!='wavy-recette':raise self.a.Refused('FOREIGN_COMPOSE_CONTAINER')
  return obj
 def running(self):
  return {node for node in self.m.LOCAL_DEPS if (obj:=self.inspect(node)) and obj['State']['Running']}
 def roots(self,running):
  inferred={c for c in self.m.MODULES if ('pwa' if c=='pwa' else c+'-front') in running}
  return set(self.ledger.get('roots',inferred))|inferred
 def command_args(self):return ['docker','compose','-p','wavy-recette','-f',str(self.directory/'candidate-runtime.private.json')]
 def save(self,roots,phase,action,details=None):
  self.ledger.update(roots=sorted(roots),phase=phase,action=action,updatedAt=self.a.now(),details=details or {})
  self.a.save(self.directory/'local-cycle.private.json',self.ledger)
  path=self.directory/'local-cycle-journal.jsonl';fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND|os.O_NOFOLLOW,0o600)
  with os.fdopen(fd,'a') as stream:stream.write(json.dumps({'at':self.a.now(),'action':action,'phase':phase,'modules':sorted(roots),'details':details or {}},ensure_ascii=False)+'\n')
 def wait(self,nodes):
  for node in nodes:
   for _ in range(90):
    obj=self.inspect(node)
    if not obj or not obj['State']['Running']:raise self.a.Refused('Service non démarré : '+node)
    health=obj['State'].get('Health',{}).get('Status')
    if health=='healthy':break
    if health is None:
     if node=='pwa':self.a.run(['docker','exec',self.name(node),'wget','-q','-O','/dev/null','http://127.0.0.1/'])
     break
    if health=='unhealthy':raise self.a.Refused('Service unhealthy : '+node)
    time.sleep(1)
   else:raise self.a.Refused('Délai santé dépassé : '+node)
 def ensure_databases(self,nodes):
  for node in sorted(n for n in nodes if n.endswith('-postgres')):
   obj=self.inspect(node)
   if not obj or not any(m['Type']=='volume' and m['Destination']=='/var/lib/postgresql/data' for m in obj.get('Mounts',[])):raise self.a.Refused('Base/volume existant requis : '+node)
   if not obj['State']['Running']:self.a.run(['docker','start',self.name(node)])
  self.wait([n for n in nodes if n.endswith('-postgres')])
 def prepare_close(self):
  if not self.directory:return
  # Called only after --confirm-close, restores original DB availability for proof.
  self.a.m.run(['docker','info','--format','{{.OSType}}'])
  self.ensure_databases({db+'-postgres' for db in self.session['baseline']})
 def snapshot_components(self,apps):
  a=self.a;added=set(apps)-set(self.components)
  if not added:return
  base=json.loads(a.run(a.compose()+['config','--format','json']))['services']
  old=json.loads((self.directory/'snapshots.private.json').read_text())
  original=json.loads((self.directory/'original-runtime.private.json').read_text())
  references={}
  for component in sorted(added):
   name=self.name(component);obj=self.inspect(component)
   if obj is None:raise a.Refused('Conteneur existant requis : '+component)
   a.PROFILE.snapshot_guard(obj,base[name],name)
   image=json.loads(a.run(['docker','image','inspect',obj['Image']]))[0]
   prefix='ghcr.io/fabffo/wavy-'+component+'@sha256:'
   reference=next(x for x in image['RepoDigests'] if x.startswith(prefix))
   old[name]=obj;original['services'][name]['image']=reference;references[name]=reference
  a.save(self.directory/'snapshots.private.json',old);a.save(self.directory/'original-runtime.private.json',original)
  self.components=tuple(c for c in self.m.COMPONENTS if c in set(self.components)|added)
  s=a.state();s['managedComponents']=list(self.components);s.setdefault('originalReferences',{}).update(references);a.persist(s)
  a.COMPONENTS=self.components;a.SERVICES=tuple(self.name(c) for c in self.components)
 def extend_databases(self,nodes):
  a=self.a;s=a.state();added={n.removesuffix('-postgres') for n in nodes if n.endswith('-postgres')}-set(s['baseline'])
  if not added:return
  a.DATABASES=tuple(c for c in ('socle','tiers','contrats','factures','tresorerie') if c in set(a.DATABASES)|added)
  report=json.loads((a.PTH/'RESULTATS-FONCTIONNELS-LOCAUX.json').read_text())
  previous=json.loads((Path(report['runDirectory'])/'original-baseline.json').read_text())
  for db in sorted(added):
   observed=a.baseline(db)
   if observed.get('flyway_schema_history')!=previous[db].get('flyway_schema_history'):raise a.Refused('Schéma différent : '+db)
   s['baseline'][db]=observed
  a.persist(s);self.session=s
  for db in sorted(added&{'socle','tiers','factures'}):a.backup(db)
 def lazy_shell(self):
  a=self.a;path=self.directory/'runtime/shell.conf.template';before=path.read_text()
  updated=self.m.lazy_module_routes(before,self.config['services'][self.name('erp-shell')]['environment'])
  if before==updated:return
  backup=self.directory/'shell-before-modules.conf'
  if not backup.exists():backup.write_text(before);backup.chmod(0o600)
  path.write_text(updated)
  obj=self.inspect('erp-shell')
  if obj and obj['State']['Running']:
   try:a.run(['docker','exec',self.name('erp-shell'),'sh','-ec','/docker-entrypoint.d/20-envsubst-on-templates.sh; nginx -t; nginx -s reload'])
   except BaseException:
    path.write_text(before)
    a.run(['docker','exec',self.name('erp-shell'),'sh','-ec','/docker-entrypoint.d/20-envsubst-on-templates.sh; nginx -t'])
    raise
 def start(self,nodes):
  self.ensure_databases(nodes)
  apps=set(nodes)&set(self.m.COMPONENTS)
  self.extend_databases(nodes)
  self.snapshot_components(apps)
  self.m.check_images('recettelocal',apps)
  self.lazy_shell()
  phases=[{c for c in apps if c.endswith('-api')},{'gateway'}&apps,{c for c in apps if c.endswith('-front') or c=='pwa'},{'erp-shell'}&apps]
  for phase in phases:
   stopped=[]
   for node in sorted(phase):
    obj=self.inspect(node)
    if obj and obj['State']['Running']:
     expected=json.loads(self.a.run(['docker','image','inspect',self.m.plan('recettelocal')['images'][node]]))[0]['Id']
     if obj['Image']!=expected:raise self.a.Refused('Image active différente, déploiement explicite requis : '+node)
     if node!='erp-shell' and self.a.ports_bindings(obj):raise self.a.Refused('Publication directe interdite : '+node)
    else:stopped.append(self.name(node))
   if stopped:self.a.run(self.command_args()+['up','-d','--no-deps','--no-build','--pull','never',*stopped],timeout=180)
   self.wait(phase)
  current=self.a.canonical(self.a.caddy_config());s=self.a.state()
  if current==s['caddyOriginalHash']:
   s.update(servicesReady=True,caddyRestored=False);self.a.persist(s);self.a.activate_caddy()
  elif current!=s['caddyCandidateHash']:raise self.a.Refused('Caddy modifié par un autre opérateur')
 def bootstrap(self,modules):
  a=self.a;nodes=self.m.local_services(modules)
  root=Path(tempfile.mkdtemp(prefix='wavy-local-',dir=str(Path.home())));root.chmod(0o700)
  a.CYCLE_COMPONENTS=tuple(c for c in self.m.COMPONENTS if c in nodes)
  a.CYCLE_DATABASES=tuple(c for c in ('socle','tiers','contrats','factures','tresorerie') if c+'-postgres' in nodes)
  receipt={'scope':ModuleCampaign.scope,'approved':True,'runDirectory':str(root),'fixtureMarker':__import__('secrets').token_hex(6),'authorizationDocumentSha256':self.m.digest(a.PTH/ModuleCampaign.authorization_document),'planSha256':self.m.plan('recettelocal')['planSha256'],'cycleComponents':list(a.CYCLE_COMPONENTS),'cycleDatabases':list(a.CYCLE_DATABASES),'approvalSource':'Explicit ./wavy local lifecycle invocation; no business data writes or PWA opening','caddyBinary':'/mnt/c/Users/FabriceFOUGERY/AppData/Local/Microsoft/WinGet/Packages/CaddyServer.Caddy_Microsoft.Winget.Source_8wekyb3d8bbwe/caddy.exe'}
  a.save(root/'authorization.json',receipt)
  self.ensure_databases(nodes)
  result=a.execute(root,root/'authorization.json',functional='cycle')
  if not result['passed']:raise a.Refused('Initialisation locale incomplète ; preuves conservées : '+str(root))
  self.__init__(a)
 def pwa_close(self):
  if not self.directory:raise self.a.Refused('Session HTTPS locale requise')
  self.a.PROFILE.close_gate()
  self.save(self.roots(self.running()),'pwa-closed','pwa-close')
  return {'passed':True,'pwaAccess':'closed','servicesStopped':False,'businessDataCleaned':False}
 def pwa_routes(self):
  a=self.a;out=self.directory/'runtime';path=out/'shell.conf.template';before=path.read_text()
  if 'include /etc/nginx/wavy-https/pwa-preview.conf;' in before:return
  gate=out/'gate';gate.mkdir(mode=0o755,exist_ok=True);gate.chmod(0o755);out.chmod(0o755)
  routes=(a.PROFILE.private/'routes.conf').read_text().replace('wavy-pwa-preprod','wavy-pwa-recette').replace('/run/wavy-private-pwa-gate/gate.sock','/etc/nginx/wavy-https/gate/gate.sock')
  canonical='proxy_set_header Host recettelocal.wavyservices.fr; proxy_set_header X-Forwarded-Host recettelocal.wavyservices.fr; proxy_set_header X-Forwarded-Proto https; proxy_set_header X-Forwarded-Port 443; proxy_set_header X-Forwarded-For $http_x_forwarded_for; proxy_set_header Forwarded "";'
  routes=re.sub(r'proxy_set_header Host \$host;\s*proxy_set_header X-Forwarded-Proto \$scheme;\s*proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;',canonical,routes)
  # Gate cookie AND live authenticated Socle session; backend still owns roles/companies.
  routes=routes.replace('location = /__private_pwa_session {','location = /__private_cookie_gate {')
  routes+='\nlocation = /__private_pwa_session { internal; auth_request /__private_cookie_gate; proxy_pass $private_api_origin/api/auth/session; proxy_pass_request_body off; proxy_set_header Content-Length ""; proxy_set_header Cookie $http_cookie; '+canonical+' }\n'
  routes+='location = /pwa-integration.json { auth_request /__private_pwa_session; error_page 401 403 500 502 503 504 = @pwa_preview_disabled; proxy_pass http://127.0.0.1:8087/__pwa_enabled; add_header Cache-Control "no-store" always; }\nlocation @pwa_preview_disabled { default_type application/json; add_header Cache-Control "no-store" always; return 200 \'{"enabled":false}\'; }\n'
  (out/'pwa-preview.conf').write_text(routes)
  old='location = /pwa-integration.json { add_header Cache-Control "no-store" always; }'
  if old not in before or 'include /etc/nginx/wavy-https/closed.conf;' not in before:raise a.Refused('PWA_TEMPLATE_SCOPE')
  updated=before.replace(old,'').replace('include /etc/nginx/wavy-https/closed.conf;','include /etc/nginx/wavy-https/pwa-preview.conf;')
  updated=updated.replace('server { listen 127.0.0.1:8087;', 'server { listen 127.0.0.1:8087; location = /__pwa_enabled { default_type application/json; return 200 \'{"enabled":true}\'; }')
  backup=out/'shell-before-pwa-preview.conf'
  if not backup.exists():backup.write_text(before);backup.chmod(0o600)
  path.write_text(updated)
  try:a.run(['docker','exec',self.name('erp-shell'),'sh','-ec','/docker-entrypoint.d/20-envsubst-on-templates.sh; nginx -t; nginx -s reload'])
  except BaseException:
   path.write_text(before);a.run(['docker','exec',self.name('erp-shell'),'sh','-ec','/docker-entrypoint.d/20-envsubst-on-templates.sh; nginx -t']);raise
  state=a.state();state['gateSocketDir']=str(gate);a.persist(state)
 def pwa_open(self):
  a=self.a
  if not self.directory:raise a.Refused('Démarrer ./wavy local up pwa avant ouverture')
  self.start(self.m.local_services(['pwa']));self.pwa_close();self.pwa_routes()
  credentials=self.directory/'identifiants.private.json';a.private_file(credentials)
  output=self.directory/('pwa-preview-'+str(time.time_ns()));output.mkdir(mode=0o700)
  win=lambda p:a.run(['wslpath','-w',str(p)]).decode().strip()
  env=os.environ.copy();env['WSLENV']='WAVY_PLAYWRIGHT_CORE';env['WAVY_PLAYWRIGHT_CORE']=win(a.REPO.parent/'wavy-erp-shell/node_modules/playwright-core')
  log=open(output/'execution.private.log','wb');os.chmod(log.name,0o600)
  browser=subprocess.Popen(['/mnt/c/Users/FabriceFOUGERY/AppData/Local/hermes/node/node.exe',win(a.PTH/'chrome-notes.cjs'),win(credentials),win(output),'--preview'],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,start_new_session=True)
  try:
   import select
   def message():
    ready,_,_=select.select([browser.stdout],[],[],65)
    if not ready:raise a.Refused('PWA_CHROME_TIMEOUT')
    line=browser.stdout.readline(16384)
    if not line:raise a.Refused('PWA_CHROME_FAILED: '+str(output))
    return json.loads(line)
   session=message()
   if session.get('kind')!='session' or session.get('user')!=2 or session.get('tenant')!=3 or session.get('company') not in (4,5) or not {'NOTE_DE_FRAIS','SUPER_NOTE_DE_FRAIS'}&set(session.get('roles',[])):raise a.Refused('PWA_TEST_ACCOUNT_SCOPE')
   read,write=os.pipe()
   try:
    proc=subprocess.Popen([sys.executable,'-B',str(a.PROFILE.private/'session-gate.py'),'--socket-dir',str(self.directory/'runtime/gate'),'--session-fd',str(read),'--parent-pid',str(os.getpid()),'--seconds','900'],pass_fds=(read,),stdout=subprocess.DEVNULL,stderr=log,start_new_session=True)
    os.close(read);read=None
    state=a.state();state.update(gatePid=proc.pid,gateSocketDir=str(self.directory/'runtime/gate'),pwaPreviewBrowserPid=browser.pid,pwaPreviewExpiresAt=time.time()+900);a.persist(state)
    os.write(write,session.pop('cookie').encode())
   finally:
    if read is not None:os.close(read)
    os.close(write)
   for _ in range(50):
    if (self.directory/'runtime/gate/gate.sock').is_socket():break
    if proc.poll() is not None:raise a.Refused('PWA_GATE_START_FAILED')
    time.sleep(.1)
   else:raise a.Refused('PWA_GATE_START_TIMEOUT')
   browser.stdin.write(b'open\n');browser.stdin.flush()
   report=message()
   if report.get('kind')!='ready' or not report.get('passed'):raise a.Refused('PWA_CHROME_ASSERTIONS_FAILED')
   self.save(self.roots(self.running()),'pwa-preview','pwa-open',{'seconds':900,'businessWrites':False,'evidence':str(output)})
   return {'passed':True,'origin':a.ORIGIN+'/pwa/notes-frais','scope':'one dedicated Chrome session, existing test account, read only','expiresInSeconds':900,'closeCommand':'./wavy local pwa-close','evidenceDirectory':str(output),'servicesLeftRunning':True}
  except BaseException:
   a.PROFILE.close_gate();browser.terminate();raise
  finally:log.close()
 def status(self,selected):
  rows={}
  for node in sorted(self.m.local_services(selected)):
   obj=self.inspect(node);rows[node]={'container':self.name(node),'running':bool(obj and obj['State']['Running']),'state':obj['State'].get('Status','inconnu') if obj else 'absent','health':obj['State'].get('Health',{}).get('Status') if obj else None}
  return {'environment':'recettelocal','composeProject':'wavy-recette','origin':'https://recettelocal.wavyservices.fr','modules':selected,'services':rows,'pwaAccess':'closed by default; starting a container never opens its session gate','autoCleanup':False}
 def test(self,selected):
  report=self.status(selected);checks=[]
  for node,row in report['services'].items():checks.append({'control':node,'passed':row['running'] and row['health'] in (None,'healthy')})
  if all(x['passed'] for x in checks):
   self.wait(self.m.local_services(selected))
   host='recettelocal.wavyservices.fr'
   for path,expected in (('/',200),('/api/auth/session',401),('/pwa/',404)):
    proc=subprocess.run(['curl.exe','--silent','--show-error','--ssl-revoke-best-effort','--max-time','8','--resolve',host+':443:127.0.0.1','--dump-header','-','--output','NUL','https://'+host+path],capture_output=True,timeout=12)
    headers=proc.stdout.decode(errors='replace').lower();statuses=re.findall(r'http/\S+ (\d+)',headers)
    ok=proc.returncode==0 and bool(statuses) and int(statuses[-1])==expected
    if path=='/api/auth/session':ok=ok and 'www-authenticate: basic' not in headers
    checks.append({'control':'HTTPS '+path,'passed':ok,'expected':expected})
  return {'passed':all(x['passed'] for x in checks),'scope':'Non-mutating health/HTTPS; no login, Notes/IA, fixtures or isolation-suite replay','checks':checks,'pwaAccess':'gate closed, not a PWA functional GO'}
 def command(self,action,selected,dry_run=False,databases=False,tail=100):
  a=self.a;self.m.run(['docker','info','--format','{{.OSType}}'])
  lock=a.REPO/'deployments/recette.lock';lock.parent.mkdir(exist_ok=True)
  fd=os.open(lock,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
  try:
   fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
   running=self.running();roots=self.roots(running);required=self.m.local_services(selected)
   stopped,kept=self.m.local_stop_plan(selected,roots,running)
   targets=stopped if databases else {x for x in stopped if not x.endswith('-postgres')}
   if dry_run:return {'action':action,'modules':selected,'required':sorted(required),'wouldStop':sorted(targets&running) if action in ('down','restart') else [],'retainedShared':sorted(kept&running),'databasePolicy':'stop only unused' if databases else 'keep running','dryRun':True,'mutations':False}
   if action=='pwa-open':return self.pwa_open()
   if action=='pwa-close':return self.pwa_close()
   if action=='status':return self.status(selected)
   if action=='test':return self.test(selected)
   if action=='logs':
    nodes=[c for c in sorted(required) if c in running]
    names=[self.name(c) for c in nodes]
    if not names:return {'logs':'Aucun service sélectionné actif'}
    services=[c if c.endswith('-postgres') else self.name(c) for c in nodes]
    cmd=['docker','logs','--tail',str(tail),names[0]] if len(names)==1 else ((self.command_args() if self.directory else a.compose())+['logs','--no-color','--tail',str(tail),*services])
    logged=subprocess.run(cmd,capture_output=True,timeout=30)
    if logged.returncode:raise a.Refused('Lecture des logs refusée')
    raw=(logged.stdout+logged.stderr).decode(errors='replace')
    secrets=[]
    for conf in getattr(self,'config',{}).get('services',{}).values():
     secrets.extend(str(v) for k,v in conf.get('environment',{}).items() if v and any(word in k.upper() for word in ('PASSWORD','SECRET','API_KEY','TOKEN')) and len(str(v))>=4)
    for secret in secrets:raw=raw.replace(secret,'[REDACTED]')
    raw=re.sub(r'(?i)(WAVY_SESSION=|Bearer\s+|Basic\s+)[^\s;,"\x27]+',r'\1[REDACTED]',raw)
    raw=re.sub(r'(?i)("?(?:password|motDePasse)"?\s*[:=]\s*)"[^"\n]*"',r'\1"[REDACTED]"',raw)
    print(raw,end='');return None
   if self.directory is None:
    if action=='down':return {'passed':True,'stopped':[],'message':'Aucune session HTTPS locale gérée ; aucun arrêt des conteneurs historiques'}
    # execute owns the same lock during bootstrap; release this descriptor first.
    fcntl.flock(fd,fcntl.LOCK_UN);self.bootstrap(selected);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    running=self.running();roots=self.roots(running);stopped,kept=self.m.local_stop_plan(selected,roots,running)
    targets=stopped if databases else {x for x in stopped if not x.endswith('-postgres')}
   if action=='up' and required.issubset(running):
    # Still verify digests, optional-route support and HTTPS, without recreating live apps.
    self.start(required);roots|=set(selected)
   else:
    self.save(roots,'intent',action,{'selected':selected})
    try:
     if action in ('down','restart'):
      if 'pwa' in selected:self.pwa_close()
      self.lazy_shell()
      apps=[x for x in targets&running if not x.endswith('-postgres')]
      if apps:a.run(['docker','stop',*[self.name(x) for x in sorted(apps)]],timeout=120)
      if any(self.inspect(x)['State']['Running'] for x in apps):raise a.Refused('WRITER_STILL_RUNNING')
      if action=='down' and databases:
       dbs=[x for x in targets&running if x.endswith('-postgres')]
       if dbs:a.run(['docker','stop',*[self.name(x) for x in sorted(dbs)]],timeout=120)
     if action=='down':roots-=set(selected)
     else:self.start(required);roots|=set(selected)
    except BaseException as error:
     self.save(roots,'failed',action,{'error':str(error) if isinstance(error,a.Refused) else type(error).__name__});raise
   self.save(roots,'ready',action,{'selected':selected,'retainedShared':sorted(kept) if action!='up' else []})
   if action=='down' and not roots and 'erp-shell' not in self.running():a.restore_caddy()
   return {'passed':True,'action':action,'modules':selected,'activeModules':sorted(roots),'retainedShared':sorted(kept) if action!='up' else [],'databasePolicy':'stop only unused' if databases else 'keep running','volumesDeleted':False,'imagesRebuilt':False,'autoCleanup':False,'sessionDirectory':str(self.directory),'pwaAccess':'closed unless separately authorized session gate is open'}
  finally:os.close(fd)

class PermanentLocalCycle(LocalCycle):
 """Daily MSI runtime. Separate local policy, same Compose, images and dependency graph."""
 def __init__(self,a):
  self.a=a;self.m=a.m
  if 'microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower() or Path('/proc/sys/kernel/hostname').read_text().strip().upper()!='MSI':raise a.Refused('Profil permanent réservé à MSI/WSL')
  self.m.run(['docker','info','--format','{{.OSType}}'])
  self.directory=Path.home()/'.local/state/wavy/recettelocal'
  self.directory.mkdir(parents=True,exist_ok=True,mode=0o700)
  if self.directory.is_symlink() or self.directory.stat().st_uid!=os.getuid() or self.directory.stat().st_mode&0o777!=0o700:raise a.Refused('LOCAL_PRIVATE_DIRECTORY')
  self.scope='MSI_LOCAL_PERMANENT';self.components=tuple(self.m.COMPONENTS);self.session={};self.ledger={}
  self.config={}
  path=self.directory/'candidate-runtime.private.json'
  if path.exists():
   a.private_file(path);self.config=json.loads(path.read_text())
   if self.config.get('x-wavy-local-only')!='recettelocal.wavyservices.fr':raise a.Refused('LOCAL_RUNTIME_SCOPE')
  path=self.directory/'local-cycle.private.json'
  if path.exists():a.private_file(path);self.ledger=json.loads(path.read_text())
  a.R=self.directory
  # A local stop never invokes deployment restoration/cleanup or Caddy rollback.
  a.restore_caddy=lambda:None
 def pwa_close(self):
  return {'passed':True,'pwaAccess':'permanent; stop with ./wavy local down pwa','servicesStopped':False,'businessDataCleaned':False}
 def build_frontends(self):
  import shutil
  a=self.a;builds=self.directory/'frontend-builds';builds.mkdir(mode=0o700,exist_ok=True)
  artifacts={}
  for component,project in (('erp-shell','wavy-erp-shell'),('pwa','wavy-pwa'),*((c+'-front','wavy-'+c+'-front') for c in ('tiers','contrats','factures','tresorerie'))):
   source=a.REPO.parent/project
   workspace=source
   # Reproduce existing Dockerfile API build arguments in a private copy;
   # never edit the source environment or change the runtime API routing.
   temporary=None
   if component in ('contrats-front','factures-front','tresorerie-front'):
    temporary=tempfile.TemporaryDirectory(prefix='frontend-compile-',dir=self.directory)
    workspace=Path(temporary.name)/project
    shutil.copytree(source,workspace,ignore=shutil.ignore_patterns('node_modules','dist','.git','.angular','test-results','playwright-report'))
    (workspace/'node_modules').symlink_to(source/'node_modules',target_is_directory=True)
    envfile=workspace/'src/environments/environment.ts'
    text=envfile.read_text().replace("apiBaseUrl: 'http://localhost:8088'", "apiBaseUrl: ''").replace("apiGatewayBaseUrl: 'http://localhost:8088/api'", "apiGatewayBaseUrl: '/api'")
    envfile.write_text(text)
   compiled=subprocess.run(['npm','run','build'],cwd=workspace,capture_output=True,timeout=240)
   log=self.directory/(component+'-build.private.log');log.write_bytes(compiled.stdout+compiled.stderr);log.chmod(0o600)
   if compiled.returncode:raise a.Refused('Compilation frontale en échec : '+str(log))
   dist=workspace/'dist'/project/'browser'
   if not (dist/'index.html').is_file():raise a.Refused('Build frontal manquant : '+project)
   version=hashlib.sha256(b''.join(str(p.relative_to(dist)).encode()+p.read_bytes() for p in sorted(dist.rglob('*')) if p.is_file())).hexdigest()[:20]
   target=builds/(component+'-'+version)
   if not target.exists():shutil.copytree(dist,target)
   artifacts[component]=str(target)
   if temporary:temporary.cleanup()
  a.save(self.directory/'local-frontends.private.json',artifacts)
  return {'built':list(artifacts),'scope':'MSI local assets only; no image publication'}
 def prepare_permanent(self):
  a=self.a
  # Transfer the old temporary session once, without running its teardown.
  reservation=a.REPO/'deployments/recette-https-reservation.json'
  legacy_root=None
  if reservation.exists():
   a.private_file(reservation);owner=json.loads(reservation.read_text())
   if owner.get('scope') not in LocalCycle.SCOPES:raise a.Refused('Opération de qualification en cours : conversion refusée')
   legacy=LocalCycle(a);legacy_root=legacy.directory;a.PROFILE.close_gate();a.R=self.directory
   a.save(self.directory/'legacy-session.private.json',owner)
  out=self.directory/'runtime'
  if not out.exists():self.m.render('recettelocal',out,self.subnet())
  out.chmod(0o755)  # Non-secret Nginx includes/availability; parent with secrets stays 0700.
  (out/'shell.conf.template').write_text(self.m.permanent_local_shell('recettelocal.wavyservices.fr'))
  (out/'local-pwa.conf').write_text(self.m.permanent_local_routes('recettelocal.wavyservices.fr'))
  if not (out/'pwa-integration.json').exists():(out/'pwa-integration.json').write_text('{"enabled":false}')
  conf=json.loads(a.run(a.compose(out/'compose.https.yml')+['config','--format','json']))
  for component in self.components:
   service=conf['services'][self.name(component)]
   service['image']=self.m.plan('recettelocal')['images'][component]
   if component.endswith('-api'):
    service['environment'].update(SPRING_JPA_HIBERNATE_DDL_AUTO='validate',SPRING_SQL_INIT_MODE='never')
  factures=conf['services'][self.name('factures-api')]
  factures['environment'].update(WAVY_FACTURES_STOCKAGE_JUSTIFICATIFS='/app/justificatifs',WAVY_AI_ACHAT_AUTO_CREATION_ENABLED='false')
  # Dedicated durable local volume, outside the public web root. Never removed by down.
  factures['volumes']=[{'type':'volume','source':'local-justificatifs','target':'/app/justificatifs','volume':{'nocopy':True}}]
  conf.setdefault('volumes',{})['local-justificatifs']={'name':'wavy-recettelocal-justificatifs'}
  conf['x-wavy-local-only']='recettelocal.wavyservices.fr'
  artifacts=self.directory/'local-frontends.private.json'
  if artifacts.exists():
   a.private_file(artifacts)
   for component,directory in json.loads(artifacts.read_text()).items():
    path=Path(directory).resolve()
    if component not in ('erp-shell','pwa','tiers-front','contrats-front','factures-front','tresorerie-front') or not path.is_relative_to(self.directory/'frontend-builds') or not (path/'index.html').is_file():raise a.Refused('LOCAL_FRONTEND_PATH')
    conf['services'][self.name(component)].setdefault('volumes',[]).append({'type':'bind','source':str(path),'target':'/usr/share/nginx/html','read_only':True,'bind':{'create_host_path':False}})
  shell=conf['services'][self.name('erp-shell')]
  template=out/'shell.conf.template'
  template.write_text(self.m.lazy_module_routes(template.read_text(),shell['environment']))
  # Never silently replace a document store already configured in an existing container.
  obj=self.inspect('factures-api')
  if obj:
   env=a.environment(obj['Config']['Env']);old=env.get('WAVY_FACTURES_STOCKAGE_JUSTIFICATIFS','')
   if old:
    mounts=[v for v in obj.get('Mounts',[]) if v['Destination']==old]
    if len(mounts)!=1 or mounts[0]['Type']!='volume':raise a.Refused('Stockage existant à préserver : configuration manuelle requise')
    conf['volumes']['local-justificatifs']['name']=mounts[0]['Name']
    if mounts[0].get('SubPath') or any(v.get('VolumeOptions',{}).get('Subpath') for v in obj.get('HostConfig',{}).get('Mounts',[])):raise a.Refused('Sous-volume documentaire existant à examiner')
  self.config=conf;a.save(self.directory/'candidate-runtime.private.json',conf)
  if legacy_root:
   state=json.loads((legacy_root/'state.private.json').read_text());state['permanentLocal']=str(self.directory);a.save(legacy_root/'state.private.json',state)
   reservation.unlink()
  a.save(self.directory/'runtime-info.json',{'mode':self.scope,'origin':a.ORIGIN,'cleanupAutomatic':False,'businessWrites':'application permissions','legacyEvidenceDirectory':str(legacy_root) if legacy_root else None})
 def subnet(self):
  network=json.loads(self.a.run(['docker','network','inspect','wavy-recette']))[0]
  subnet=network['IPAM']['Config'][0]['Subnet'];self.m.proxy_regex(subnet);return subnet
 def ensure_https(self):
  a=self.a;file=Path('/mnt/c/Wavy/Caddy/Caddyfile');candidate=(a.PTH/'Caddyfile.local-only.candidate').read_bytes();source=file.read_bytes();marker=b'\n\nrecette.wavyservices.fr'
  if marker not in source or source.partition(marker)[2]!=candidate.partition(marker)[2]:raise a.Refused('Blocs HTTPS distants différents : aucun remplacement')
  expected=a.adapted(candidate)
  if a.canonical(a.caddy_config())!=a.canonical(expected):
   a.caddy(['--header','Content-Type: application/json','--data-binary','@-','http://127.0.0.1:2019/load'],json.dumps(expected).encode())
  if source!=candidate:a.atomic_bytes(file,candidate)
 def ensure_storage(self):
  a=self.a;name=self.config['volumes']['local-justificatifs']['name']
  if not re.fullmatch(r'[a-zA-Z0-9_.-]+',name):raise a.Refused('LOCAL_STORAGE_VOLUME')
  a.run(['docker','volume','create',name])
  ref=self.config['services'][self.name('factures-api')]['image']
  script='uid="$(id -u wavy)"; gid="$(id -g wavy)"; if [ "$(stat -c %u /store)" != "$uid" ]; then [ -z "$(find /store -mindepth 1 -maxdepth 1 -print -quit)" ] || exit 1; chown "$uid:$gid" /store; chmod 700 /store; fi'
  a.run(['docker','run','--rm','--pull','never','--network','none','--user','0:0','--mount','type=volume,source='+name+',target=/store,volume-nocopy','--entrypoint','sh',ref,'-ec',script])
 def start(self,nodes):
  self.prepare_permanent();self.ensure_databases(nodes)
  if 'factures-api' in nodes:self.ensure_storage()
  apps=set(nodes)&set(self.components);self.m.check_images('recettelocal',apps)
  phases=[{c for c in apps if c.endswith('-api')},{'gateway'}&apps,{c for c in apps if c.endswith('-front') or c=='pwa'},{'erp-shell'}&apps]
  for phase in phases:
   if phase:self.a.run(self.command_args()+['up','-d','--no-deps','--no-build','--pull','never',*[self.name(c) for c in sorted(phase)]],timeout=180)
   self.wait(phase)
  if 'erp-shell' in apps:self.a.run(['docker','exec',self.name('erp-shell'),'sh','-ec','/docker-entrypoint.d/20-envsubst-on-templates.sh; nginx -t; nginx -s reload'])
  self.ensure_https();self.refresh_pwa_availability()
 def refresh_pwa_availability(self):
  if not self.config:return
  ready=True
  for node in ('pwa','factures-api','gateway','socle-api'):
   obj=self.inspect(node)
   ready=ready and bool(obj and obj['State']['Running'] and obj['State'].get('Health',{}).get('Status','healthy')=='healthy')
  path=self.directory/'runtime/pwa-integration.json'
  path.write_text(json.dumps({'enabled':ready}));path.chmod(0o644)
 def lazy_shell(self):pass
 def status(self,selected):
  report=super().status(selected);report.update(mode=self.scope,pwaAccess='authenticated users with Notes permissions; no session lease',businessWrites='application permissions',autoCleanup=False)
  return report
 def browser_test(self,layout=None):
  a=self.a;legacy=self.directory/'legacy-session.private.json'
  if not legacy.exists():raise a.Refused('Compte de test : fournir un fichier privé identifiants.private.json dans le dossier local')
  credentials=Path(json.loads(legacy.read_text())['runDirectory'])/'identifiants.private.json';a.private_file(credentials)
  output=self.directory/('chrome-'+str(time.time_ns()));output.mkdir(mode=0o700)
  win=lambda p:a.run(['wslpath','-w',str(p)]).decode().strip()
  env=os.environ.copy();env['WSLENV']='WAVY_PLAYWRIGHT_CORE';env['WAVY_PLAYWRIGHT_CORE']=win(a.REPO.parent/'wavy-erp-shell/node_modules/playwright-core')
  with open(output/'execution.private.log','wb') as log:
   os.chmod(log.name,0o600)
   browser=subprocess.Popen(['/mnt/c/Users/FabriceFOUGERY/AppData/Local/hermes/node/node.exe',win(a.PTH/'chrome-notes.cjs'),win(credentials),win(output),*(['--layout',layout] if layout else ['--permanent'])],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=log,start_new_session=True)
   import select
   ready,_,_=select.select([browser.stdout],[],[],240 if layout else 90)
   if not ready:raise a.Refused('Chrome : délai dépassé, preuves conservées '+str(output))
   message=browser.stdout.readline(16384)
   if not message:raise a.Refused('Chrome : échec, preuves conservées '+str(output))
   result=json.loads(message)
   if result.get('kind')!='ready' or not result.get('passed'):raise a.Refused('Contrôle Chrome en échec')
  return {'passed':True,'evidenceDirectory':str(output),'browserLeftOpen':not bool(layout),'businessWritesAutomated':0,'sessionLease':False}
 def command(self,action,selected,**options):
  if action in ('pwa-open','pwa-close'):raise self.a.Refused('Le mode local permanent ne nécessite plus pwa-open/pwa-close ; utiliser up/down pwa et le navigateur habituel')
  result=super().command(action,selected,**options)
  if action in ('up','down','restart') and not options.get('dry_run'):self.refresh_pwa_availability()
  if isinstance(result,dict):
   if 'sessionDirectory' in result:result['runtimeDirectory']=result.pop('sessionDirectory')
   result.update(mode=self.scope,pwaAccess='application authentication and Notes permissions; no temporary gate',autoCleanup=False)
  return result
