#!/usr/bin/env python3
"""Phase MSI autorisée : huit services existants,54 lignes Socle, restauration finale."""
import fcntl,hashlib,hmac,importlib.util,io,json,os,re,secrets,signal,stat,subprocess,sys,tarfile,time,zipfile
from datetime import datetime,timezone
from http.cookies import SimpleCookie
from pathlib import Path
PTH=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('https_candidate',PTH/'wavy_deploy.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
REPO=m.ROOT;DATABASES=('socle','tiers','contrats','factures','tresorerie')
COMPONENTS=('socle-api','gateway','socle-front','tiers-front','contrats-front','factures-front','tresorerie-front','erp-shell')
SERVICES=tuple('wavy-'+x+'-recette' for x in COMPONENTS)
SCOPE='HTTPS_AUTH_ONLY_54_SOCLE_ROWS_8_EXISTING_SERVICES'
ORIGIN='https://recettelocal.wavyservices.fr'
R=None;P={};AUTH_MARKER=None
PROFILE=None
AUTHORIZATION_DOCUMENT='AUTORISATION-LOCALE.txt'
class Refused(ValueError):pass

def now():return datetime.now(timezone.utc).isoformat()
def emit(stage,**fields):print(json.dumps({'stage':stage,**fields}),flush=True)
def run(args,input=None,timeout=90,**kw):
 result=subprocess.run(args,input=input,capture_output=True,timeout=timeout,**kw)
 if result.returncode:raise Refused('COMMAND_REFUSED')
 return result.stdout

def save(path,data):
 path=Path(path);tmp=path.with_suffix('.new')
 fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 try:
  with os.fdopen(fd,'w') as f:json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
  os.replace(tmp,path)
 finally:tmp.unlink(missing_ok=True)
def state():return json.loads((R/'state.private.json').read_text()) if (R/'state.private.json').exists() else {}
def persist(s):save(R/'state.private.json',s)
def inspect(name):return json.loads(run(['docker','inspect',name]))[0]
def q(v):
 if v is None:return 'NULL'
 if isinstance(v,bool):return 'true' if v else 'false'
 if isinstance(v,(int,float)):return str(v)
 return "'"+str(v).replace("'","''")+"'"
def sql(db,text,write=False):
 if db not in DATABASES or write and db!='socle':raise Refused('SQL_SCOPE')
 body=('BEGIN; ' if write else 'BEGIN READ ONLY; ')+'SET LOCAL statement_timeout=30000; '+text+(' COMMIT;' if write else ' ROLLBACK;')
 return run(['docker','exec','-i',db+'-db-recette','sh','-c','exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'],input=body.encode(),timeout=45).decode().strip()

def baseline(db,ids=()):
 metadata=json.loads(sql(db,"SELECT json_object_agg(table_name,cols) FROM (SELECT table_name,json_agg(column_name) cols FROM information_schema.columns WHERE table_schema='public' GROUP BY table_name) t;"))
 answer={}
 for table,cols in metadata.items():
  if not re.fullmatch('[a-z_]+',table):raise Refused('TABLE_NAME')
  condition='true'
  if db=='socle' and ids:
   csv=','.join(map(str,ids))
   if table=='tenant':condition='t.id NOT IN ('+csv+')'
   elif 'tenant_id' in cols:condition='t.tenant_id NOT IN ('+csv+')'
  answer[table]=json.loads(sql(db,"SELECT json_build_object('count',count(*),'hash',md5(coalesce(string_agg(md5(row_to_json(t)::text),'' ORDER BY row_to_json(t)::text),''))) FROM public."+table+' t WHERE '+condition+';'))
 return answer

def compose(overlay=None):
 args=['docker','compose','-p','wavy-recette','--env-file',str(REPO/'.env.recette'),'--env-file',str(REPO/'versions/recette.env'),'-f',str(REPO/'docker-compose.recette.yml')]
 if overlay:args+=['-f',str(overlay)]
 return args

def private_file(path):
 info=Path(path).lstat()
 if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600:raise Refused('PRIVATE_FILE_REQUIRED')

def environment(items):return dict(v.split('=',1) for v in items)
def ports_bindings(obj):
 return sorted((key,p.get('HostIp') or '0.0.0.0',str(p['HostPort'])) for key,items in obj['HostConfig'].get('PortBindings',{}).items() for p in items or [])

def snapshot_guard(obj,base):
 if obj['State']['Running'] or obj['Config'].get('Labels',{}).get('com.docker.compose.project')!='wavy-recette':raise Refused('EXPECTED_STOPPED_EXISTING_SERVICE')
 image=json.loads(run(['docker','image','inspect',base['image']]))[0]
 if obj['Image']!=image['Id']:raise Refused('ORIGINAL_IMAGE_DIFFERS_FROM_ACTIVE_MANIFEST')
 expected=environment(image['Config'].get('Env',[]));expected.update({k:str(v).replace('$$','$') for k,v in base.get('environment',{}).items() if v is not None})
 if environment(obj['Config'].get('Env',[]))!=expected:raise Refused('ORIGINAL_ENVIRONMENT_NOT_REPRODUCIBLE')
 expected_ports=sorted((str(p['target'])+'/'+p.get('protocol','tcp'),p.get('host_ip') or '0.0.0.0',str(p['published'])) for p in base.get('ports',[]))
 if ports_bindings(obj)!=expected_ports:raise Refused('ORIGINAL_PORTS_NOT_REPRODUCIBLE')
 if obj.get('Mounts') or base.get('volumes'):raise Refused('UNREVIEWED_APPLICATION_MOUNT')
 if set(obj['NetworkSettings']['Networks'])!={'wavy-recette'}:raise Refused('FOREIGN_APPLICATION_NETWORK')

def caddy(args=(),data=None):
 return run(['curl.exe','--silent','--show-error','--fail-with-body','--max-time','12',*args],input=data,timeout=15)
def caddy_config():return json.loads(caddy(['http://127.0.0.1:2019/config/']))
def canonical(data):return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def adapted(data):
 result=json.loads(caddy(['--header','Content-Type: text/caddyfile','--data-binary','@-','http://127.0.0.1:2019/adapt'],data))
 if 'error' in result:raise Refused('CADDY_PARSE')
 return result['result']

def guard():
 if 'microsoft' not in Path('/proc/sys/kernel/osrelease').read_text().lower():raise Refused('MSI_WSL_ONLY')
 if os.environ.get('DOCKER_HOST') or os.environ.get('DOCKER_CONTEXT'):raise Refused('REMOTE_DOCKER_REFUSED')
 m.run(['docker','info','--format','{{.OSType}}'])
 for db in DATABASES:
  obj=inspect(db+'-db-recette')
  if not obj['State']['Running'] or obj['Config'].get('Labels',{}).get('com.docker.compose.project')!='wavy-recette':raise Refused('EXISTING_RECETTE_DB_REQUIRED')
 receipt=json.loads((R/'authorization.json').read_text());private_file(R/'authorization.json')
 if receipt.get('scope')!=SCOPE or receipt.get('approved') is not True or receipt.get('runDirectory')!=str(R):raise Refused('AUTHORIZATION_SCOPE')
 if receipt.get('authorizationDocumentSha256')!=m.digest(PTH/AUTHORIZATION_DOCUMENT):raise Refused('AUTHORIZATION_DOCUMENT_CHANGED')
 if receipt.get('planSha256')!=m.plan('recettelocal')['planSha256']:raise Refused('PLAN_CHANGED')
 version=run([receipt['caddyBinary'],'version']).decode().split()[0]
 if version!='v2.11.7':raise Refused('CADDY_VERSION')
 return receipt


def preflight():
 receipt=guard();s=state()
 if s:raise Refused('NEW_RUN_REQUIRED')
 baseline_render=json.loads(run(compose()+['config','--format','json']))
 snapshots={}
 for name in SERVICES:
  obj=inspect(name)
  if PROFILE:PROFILE.snapshot_guard(obj,baseline_render['services'][name],name)
  else:snapshot_guard(obj,baseline_render['services'][name])
  snapshots[name]=obj
 network=json.loads(run(['docker','network','inspect','wavy-recette']))[0]
 allowed=set(SERVICES)|{db+'-db-recette' for db in DATABASES}
 if PROFILE and getattr(PROFILE,'allowKnownNetworkMembers',False):
  allowed={ 'wavy-'+c+'-recette' for c in m.COMPONENTS }|{d+'-db-recette' for d in ('socle','tiers','contrats','factures','tresorerie')}
 if any(v['Name'] not in allowed for v in network.get('Containers',{}).values()):raise Refused('FOREIGN_NETWORK_MEMBER')
 subnet=network['IPAM']['Config'][0]['Subnet'];m.proxy_regex(subnet)
 source=Path('/mnt/c/Wavy/Caddy/Caddyfile').read_bytes();candidate=(PTH/'Caddyfile.local-only.candidate').read_bytes();marker=b'\n\nrecette.wavyservices.fr'
 if marker not in source or source.partition(marker)[2]!=candidate.partition(marker)[2]:raise Refused('NONLOCAL_CADDY_BLOCK_CHANGED')
 original=caddy_config()
 if canonical(adapted(source))!=canonical(original):raise Refused('CADDY_FILE_NOT_ACTIVE_CONFIG')
 target=adapted(candidate)
 (R/'Caddyfile.original').write_bytes(source);(R/'Caddyfile.original').chmod(0o600)
 save(R/'caddy-active.private.json',original);save(R/'snapshots.private.json',snapshots)
 inputs={str(p):m.digest(p) for p in [REPO/'.env.recette',REPO/'docker-compose.recette.yml',REPO/'versions/recette.env',REPO/'versions/recette.digests',*sorted((REPO/'versions/history/preprod').glob('*.tsv'))]}
 s={'runDirectory':str(R),'phase':'preflight','startedAt':now(),'authorizationScope':SCOPE,'counts':{'requests':0,'logins':0},'inputHashes':inputs,'caddyOriginalHash':canonical(original),'caddyCandidateHash':canonical(target),'caddyOriginalFileHash':hashlib.sha256(source).hexdigest(),'caddyCandidateFileHash':hashlib.sha256(candidate).hexdigest(),'subnet':subnet,'caddyVersion':'v2.11.7','baseline':{db:baseline(db) for db in DATABASES}}
 persist(s);emit('preflight',existingApplicationsStopped=len(SERVICES),existingDatabases=5,caddyVersion='2.11.7',nonlocalCaddyBlocksUnchanged=True)


def migration_check():
 # JAR exact du Socle EXISTANT ; aucun démarrage Spring ni Flyway migrate/repair.
 folder=R/'socle-crypto';folder.mkdir(mode=0o700,exist_ok=True)
 raw=run(['docker','cp','wavy-socle-api-recette:/app/app.jar','-'])
 with tarfile.open(fileobj=io.BytesIO(raw)) as t:jar=t.extractfile(next(x for x in t if x.isfile() and x.name.endswith('.jar'))).read()
 with zipfile.ZipFile(io.BytesIO(jar)) as z:
  for name in z.namelist():
   if name.startswith(('BOOT-INF/classes/','BOOT-INF/lib/')) and not name.endswith('/'):
    if '..' in Path(name).parts:raise Refused('JAR_PATH')
    target=folder/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(name))
 java=folder/'FlywayBeforeStartup.java'
 java.write_text('''import java.io.*;import java.sql.*;import org.flywaydb.core.Flyway;import org.flywaydb.core.api.MigrationState;
public class FlywayBeforeStartup{public static void main(String[]a)throws Exception{var b=new BufferedReader(new InputStreamReader(System.in));String url=b.readLine(),u=b.readLine(),p=b.readLine();try(var c=DriverManager.getConnection(url,u,p);var st=c.createStatement();var r=st.executeQuery("SHOW default_transaction_read_only")){if(!r.next()||!r.getString(1).equals("on"))throw new Exception();}var f=Flyway.configure().dataSource(url,u,p).locations("classpath:db/migration").baselineOnMigrate(false).cleanDisabled(true).outOfOrder(true).ignoreMigrationPatterns(new String[0]).load();if(!f.validateWithResult().validationSuccessful)throw new Exception();int n=0;for(var x:f.info().all()){if(x.getState()==MigrationState.BASELINE){if(!x.getVersion().toString().equals("0"))throw new Exception();}else{if(x.getState()!=MigrationState.SUCCESS&&x.getState()!=MigrationState.OUT_OF_ORDER)throw new Exception("UNEXPECTED_MIGRATION_STATE");n++;}}System.out.println("WAVY_READONLY_FLYWAY_OK "+n);}}
''')
 cp=str(folder/'BOOT-INF/classes')+':'+str(folder/'BOOT-INF/lib/*')
 run(['javac','--release','17','-cp',cp,'-d',str(folder),str(java)])
 db=inspect('socle-db-recette');env=environment(db['Config']['Env']);bindings=db['HostConfig']['PortBindings']['5432/tcp']
 if len(bindings)!=1:raise Refused('SOCLE_DATABASE_PORT')
 port=int(bindings[0]['HostPort']);url='jdbc:postgresql://127.0.0.1:'+str(port)+'/'+env['POSTGRES_DB']+'?options=-c%20default_transaction_read_only%3Don'
 out=run(['java','-cp',str(folder)+':'+cp,'FlywayBeforeStartup'],input=('\n'.join((url,env['POSTGRES_USER'],env['POSTGRES_PASSWORD']))+'\n').encode())
 match=re.search(rb'WAVY_READONLY_FLYWAY_OK (\d+)',out)
 if not match:raise Refused('FLYWAY_NO_SUCCESS')
 s=state();s['migrationCheck']={'jarSha256':hashlib.sha256(jar).hexdigest(),'migrations':int(match[1]),'readOnly':True,'pending':0};persist(s);emit('migrations',pending=0,readOnly=True,migrations=int(match[1]))


