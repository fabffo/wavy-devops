#!/usr/bin/env python3
"""Read-only Flyway/JPA preconditions for the approved local functional campaign.

Reuses local_auth's local Docker guard, SQL fingerprints and private evidence I/O.
Never starts Spring or migrates a database. The artifact container is never started.
"""
import importlib.util
import io
import json
from pathlib import Path
import re
import sys
import tarfile
import zipfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('local_auth', HERE / 'local_auth.py')
a = importlib.util.module_from_spec(spec); spec.loader.exec_module(a)

JAVA = r'''import java.io.*;import java.nio.file.*;import java.sql.*;import java.util.*;
import jakarta.persistence.*;import org.flywaydb.core.Flyway;import org.flywaydb.core.api.MigrationState;
import org.hibernate.boot.MetadataSources;import org.hibernate.boot.registry.StandardServiceRegistryBuilder;
public class FunctionalReadOnly {
 public static void main(String[]args)throws Exception {
  var b=new BufferedReader(new InputStreamReader(System.in));String url=b.readLine(),u=b.readLine(),p=b.readLine();
  try(var c=DriverManager.getConnection(url,u,p);var st=c.createStatement();var rs=st.executeQuery("SHOW default_transaction_read_only")) {
   if(!rs.next()||!rs.getString(1).equals("on"))throw new Exception("NOT_READONLY");
  }
  var f=Flyway.configure().dataSource(url,u,p).locations(args[1].split(","))
   .baselineOnMigrate(false).cleanDisabled(true).outOfOrder(args[2].equals("true"))
   .ignoreMigrationPatterns(new String[0]).load();
  var validation=f.validateWithResult();int n=0;var bad=new ArrayList<String>();
  for(var x:f.info().all()) {
   if(x.getState()==MigrationState.BASELINE) {if(!x.getVersion().toString().equals("0"))bad.add("BASELINE");}
   else if(x.getState()!=MigrationState.SUCCESS&&x.getState()!=MigrationState.OUT_OF_ORDER)bad.add(x.getVersion()+":"+x.getState());
   else n++;
  }
  System.out.println("WAVY_FLYWAY migrations="+n+" valid="+validation.validationSuccessful+" unexpected="+String.join(",",bad));
  if(!validation.validationSuccessful||!bad.isEmpty())System.exit(2);
  var builder=new StandardServiceRegistryBuilder().applySetting("hibernate.connection.url",url)
   .applySetting("hibernate.connection.username",u).applySetting("hibernate.connection.password",p)
   .applySetting("hibernate.connection.driver_class","org.postgresql.Driver")
   .applySetting("hibernate.hbm2ddl.auto","validate").applySetting("hibernate.default_schema","public")
   .applySetting("hibernate.show_sql","false").applySetting("hibernate.jdbc.time_zone","UTC")
   .applySetting("hibernate.physical_naming_strategy","org.hibernate.boot.model.naming.PhysicalNamingStrategySnakeCaseImpl")
   .applySetting("hibernate.implicit_naming_strategy","org.springframework.boot.hibernate.SpringImplicitNamingStrategy");
  var registry=builder.build();int entities=0;
  try {var sources=new MetadataSources(registry);var converters=new ArrayList<Class<?>>();Path root=Path.of(args[0]);
   try(var files=Files.walk(root.resolve("fr/wavy"))) {
    for(var file:files.filter(pth->pth.toString().endsWith(".class")).sorted().toList()) {
     var name=root.relativize(file).toString().replace('/','.').replaceAll("\\.class$","");
     Class<?> cls=Class.forName(name,false,FunctionalReadOnly.class.getClassLoader());
     if(cls.isAnnotationPresent(Entity.class)||cls.isAnnotationPresent(Embeddable.class)||cls.isAnnotationPresent(MappedSuperclass.class)) {
      sources.addAnnotatedClass(cls);if(cls.isAnnotationPresent(Entity.class))entities++;
     }
     if(cls.isAnnotationPresent(Converter.class))converters.add(cls);
    }
   }
   var metadata=sources.getMetadataBuilder();for(var cls:converters)metadata.applyAttributeConverter((Class)cls,cls.getAnnotation(Converter.class).autoApply());
   try(var factory=metadata.build().buildSessionFactory()){if(!factory.isOpen())throw new Exception();}
  }finally{StandardServiceRegistryBuilder.destroy(registry);}
  System.out.println("WAVY_JPA_OK entities="+entities);
 }
}'''


def artifacts(component, reference, folder):
    name = 'wavy-functional-artifact-' + component + '-' + a.R.name.rsplit('-', 1)[-1]
    a.run(['docker', 'create', '--name', name, '--network', 'none', '--entrypoint', '/bin/true', reference])
    try:
        raw = a.run(['docker', 'cp', name + ':/app/app.jar', '-'])
    finally:
        a.run(['docker', 'rm', '-v', name])
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        jar = archive.extractfile(next(x for x in archive if x.isfile() and x.name.endswith('.jar'))).read()
    with zipfile.ZipFile(io.BytesIO(jar)) as z:
        for name in z.namelist():
            if name.startswith(('BOOT-INF/classes/', 'BOOT-INF/lib/')) and not name.endswith('/'):
                if '..' in Path(name).parts: raise a.Refused('JAR_PATH')
                target = folder / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(z.read(name))
    return a.hashlib.sha256(jar).hexdigest()


def run_checks(run_directory):
    import subprocess
    a.R = Path(run_directory)
    a.private_file(a.R / 'authorization.json')
    approval = json.loads((a.R / 'authorization.json').read_text())
    if approval.get('approved') is not True or approval.get('authorizationDocumentSha256') != a.m.digest(HERE/'AUTORISATION-FONCTIONNELLE.txt'):
        raise a.Refused('FUNCTIONAL_APPROVAL')
    a.m.run(['docker', 'info', '--format', '{{.OSType}}'])
    plan = a.m.plan('recettelocal')
    results = {}
    # Preserve a complete initial fingerprint, including bases that must stay untouched.
    baseline = {db: a.baseline(db) for db in a.DATABASES}
    a.save(a.R/'original-baseline.json', baseline)
    for component in a.DATABASES:
        folder = a.R / (component + '-artifact'); folder.mkdir(mode=0o700)
        jar_hash = artifacts(component, plan['images'][component+'-api'], folder)
        java = folder / 'FunctionalReadOnly.java'; java.write_text(JAVA)
        cp = str(folder/'BOOT-INF/classes') + ':' + str(folder/'BOOT-INF/lib/*')
        a.run(['javac', '--release', '17', '-cp', cp, '-d', str(folder), str(java)])
        db = a.inspect(component+'-db-recette'); env = a.environment(db['Config']['Env'])
        binding = db['HostConfig']['PortBindings']['5432/tcp']
        if len(binding) != 1: raise a.Refused('LOCAL_DB_PORT')
        url = 'jdbc:postgresql://127.0.0.1:'+str(int(binding[0]['HostPort']))+'/'+env['POSTGRES_DB']+'?options=-c%20default_transaction_read_only%3Don'
        locations = {'tiers':'classpath:db/migration,classpath:db/vendor/postgresql',
                     'factures':'classpath:db/migration/common,classpath:db/migration/postgresql'}.get(component, 'classpath:db/migration')
        proc = subprocess.run(['java','-cp',str(folder)+':'+cp,'FunctionalReadOnly',str(folder/'BOOT-INF/classes'),locations,str(component=='socle').lower()],
                              input=('\n'.join((url,env['POSTGRES_USER'],env['POSTGRES_PASSWORD']))+'\n').encode(), capture_output=True, timeout=90)
        # Keep dependency diagnostics private; only controlled markers go to the report.
        log = folder/'validation.private.log';log.write_bytes(proc.stdout+proc.stderr);log.chmod(0o600)
        markers = [x for x in proc.stdout.decode(errors='replace').splitlines() if x.startswith('WAVY_')]
        results[component] = {'passed':proc.returncode==0,'readOnly':True,'jarSha256':jar_hash,'markers':markers,'diagnosticsSha256':a.m.digest(log)}
        a.save(a.R/'migration-jpa-results.json', results)
        a.emit('read-only-api-compatibility',component=component,**results[component])
    after = {db:a.baseline(db) for db in a.DATABASES}
    proof = {'passed':all(v['passed'] for v in results.values()),'originalRowsMatch':baseline==after,'databasesReadOnly':True,'springStarted':False,'migrationsApplied':False,'results':results}
    a.save(a.R/'preflight-result.json',proof)
    return proof

if __name__ == '__main__':
    result=run_checks(sys.argv[1]);sys.exit(0 if result['passed'] and result['originalRowsMatch'] else 1)