def backup(db='socle'):
 s=state()
 if db not in ('socle','tiers','factures') or (db!='socle' and not PROFILE):raise Refused('BACKUP_SCOPE')
 if db in s.get('backups',{}) or db=='socle' and s.get('backupComplete'):raise Refused('BACKUP_REPLAY')
 key=R/'backup-key.private'
 if db=='socle':key.write_text(secrets.token_hex(32)+'\n');key.chmod(0o600)
 else:private_file(key)
 dump=subprocess.Popen(['docker','exec',db+'-db-recette','sh','-c','exec pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 encrypted=R/(db+'.dump.enc')
 enc=subprocess.Popen(['openssl','enc','-aes-256-cbc','-salt','-pbkdf2','-pass','file:'+str(key),'-out',str(encrypted)],stdin=dump.stdout,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 dump.stdout.close();enc.communicate(timeout=90);dump.communicate(timeout=90)
 if dump.returncode or enc.returncode:raise Refused('BACKUP_FAILED')
 encrypted.chmod(0o600)
 mac=hmac.new(hashlib.sha256(key.read_bytes()+b'WAVY-MAC').digest(),encrypted.read_bytes(),hashlib.sha256).hexdigest()
 dec=subprocess.Popen(['openssl','enc','-d','-aes-256-cbc','-pbkdf2','-pass','file:'+str(key),'-in',str(encrypted)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 catalogue=subprocess.run(['docker','exec','-i',db+'-db-recette','pg_restore','--list'],stdin=dec.stdout,capture_output=True,timeout=60);dec.stdout.close();dec.communicate(timeout=60)
 if catalogue.returncode or dec.returncode:raise Refused('BACKUP_CATALOGUE')
 item={'sha256':m.digest(encrypted),'hmacSha256':mac,'catalogueChecked':True,'actualRestorePerformed':False}
 s.setdefault('backups',{})[db]=item
 s.update(backupComplete=True,phase='backed-up',backup=item);persist(s);emit('backup',database=db,encrypted=True,hmac=True,catalogueVerified=True)


def provision():
 s=state()
 if not s.get('backupComplete'):raise Refused('BACKUP_REQUIRED')
 if s.get('provisionComplete'):emit('provision',alreadyComplete=True);return
 if s.get('phase') not in ('backed-up','services-ready'):raise Refused('PROVISION_REPLAY_REFUSED')
 if {db:baseline(db) for db in DATABASES}!=s['baseline']:raise Refused('ORIGINAL_DATA_DRIFT_BEFORE_PROVISION')
 marker=AUTH_MARKER
 prefix='QA_PWA_'+marker.upper()
 roles=json.loads(sql('socle',"SELECT json_object_agg(code,id) FROM role WHERE code IN ('NOTE_DE_FRAIS','GESTIONNAIRE','SUPER_NOTE_DE_FRAIS');"))
 if len(roles)!=3:raise Refused('ROLE_CATALOGUE')
 # Use the existing password compatibility class from the pinned SOCLE artifact.
 raw=run(['docker','cp','wavy-socle-api-recette:/app/app.jar','-'])
 import zipfile
 with tarfile.open(fileobj=io.BytesIO(raw)) as t:
  member=next(m for m in t if m.isfile() and m.name.endswith('.jar'));jar=t.extractfile(member).read()
 folder=R/'socle-crypto';folder.mkdir(mode=0o700,exist_ok=True)
 with zipfile.ZipFile(io.BytesIO(jar)) as z:
  custom='BOOT-INF/classes/fr/wavy/socle_multitenant/configuration/MotDePasseCompatiblePasswordEncoder.class'
  if custom not in z.namelist():raise Refused('PASSWORD_ENCODER_NOT_REVIEWED')
  for name in z.namelist():
   if name.startswith(('BOOT-INF/classes/','BOOT-INF/lib/')) and not name.endswith('/'):
    target=folder/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(name))
 java=folder/'Encode.java';java.write_text('''public class Encode {public static void main(String[] a)throws Exception {var b=new java.io.BufferedReader(new java.io.InputStreamReader(System.in));var e=new fr.wavy.socle_multitenant.configuration.MotDePasseCompatiblePasswordEncoder();for(String p;(p=b.readLine())!=null;) {String h=e.encode(p);if(!e.matches(p,h))throw new Exception();System.out.println(h);}}}''')
 cp=str(folder/'BOOT-INF/classes')+':'+str(folder/'BOOT-INF/lib/*')
 run(['javac','--release','17','-cp',cp,'-d',str(folder),str(java)])
 actors=P['actors'];users={}
 for actor in actors:
  alias=actor['alias'];users[alias]={'password':secrets.token_urlsafe(32),'email':'qa.pwa.'+marker+'.'+alias.lower()+'@example.invalid','tenantAlias':actor['tenant'],'companies':actor['companies'],'roles':actor['roles']}
 hashes=run(['java','-cp',str(folder)+':'+cp,'Encode'],input=('\n'.join(u['password'] for u in users.values())+'\n').encode()).decode().splitlines()
 if len(hashes)!=8 or not all(h.startswith(('$2','{bcrypt}')) for h in hashes):raise Refused('HASH_ENCODING')
 if sql('socle',"SELECT count(*) FROM tenant WHERE code IN ("+q(prefix+'_A')+','+q(prefix+'_B')+');')!='0':raise Refused('NAMESPACE_EXISTS')
 s.update(prefix=prefix,users=users,phase='provisioning');persist(s)
 # One SQL statement, all 54 business rows committed atomically. Never update old data.
 ctes=[]
 def ins(label,table,fields,expressions):ctes.append(label+' AS (INSERT INTO '+table+' ('+','.join(fields)+') VALUES ('+','.join(expressions)+') RETURNING id)')
 for tenant in ('A','B'):
  ins('t'+tenant,'tenant',['code','nom','statut','base_dediee','date_creation','date_modification'],[q(prefix+'_'+tenant),q('QA PWA TEST '+tenant),q('ACTIF'),'false','now()','now()'])
 for i,company in enumerate(('A1','A2','B1','B2')):
  siren='000'+str(secrets.randbelow(1000000)).zfill(6)
  if sql('socle',"SELECT count(*) FROM societe_interne WHERE numero_siren="+q(siren)+';')!='0':raise Refused('SYNTHETIC_COMPANY_COLLISION')
  ins('c'+company,'societe_interne',['tenant_id','raison_sociale','numero_siren','actif','date_creation','date_modification'],['(SELECT id FROM t'+company[0]+')',q(prefix+' '+company),q(siren),'true','now()','now()'])
 for i,(alias,u) in enumerate(users.items()):
  ins('u'+str(i),'utilisateur',['tenant_id','nom','prenom','email','mot_de_passe_hash','actif','mot_de_passe_a_changer','date_creation','date_modification'],['(SELECT id FROM t'+u['tenantAlias']+')',q('TEST SYNTHETIQUE'),q(alias),q(u['email']),q(hashes[i]),'true','false','now()','now()'])
 role_values=[];company_values=[];counter_values=[]
 for i,(alias,u) in enumerate(users.items()):
  tid='(SELECT id FROM t'+u['tenantAlias']+')';uid='(SELECT id FROM u'+str(i)+')'
  for role in u['roles']:role_values.append('('+','.join([tid,uid,str(roles[role]),'now()','now()'])+')')
  for j,company in enumerate(u['companies']):company_values.append('('+','.join([tid,uid,'(SELECT id FROM c'+company+')','true',q(j==0),'now()','now()'])+')')
 for company in ('A1','A2','B1','B2'):
  for mod,obj,pref in [('FACTURES','FACTURE_VENTE','FAC'),('CONTRATS','CONTRAT_CLIENT','CC'),('CONTRATS','CONTRAT_FOURNISSEUR','CF')]:
   counter_values.append('('+','.join(['(SELECT id FROM t'+company[0]+')','(SELECT id FROM c'+company+')',q(mod),q(obj),q('QA PWA TEST'),q(pref)])+')')
 ctes.append('roles_added AS (INSERT INTO utilisateur_role (tenant_id,utilisateur_id,role_id,date_creation,date_modification) VALUES '+','.join(role_values)+' RETURNING id)')
 ctes.append('companies_added AS (INSERT INTO utilisateur_societe (tenant_id,utilisateur_id,societe_interne_id,actif,societe_principale,date_creation,date_modification) VALUES '+','.join(company_values)+' RETURNING id)')
 ctes.append('counters_added AS (INSERT INTO compteur (tenant_id,societe_interne_id,module_code,objet_code,libelle,prefixe) VALUES '+','.join(counter_values)+' RETURNING id)')
 final="SELECT json_build_object('tenants',json_build_object('A',(SELECT id FROM tA),'B',(SELECT id FROM tB)),'companies',json_build_object("+','.join(q(c)+',(SELECT id FROM c'+c+')' for c in ('A1','A2','B1','B2'))+"),'users',json_build_object("+','.join(q(alias)+',(SELECT id FROM u'+str(i)+')' for i,alias in enumerate(users))+"),'rolesAdded',(SELECT count(*) FROM roles_added),'companiesAdded',(SELECT count(*) FROM companies_added),'countersAdded',(SELECT count(*) FROM counters_added));"
 answer=json.loads(sql('socle','WITH '+','.join(ctes)+' '+final,True))
 for alias,uid in answer['users'].items():s['users'][alias]['id']=uid;s['users'][alias]['tenant']=answer['tenants'][s['users'][alias]['tenantAlias']]
 s.update(tenants=answer['tenants'],companies=answer['companies'],roleIds=roles,provisionComplete=True,phase='provisioned');persist(s)
 emit('provision',tenants=2,companies=4,accounts=8,rows=54)


def escaped(value):
 if isinstance(value,str):return value.replace('$','$$')
 if isinstance(value,list):return [escaped(v) for v in value]
 if isinstance(value,dict):return {k:escaped(v) for k,v in value.items()}
 return value

def prepare_runtime():
 s=state();output=R/'runtime';m.render('recettelocal',output,s['subnet'])
 rendered=json.loads(run(compose(output/'compose.https.yml')+['config','--format','json']))
 if any(rendered['services'][name].get('ports') for name in SERVICES if name!='wavy-erp-shell-recette'):raise Refused('API_PORT_EXPOSED')
 port=rendered['services']['wavy-erp-shell-recette']['ports']
 if len(port)!=1 or port[0].get('host_ip')!='127.0.0.1':raise Refused('SHELL_LOOPBACK_REQUIRED')
 source=json.loads(run(compose()+['config','--format','json']))
 snapshots=json.loads((R/'snapshots.private.json').read_text())
 original_refs={}
 for name,obj in snapshots.items():
  image=json.loads(run(['docker','image','inspect',obj['Image']]))[0]
  prefix='ghcr.io/fabffo/'+name.removesuffix('-recette')+'@sha256:'
  ref=next((r for r in image.get('RepoDigests',[]) if r.startswith(prefix)),None)
  if not ref:raise Refused('ORIGINAL_DIGEST_REQUIRED')
  original_refs[name]=ref;source['services'][name]['image']=ref
 save(R/'original-runtime.private.json',source)
 s.update(originalReferences=original_refs,runtimePrepared=True);persist(s)


def start():
 s=state()
 if not s.get('backupComplete') or not s.get('runtimePrepared'):raise Refused('SETUP_REQUIRED')
 # Intent before Docker, so interruption never loses ownership of a partial start.
 s.update(servicesAttempted=True,phase='starting');persist(s)
 cmd=compose(R/'runtime/compose.https.yml')
 for name in SERVICES:
  run(cmd+['up','-d','--no-deps','--no-build','--pull','never','--force-recreate',name],timeout=120)
 for name in SERVICES:
  for attempt in range(60):
   obj=inspect(name);health=obj['State'].get('Health',{}).get('Status')
   if health=='healthy':break
   if health=='unhealthy' or not obj['State']['Running']:raise Refused('SERVICE_HEALTH_FAILED')
   time.sleep(1)
  else:raise Refused('HEALTH_TIMEOUT_'+name)
  component=name.removeprefix('wavy-').removesuffix('-recette');expected=m.plan('recettelocal')['images'][component]
  if obj['Image']!=json.loads(run(['docker','image','inspect',expected]))[0]['Id']:raise Refused('RUNTIME_IMAGE_MISMATCH')
 s.update(phase='services-ready',servicesReady=True);persist(s);emit('services',healthy=len(SERVICES),buildOrPull=False)


def atomic_bytes(path,content):
 tmp=path.with_name(path.name+'.wavy-'+AUTH_MARKER)
 fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 try:
  with os.fdopen(fd,'wb') as f:f.write(content);f.flush();os.fsync(f.fileno())
  os.replace(tmp,path)
 finally:tmp.unlink(missing_ok=True)


def activate_caddy():
 s=state()
 if not s.get('servicesReady'):raise Refused('SERVICES_NOT_READY')
 if canonical(caddy_config())!=s['caddyOriginalHash']:raise Refused('CADDY_CHANGED_BY_ANOTHER_OPERATOR')
 file=Path('/mnt/c/Wavy/Caddy/Caddyfile');candidate=(PTH/'Caddyfile.local-only.candidate').read_bytes()
 if hashlib.sha256(file.read_bytes()).hexdigest()!=s['caddyOriginalFileHash'] or hashlib.sha256(candidate).hexdigest()!=s['caddyCandidateFileHash']:raise Refused('CADDY_FILE_CHANGED')
 config=adapted(candidate)
 s.update(caddyAttempted=True,phase='caddy-switching');persist(s)
 atomic_bytes(file,candidate)
 caddy(['--header','Content-Type: application/json','--data-binary','@-','http://127.0.0.1:2019/load'],json.dumps(config).encode())
 if canonical(caddy_config())!=s['caddyCandidateHash']:raise Refused('CADDY_ACTIVATION_FAILED')
 s.update(caddyActive=True,phase='testing');persist(s);emit('https',localProxyActive=True,nonlocalCaddyBlocksUnchanged=True)


class Client:
 def __init__(self):self.sessions=[];self.results=[]
 def request(self,method,path,session=None,data=None,headers=None,origin=ORIGIN):
  if not path.startswith('/') or '\r' in path or '\n' in path:raise Refused('HTTP_PATH')
  s=state();s['counts']['requests']+=1
  if s['counts']['requests']>500:raise Refused('REQUEST_BUDGET')
  persist(s)
  def opt(name,value):return name+' = '+json.dumps(value)+'\n'
  config=opt('url',ORIGIN+path)+opt('resolve','recettelocal.wavyservices.fr:443:127.0.0.1')+opt('request',method)+opt('dump-header','-')+opt('output','-')
  h={'Accept':'application/json'}
  if origin:h['Origin']=origin
  if session:h['Cookie']=session['cookie']
  if headers:h.update(headers)
  if data is not None:h['Content-Type']='application/json';config+=opt('data-binary',json.dumps(data))
  for key,value in h.items():
   if '\n' in value or '\r' in value:raise Refused('HEADER_CONTROL_CHAR')
   config+=opt('header',key+': '+value)
  raw=run(['curl.exe','--silent','--show-error','--ssl-revoke-best-effort','--max-time','15','--config','-'],input=config.encode(),timeout=20)
  while True:
   block,sep,body=raw.partition(b'\r\n\r\n')
   if not sep:raise Refused('HTTPS_RESPONSE_HEADER')
   lines=block.decode(errors='replace').splitlines();status=int(lines[0].split()[1])
   if status>=200:break
   raw=body
  pairs=[line.split(':',1) for line in lines[1:] if ':' in line];hs={}
  for key,value in pairs:hs.setdefault(key.lower(),[]).append(value.strip())
  try:payload=json.loads(body)
  except Exception:payload=None
  return {'status':status,'json':payload,'headers':hs,'body':body,'bodyHash':hashlib.sha256(body).hexdigest()}
 def check(self,label,condition):
  self.results.append({'control':label,'passed':bool(condition)})
  save(R/'http-results.json',{'checks':self.results,'realGatewayAndSocle':True,'https':True})
  if not condition:raise Refused('AUTH_ASSERTION_'+label)
 def login(self,alias,headers=None):
  s=state();s['counts']['logins']+=1
  if s['counts']['logins']>100:raise Refused('LOGIN_BUDGET')
  persist(s);u=s['users'][alias]
  r=self.request('POST','/api/auth/session',data={'email':u['email'],'motDePasse':u['password']},headers=headers)
  self.check('login-status',r['status']==200)
  d=r['json'];self.check('canonical-session-identity',d.get('utilisateurId')==u['id'] and d.get('tenantId')==u['tenant'])
  jar=SimpleCookie()
  for line in r['headers'].get('set-cookie',[]):jar.load(line)
  self.check('cookie-present','WAVY_SESSION' in jar)
  cookie=jar['WAVY_SESSION']
  self.check('cookie-Secure-HttpOnly-Strict',bool(cookie['secure']) and bool(cookie['httponly']) and cookie['samesite'].lower()=='strict')
  self.check('cookie-host-only-path-age',cookie['domain']=='' and cookie['path']=='/' and cookie['max-age']=='1800')
  session={'cookie':'WAVY_SESSION='+cookie.value,'alias':alias,'companyId':d['societeCouranteId']};self.sessions.append(session)
  return session
 def identity(self,session,expected_company=None,headers=None):
  r=self.request('GET','/api/auth/session',session,headers=headers);u=state()['users'][session['alias']]
  self.check('session-read-authenticated',r['status']==200)
  d=r['json'];self.check('session-context-isolated',d.get('utilisateurId')==u['id'] and d.get('tenantId')==u['tenant'] and d.get('societeCouranteId')==(expected_company or session['companyId']))
  return d
 def switch(self,session,company,allowed):
  target=state()['companies'][company];r=self.request('POST','/api/auth/session/societe',session,data={'societeInterneId':target})
  if allowed:
   self.check('authorized-company-switch',r['status']==200 and r['json'].get('societeCouranteId')==target);session['companyId']=target
  else:self.check('unauthorized-company-switch-refused',r['status'] in (403,404))
  self.identity(session)
 def tests(self):
  for method,path in [('GET','/'),*[('GET','/modules/'+module+'/') for module in ('socle','tiers','contrats','factures','tresorerie')]]:
   r=self.request(method,path);self.check('erp-html-'+path,r['status']==200 and b'<html' in r['body'].lower())
  for path in ('/pwa','/pwa/','/api/pwa','/api/pwa/'):
   self.check('pwa-closed-'+path,self.request('GET',path)['status']==404)
  self.check('unauthenticated-session-refused',self.request('GET','/api/auth/session')['status']==401)
  for source,expect in ((ORIGIN,200),('https://preprod.wavyservices.fr',403),('https://untrusted.invalid',403)):
   r=self.request('OPTIONS','/api/auth/session',headers={'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'content-type'},origin=source)
   self.check('cors-preflight',r['status']==expect)
   if expect==200:self.check('cors-exact-with-credentials',r['headers'].get('access-control-allow-origin')==[ORIGIN] and r['headers'].get('access-control-allow-credentials')==['true'])
  # No credential data in these requests; the edge must reject before Socle.
  for source in (None,'https://untrusted.invalid','http://recettelocal.wavyservices.fr'):
   self.check('csrf-Origin-required',self.request('POST','/api/auth/session',data={},origin=source)['status']==403)
  sessions={}
  for alias,u in state()['users'].items():
   session=self.login(alias);sessions[alias]=session;self.identity(session)
  self.switch(sessions['A-owner'],'A2',True);self.switch(sessions['A-owner'],'A1',True)
  self.switch(sessions['B-owner'],'B2',True);self.switch(sessions['B-owner'],'B1',True)
  self.switch(sessions['A-peer'],'A2',False);self.switch(sessions['B-peer'],'B2',False)
  self.switch(sessions['A-owner'],'B1',False);self.switch(sessions['B-owner'],'A1',False)
  self.identity(sessions['A-owner'],headers={'X-Tenant-Id':str(state()['tenants']['B']),'X-Utilisateur-Id':str(state()['users']['B-owner']['id']),'X-Societe-Courante-Id':str(state()['companies']['B1']),'X-Wavy-Roles':'ADMIN_PLATEFORME'})
  forged=self.login('A-owner',headers={'X-Forwarded-Proto':'http','X-Forwarded-Host':'untrusted.invalid','Forwarded':'proto=http;host=untrusted.invalid','X-Forwarded-For':'192.0.2.99'})
  self.identity(forged)
  for session in self.sessions:
   r=self.request('DELETE','/api/auth/session',session)
   self.check('real-logout',r['status'] in (200,204))
   expired=SimpleCookie()
   for line in r['headers'].get('set-cookie',[]):expired.load(line)
   self.check('logout-cookie-cleared-secure', 'WAVY_SESSION' in expired and expired['WAVY_SESSION']['max-age']=='0' and bool(expired['WAVY_SESSION']['secure']) and bool(expired['WAVY_SESSION']['httponly']))
   self.check('logout-replay-refused',self.request('GET','/api/auth/session',session)['status']==401)
  s=state();s.update(httpPassed=True,phase='tested',httpChecks=len(self.results));persist(s);emit('tests',passed=len(self.results),failed=0,realAccounts=8,requestCount=s['counts']['requests'],loginCount=s['counts']['logins'])

def restore_caddy():
 s=state()
 if not s.get('caddyAttempted'):return
 if s.get('caddyRestored'):
  if canonical(caddy_config())!=s['caddyOriginalHash']:raise Refused('CADDY_RESTORE_DRIFT')
  return
 current=canonical(caddy_config())
 if current not in (s['caddyOriginalHash'],s['caddyCandidateHash']):raise Refused('CADDY_OWNERSHIP_CHANGED')
 file=Path('/mnt/c/Wavy/Caddy/Caddyfile');fh=hashlib.sha256(file.read_bytes()).hexdigest()
 if fh not in (s['caddyOriginalFileHash'],s['caddyCandidateFileHash']):raise Refused('CADDY_SOURCE_OWNERSHIP_CHANGED')
 original=json.loads((R/'caddy-active.private.json').read_text())
 if current!=s['caddyOriginalHash']:caddy(['--header','Content-Type: application/json','--data-binary','@-','http://127.0.0.1:2019/load'],json.dumps(original).encode())
 atomic_bytes(file,(R/'Caddyfile.original').read_bytes())
 if canonical(caddy_config())!=s['caddyOriginalHash'] or hashlib.sha256(file.read_bytes()).hexdigest()!=s['caddyOriginalFileHash']:raise Refused('CADDY_RESTORE_FAILED')
 s.update(caddyRestored=True,caddyActive=False);persist(s)


def cleanup_data():
 if PROFILE:return PROFILE.cleanup_data()
 s=state()
 if s.get('dataCleaned'):return
 ids=[]
 if s.get('prefix'):
  codes=[s['prefix']+'_'+a for a in ('A','B')]
  ids=json.loads(sql('socle',"SELECT coalesce(json_agg(id),'[]'::json) FROM tenant WHERE code IN ("+','.join(map(q,codes))+');'))
 if ids and len(ids)!=2:raise Refused('SYNTHETIC_TENANT_OWNERSHIP')
 before={db:baseline(db,ids) for db in DATABASES}
 if before!=s['baseline']:raise Refused('ORIGINAL_DATA_DRIFT_BEFORE_CLEANUP')
 if ids:
  csv=','.join(map(str,ids));expected_emails=[u['email'] for u in s['users'].values()]
  users=json.loads(sql('socle',"SELECT coalesce(json_agg(email),'[]'::json) FROM utilisateur WHERE tenant_id IN ("+csv+');'))
  if sorted(users)!=sorted(expected_emails):raise Refused('SYNTHETIC_USER_OWNERSHIP')
  counts=json.loads(sql('socle',"SELECT json_build_object('tenants',(SELECT count(*) FROM tenant WHERE id IN ("+csv+")),'companies',(SELECT count(*) FROM societe_interne WHERE tenant_id IN ("+csv+")),'users',(SELECT count(*) FROM utilisateur WHERE tenant_id IN ("+csv+")),'roles',(SELECT count(*) FROM utilisateur_role WHERE tenant_id IN ("+csv+")),'allocations',(SELECT count(*) FROM utilisateur_societe WHERE tenant_id IN ("+csv+")),'counters',(SELECT count(*) FROM compteur WHERE tenant_id IN ("+csv+")));") )
  if counts!={'tenants':2,'companies':4,'users':8,'roles':16,'allocations':12,'counters':12}:raise Refused('FIXTURE_ROW_COUNT_DRIFT')
  statements=''.join('DELETE FROM '+table+' WHERE tenant_id IN ('+csv+');' for table in ('utilisateur_role','utilisateur_societe','compteur','utilisateur'))
  statements+='DELETE FROM societe_interne WHERE tenant_id IN ('+csv+');DELETE FROM tenant WHERE id IN ('+csv+');'
  sql('socle',statements,True)
 after={db:baseline(db) for db in DATABASES}
 if after!=s['baseline']:raise Refused('ORIGINAL_DATA_DRIFT_AFTER_CLEANUP')
 s.update(dataCleaned=True,originalRowsMatch=True,cleanedRows=54 if ids else 0,checkedTables=sum(len(tables) for tables in after.values()));persist(s)
 emit('cleanup',syntheticRowsRemoved=s['cleanedRows'],originalTablesMatch=s['checkedTables'],nonSocleDatabasesUnchanged=True)


def restore_services():
 s=state()
 if not s.get('servicesAttempted') or s.get('servicesRestored'):return
 if not s.get('dataCleaned'):raise Refused('NO_ORIGINAL_WRITER_RESTORE_UNTIL_CLEAN')
 run(['docker','compose','-p','wavy-recette','-f',str(R/'original-runtime.private.json'),'up','--no-start','--no-deps','--no-build','--pull','never','--force-recreate',*SERVICES],timeout=150)
 originals=json.loads((R/'snapshots.private.json').read_text())
 for name,old in originals.items():
  current=inspect(name)
  if current['State']['Running'] or current['Image']!=old['Image']:raise Refused('ORIGINAL_IMAGE_RESTORE_FAILED')
  for field in ('Env','Cmd','Entrypoint','Healthcheck','User','WorkingDir'):
   first=current['Config'].get(field);second=old['Config'].get(field)
   if field=='Env':first=sorted(first or []);second=sorted(second or [])
   if first!=second:raise Refused('ORIGINAL_CONFIG_RESTORE_FAILED_'+field)
  if ports_bindings(current)!=ports_bindings(old) or current.get('Mounts')!=old.get('Mounts') or set(current['NetworkSettings']['Networks'])!=set(old['NetworkSettings']['Networks']):raise Refused('ORIGINAL_HOSTCONFIG_RESTORE_FAILED')
 s.update(servicesRestored=True,servicesStopped=True);persist(s);emit('restore',originalImagesAndConfigurations=True,applicationsStopped=len(SERVICES))


def archive_sensitive():
 key=R/'backup-key.private'
 names=['state.private.json','snapshots.private.json','original-runtime.private.json','caddy-active.private.json']
 if PROFILE:names+= [str(p.relative_to(R)) for p in R.rglob('*.private.json') if str(p.relative_to(R)) not in names]
 for name in names:
  path=R/name
  if not path.exists():continue
  run(['openssl','enc','-aes-256-cbc','-salt','-pbkdf2','-pass','file:'+str(key),'-in',str(path),'-out',str(path)+'.enc'])
  Path(str(path)+'.enc').chmod(0o600)
  if name!='state.private.json':path.unlink()
 s=state();s.pop('users',None);s.pop('tenants',None);s.pop('companies',None);s.pop('roleIds',None);persist(s)


def cleanup():
 s=state()
 if not s or s.get('cleanupComplete'):return
 errors=[]
 if PROFILE:
  try:PROFILE.close_gate()
  except BaseException as e:errors.append(str(e) if isinstance(e,Refused) else type(e).__name__)
 writers_stopped=not s.get('servicesAttempted')
 def stop_writers():
  nonlocal writers_stopped
  if not state().get('servicesAttempted'):return
  run(['docker','stop',*SERVICES],timeout=100)
  if any(inspect(name)['State']['Running'] for name in SERVICES):raise Refused('WRITER_STILL_RUNNING')
  writers_stopped=True
 for action in (restore_caddy,stop_writers):
  try:action()
  except BaseException as e:errors.append(str(e) if isinstance(e,Refused) else type(e).__name__)
 # Never delete fixtures or recreate containers while a writer may still run.
 if writers_stopped:
  try:cleanup_data()
  except BaseException as e:errors.append(str(e) if isinstance(e,Refused) else type(e).__name__)
 if writers_stopped and state().get('dataCleaned'):
  try:restore_services()
  except BaseException as e:errors.append(str(e) if isinstance(e,Refused) else type(e).__name__)
 s=state()
 if errors:
  s.update(phase='recovery-required',cleanupErrors=errors);persist(s);raise Refused('CLEANUP_INCOMPLETE_OWNER_RESERVATION_RETAINED')
 for path,sha in s['inputHashes'].items():
  if m.digest(Path(path))!=sha:raise Refused('ACTIVE_INPUT_CHANGED')
 s.update(phase='restored-stopped',finishedAt=now());persist(s)
 if s.get('backupComplete'):archive_sensitive()
 s=state();s['cleanupComplete']=True;persist(s)


def execute(run_dir,authorization,recover=False,functional=False):
 global R,P,AUTH_MARKER,PROFILE,SCOPE,SERVICES,COMPONENTS,AUTHORIZATION_DOCUMENT,DATABASES
 if (Path(run_dir)/'state.private.json').exists() and json.loads((Path(run_dir)/'state.private.json').read_text()).get('permanentLocal'):raise Refused('Session convertie en environnement permanent : utiliser ./wavy local down ; aucune restauration historique automatique')
 if functional:
  fspec=importlib.util.spec_from_file_location('local_functional',PTH/'local_functional.py')
  fm=importlib.util.module_from_spec(fspec);fspec.loader.exec_module(fm)
  klass=fm.ModuleCampaign if functional=='cycle' else (fm.ManualCampaign if functional=='manual' else (fm.AnonymousCampaign if functional=='anonymous' else fm.Campaign))
  PROFILE=klass(sys.modules[__name__])
  SCOPE=PROFILE.scope;AUTHORIZATION_DOCUMENT=getattr(PROFILE,'authorization_document','AUTORISATION-FONCTIONNELLE.txt')
  COMPONENTS=tuple(getattr(PROFILE,'components',m.COMPONENTS));SERVICES=tuple('wavy-'+x+'-recette' for x in COMPONENTS)
  if functional=='cycle':DATABASES=PROFILE.databases
 def interrupted(signum,frame):raise InterruptedError('LOCAL_PHASE_INTERRUPTED')
 signal.signal(signal.SIGTERM,interrupted)
 R=Path(run_dir).absolute()
 if R.resolve()!=R or R.is_relative_to(REPO) or R.is_symlink():raise Refused('PRIVATE_RUN_PATH')
 info=R.lstat()
 if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:raise Refused('PRIVATE_RUN_DIRECTORY')
 if Path(authorization).absolute()!=R/'authorization.json':raise Refused('CANONICAL_AUTHORIZATION_PATH')
 if recover and PROFILE and state().get('managedComponents') and not state().get('cleanupComplete'):
  managed=state()['managedComponents']
  if not set(managed).issubset(m.COMPONENTS):raise Refused('MANAGED_COMPONENT_SCOPE')
  saved=json.loads((R/'snapshots.private.json').read_text())
  if set(saved)!={'wavy-'+c+'-recette' for c in managed}:raise Refused('MANAGED_SNAPSHOT_SCOPE')
  COMPONENTS=tuple(managed);SERVICES=tuple('wavy-'+c+'-recette' for c in COMPONENTS)
 receipt=guard();AUTH_MARKER=receipt.get('fixtureMarker','')
 if not re.fullmatch('[a-f0-9]{12}',AUTH_MARKER):raise Refused('FIXTURE_MARKER')
 P={'actors':json.loads((REPO/'preparation/pwa-notes-frais/private-shell/PLAN-MUTATIONS-RECETTE.json').read_text())['actors']}
 (REPO/'deployments').mkdir(exist_ok=True)
 lock=REPO/'deployments/recette.lock';fd=os.open(lock,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
 reservation=REPO/'deployments/recette-https-reservation.json'
 try:
  fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
  if reservation.exists():
   private_file(reservation);owner=json.loads(reservation.read_text())
   if not recover or owner.get('runDirectory')!=str(R) or owner.get('scope')!=SCOPE:raise Refused('LOCAL_RESERVATION_CONFLICT')
  else:
   if recover:raise Refused('NO_RESERVATION_TO_RECOVER')
   if (R/'state.private.json').exists():raise Refused('EXISTING_RUN_CANNOT_REPLAY')
   save(reservation,{'scope':SCOPE,'runDirectory':str(R),'startedAt':now()})
  failure=None
  try:
   if recover:cleanup()
   else:
    preflight()
    if PROFILE:PROFILE.execute()
    else:migration_check();backup();prepare_runtime();start();provision();activate_caddy();Client().tests()
  except BaseException as error:
   failure=str(error) if isinstance(error,Refused) else type(error).__name__
   emit('phase-failure',reason=failure)
  finally:
   if functional in ('manual','cycle') and not recover:
    # Explicit persistent handoff: no teardown, timer or automatic recovery.
    s=state()
    if s:s.update(keepOpen=True,autoCleanup=False,phase='manual-ready' if not failure else 'manual-open-failed');persist(s)
   else:
    try:cleanup()
    except BaseException as error:
     emit('cleanup-failure',reason=str(error) if isinstance(error,Refused) else type(error).__name__)
     failure=failure or 'CLEANUP_FAILED'
  s=state()
  if s.get('cleanupComplete'):
   reservation.unlink()
  elif not s:
   # No preflight snapshot persisted, therefore absolutely no mutation attempted.
   reservation.unlink()
  result={'scope':SCOPE,'passed':bool(s.get('httpPassed')) and bool(s.get('cleanupComplete')) and failure is None,'failure':failure,'realHttpChecks':s.get('httpChecks',0),'counts':s.get('counts',{}),'cleanedRows':s.get('cleanedRows',0),'checkedOriginalTables':s.get('checkedTables',0),'originalRowsMatch':s.get('originalRowsMatch',False),'servicesRestored':s.get('servicesRestored',False),'caddyRestored':s.get('caddyRestored',False),'cleanupComplete':s.get('cleanupComplete',False),'vmAccess':False,'migrationApplied':False,'preprodAttestations':{k:False for k in ('rollback-schema-compatible','session-isolation-plan','isolated-restore-capacity')}}
  if functional in ('manual','cycle'):
   if not recover:result.update(passed=bool(s.get('httpPassed')) and failure is None,environmentLeftRunning=True,autoCleanup=False,reservationRetained=reservation.exists())
   else:
    stopped=all(not inspect(name)['State']['Running'] for name in SERVICES)
    s['keepOpen']=not stopped;persist(s);result.update(environmentLeftRunning=not stopped,autoCleanup=False,reservationRetained=reservation.exists())
  save(R/'result.json',result)
  return result
 finally:os.close(fd)
