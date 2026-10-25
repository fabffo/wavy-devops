#!/usr/bin/env python3
"""Local candidate control library; no standalone execution path to bypass restore guards."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import time
import tempfile
import zipfile

P = Path(__file__).resolve().parent
PG_IMAGE = 'postgres:16-alpine@sha256:93d55776e04376e19adb2733e3ccebb4392ee7dd86d8ff238503b30fe719c84f'
IMAGES = {
    'old': ('ghcr.io/fabffo/wavy-factures-api@sha256:fad65c9b2c1b5326b3fd45c2fd8f19727104a2ace32b481d12ed3872075f261f', '43428f14be377689030cd2309acfd5f1fe7bdea5f888a1f753c6f4f49c1d97ca'),
    'new': ('ghcr.io/fabffo/wavy-factures-api@sha256:a414a866c910bd20a4c8af4018fc0e31db513ffff1cca76b15c913807f75d0e5', 'b2452d8a99ee99ae8920a0714e5e5b2de3e885726338a68b2760ada5e933a2c9'),
}
CHECKS = ('jpa', 'flyway', 'factures-schema-data-invariant', 'validator-cleanup')


class ValidationRefused(ValueError):
    def __init__(self,stage):
        super().__init__('Isolated validation refused')
        self.stage=stage


def execute(args, input=None, timeout=90, stdout_file=None):
    # Output from DB/JVM may contain business metadata; never forward on exception.
    output={'capture_output':True} if stdout_file is None else {'stdout':stdout_file,'stderr':subprocess.PIPE}
    result = subprocess.run(args, input=input, timeout=timeout, **output)
    if result.returncode:
        raise ValueError('Isolated validation command refused')
    return result.stdout


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def atomic(path, value):
    tmp = path.with_suffix('.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, sort_keys=True); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(tmp, path)
        parent=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(parent)
        finally:os.close(parent)
    finally:
        tmp.unlink(missing_ok=True)


def archive_evidence(path):
    """Retain the exact bytes/hash of a previous report before a retry replaces it."""
    try:info=path.lstat()
    except FileNotFoundError:return
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600:
        raise ValueError('Previous evidence is not private')
    content=path.read_bytes();sha=hashlib.sha256(content).hexdigest()
    history=path.parent/'schema-validation-history'
    history.mkdir(mode=0o700,exist_ok=True)
    info=history.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:
        raise ValueError('Evidence history directory refused')
    destination=history/(sha+'.json')
    try:fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    except FileExistsError:
        info=destination.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600 or destination.read_bytes()!=content:
            raise ValueError('Evidence archive differs')
        return
    with os.fdopen(fd,'wb') as stream:
        stream.write(content);stream.flush();os.fsync(stream.fileno())
    fd=os.open(history,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def guard_container(data, project):
    if not re.fullmatch(r'wavy-pwa-restore-[a-z0-9-]+', project) or 'preprod' in project:
        raise ValueError('Invalid isolated project')
    labels = data['Config'].get('Labels') or {}
    host = data['HostConfig']
    if (labels.get('com.docker.compose.project') != project
            or labels.get('com.docker.compose.service') != 'factures'
            or data['Config']['Image'] != PG_IMAGE
            or host.get('NetworkMode') != 'none' or host.get('PortBindings')
            or host.get('Privileged') or not host.get('ReadonlyRootfs')
            or not data.get('State', {}).get('Running')):
        raise ValueError('Database must belong to isolated networkless project')
    for mount in data.get('Mounts', []):
        if mount['Type'] == 'volume':
            if mount.get('Name') != project + '_factures-data' or mount['Destination'] != '/var/lib/postgresql/data':
                raise ValueError('Unexpected database volume')
        elif mount['Type'] == 'bind':
            if mount.get('RW') or mount['Destination'] != '/run/secrets/db-password':
                raise ValueError('Unexpected database bind')
        elif mount['Type'] != 'tmpfs':
            raise ValueError('Unexpected mount type')


def configuration_guard(environment):
    # Matching the pinned pair's Boot defaults, fail closed on unreviewed overrides.
    accepted = {
        'SPRING_JPA_HIBERNATE_DDL_AUTO': 'validate', 'SPRING_JPA_OPEN_IN_VIEW': 'false',
        'SPRING_JPA_SHOW_SQL': 'false', 'SPRING_JPA_PROPERTIES_HIBERNATE_JDBC_TIME_ZONE': 'UTC',
        'SPRING_FLYWAY_ENABLED': 'true', 'SPRING_FLYWAY_CLEAN_DISABLED': 'true',
        'SPRING_FLYWAY_VALIDATE_ON_MIGRATE': 'true',
    }
    for key, value in environment.items():
        if key.startswith(('SPRING_JPA_', 'SPRING_FLYWAY_')) and accepted.get(key) != str(value):
            raise ValueError('JPA/Flyway override is not reviewed')
    for key in ('SPRING_CONFIG_IMPORT', 'SPRING_APPLICATION_JSON', 'JAVA_TOOL_OPTIONS', 'JDK_JAVA_OPTIONS', 'SPRING_CONFIG_LOCATION'):
        if environment.get(key):
            raise ValueError('Unreviewed runtime configuration source')
    if any(value for key,value in environment.items() if key.startswith('SPRING_CONFIG_')):
        raise ValueError('Additional configuration source is not reviewed')
    if any(value for key,value in environment.items() if key.startswith('SPRING_PROFILES_') and key!='SPRING_PROFILES_ACTIVE'):
        raise ValueError('Additional profiles are not reviewed')
    if environment.get('SPRING_PROFILES_ACTIVE','preprod,secure')!='preprod,secure':
        raise ValueError('Profiles are not reviewed')


def prepare_image(reference, expected_hash, folder, command=execute):
    folder.mkdir(mode=0o755)
    image = json.loads(command(['docker', 'image', 'inspect', reference]))[0]
    if reference not in image.get('RepoDigests', []) or image['Os'] + '/' + image['Architecture'] != 'linux/amd64':
        raise ValueError('Unpinned application image')
    # Created but never started; no application or network can run during extraction.
    name = 'wavy-validator-extract-' + secrets.token_hex(12)
    try:
        command(['docker', 'create', '--pull', 'never', '--name', name, '--network', 'none', '--read-only',
                 '--entrypoint', '/bin/true', reference])
        command(['docker', 'cp', name + ':/app/app.jar', str(folder / 'app.jar')])
    finally:
        command(['docker', 'rm', '-f', name])
    if digest(folder / 'app.jar') != expected_hash:
        raise ValueError('Unexpected embedded JAR')
    with zipfile.ZipFile(folder / 'app.jar') as jar:
        for entry in jar.infolist():
            if not entry.filename.startswith(('BOOT-INF/lib/', 'BOOT-INF/classes/')) or entry.is_dir():
                continue
            target = folder / entry.filename
            if '..' in Path(entry.filename).parts or target.is_absolute() and not target.is_relative_to(folder):
                raise ValueError('Unsafe JAR path')
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            target.write_bytes(jar.read(entry)); target.chmod(0o644)
    command(['javac', '-J-Xmx256m', '--release', '17', '-cp', str(folder / 'BOOT-INF/lib/*'),
             '-d', str(folder), str(P / 'IsolatedSchemaValidator.java')])
    for file in folder.glob('*.class'): file.chmod(0o644)
    return {'reference': reference, 'jarSha256': expected_hash, 'imageId': image['Id'],
            'classSha256': digest(folder / 'IsolatedSchemaValidator.class')}


def admin_sql(container, database, sql, command=execute):
    return command(['docker', 'exec', '-i', container, 'psql', '-X', '-v', 'ON_ERROR_STOP=1',
                    '-U', 'restore_operator', '-d', database, '-At'], input=sql.encode())


def snapshot(container, database, command=execute, scratch=None):
    # Unlinked private temporary file: never retain a plaintext database dump as evidence.
    # Stream hash instead of keeping three full SQL dumps in Python memory.
    fingerprint=hashlib.sha256()
    with tempfile.TemporaryFile(dir=scratch) as output:
        command(['docker', 'exec', container, 'pg_dump', '-U', 'restore_operator', '-d', database,
                 '--no-owner', '--no-acl', '--no-comments'], timeout=90, stdout_file=output)
        output.seek(0)
        for line in output:
            if not line.startswith((b'\\restrict ', b'\\unrestrict ')):
                fingerprint.update(line)
    return fingerprint.hexdigest()


def restricted_role(container, database, command=execute):
    if not re.fullmatch(r'[a-z][a-z0-9_]*', database): raise ValueError('Invalid database identifier')
    role = 'validator_' + secrets.token_hex(12); password = secrets.token_hex(32)
    admin_sql(container, database, f"""
CREATE ROLE {role} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD '{password}';
REVOKE ALL ON DATABASE {database} FROM PUBLIC;
GRANT CONNECT ON DATABASE {database} TO {role};
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO {role};
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
GRANT SELECT ON TABLE public.flyway_schema_history TO {role};
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;
ALTER ROLE {role} SET default_transaction_read_only=on;
ALTER ROLE {role} SET statement_timeout='30s';
""", command)
    # Only this disposable cluster, no external host ranges accepted; no trust on TCP.
    hba=f'local all all trust\nhost {database} {role} 127.0.0.1/32 scram-sha-256\nhost all all 127.0.0.1/32 reject\nhost all all ::1/128 reject\n'
    command(['docker','exec','-i',container,'sh','-c','cat > "$PGDATA/pg_hba.conf"'],input=hba.encode())
    admin_sql(container, database, 'SELECT pg_reload_conf();', command)
    return role, password


def launch(container, project, reference, folder, database, role, password, name, command=execute):
    # Reinspect immediately: never share the namespace of an active/foreign DB.
    inspected = json.loads(command(['docker', 'inspect', container]))[0]
    guard_container(inspected, project)
    command(['docker', 'create', '--pull', 'never', '--name', name, '--label', 'wavy.validator.project=' + project,
             '--interactive', '--network', 'container:' + inspected['Id'], '--read-only',
             '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true', '--user', '1000:1000',
             '--memory', '512m', '--cpus', '1', '--pids-limit', '128',
             '--tmpfs', '/tmp:rw,nosuid,nodev,size=64m',
             '--mount', 'type=bind,source=' + str(folder) + ',target=/work,readonly',
             '--entrypoint', 'java', reference, '-cp', '/work:/work/BOOT-INF/classes:/work/BOOT-INF/lib/*',
             'IsolatedSchemaValidator', database, role, '/work/BOOT-INF/classes'])
    try:
        result = command(['docker', 'start', '-a', '-i', name], input=(password + '\n').encode(), timeout=120)
    except (ValueError,subprocess.TimeoutExpired):
        stage='process'
        try:
            output=command(['docker','logs',name])
            found=re.search(rb'^WAVY_VALIDATION_FAILED stage=(input|sql-permissions|flyway|jpa)$',output,re.M)
            if found:stage=found[1].decode()
        except Exception:pass
        raise ValidationRefused(stage) from None
    status = json.loads(command(['docker', 'inspect', name]))[0]
    if status['State']['ExitCode'] != 0 or not re.search(rb'^WAVY_VALIDATION_OK migrations=20 entities=[1-9][0-9]*$', result, re.M):
        raise ValueError('JPA/Flyway validation failed')
    return {'passed': True, 'summary': re.search(rb'WAVY_VALIDATION_OK[^\r\n]*', result)[0].decode()}


def validate_copies(cmd, project, staging, evidence, binding, command=execute, timeout_seconds=240):
    """Called only by owner-guarded restore. A library call is not a deploy authorization."""
    started = time.monotonic()
    deadline=started+timeout_seconds
    cleaning=False
    report = {**binding, 'project': project, 'status': 'running', 'images': {},
              'runnerSourceSha256': digest(P / 'IsolatedSchemaValidator.java'), 'cleanup': False}
    evidence = Path(evidence)
    archive_evidence(evidence)
    if not 1 <= timeout_seconds <= 240:
        report.update(status='failed',cleanup=True,failure={'stage':'budget','kind':'ValueError'},containers=[])
        atomic(evidence,report)
        raise ValueError('Insufficient bounded validation budget')
    containers = []
    underlying = command
    atomic(evidence,report)
    def tracked(args, **kwargs):
        remaining=10 if cleaning else deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('Isolated validation budget exhausted')
        kwargs['timeout']=min(kwargs.get('timeout',90),remaining)
        if args[:2]==['docker','create'] and '--name' in args:
            args=list(args)
            args[2:2]=['--label','wavy.validator.project='+project]
            name=args[args.index('--name')+1]
            if name not in containers:containers.append(name)
            report['containers']=list(containers);atomic(evidence,report)
        result=underlying(args,**kwargs)
        if args[:3]==['docker','rm','-f'] and args[3] in containers:
            containers.remove(args[3])
        return result
    command=tracked
    try:
        container = command(cmd + ['ps', '-q', 'factures']).decode().strip()
        inspected = json.loads(command(['docker', 'inspect', container]))[0]
        guard_container(inspected, project)
        role, password = restricted_role(container, 'factures', command)
        before = snapshot(container, 'factures', command, scratch=staging)
        for version, (reference, jar_hash) in IMAGES.items():
            folder = Path(staging) / ('validator-' + version)
            image = prepare_image(reference, jar_hash, folder, command)
            name = 'wavy-validator-' + secrets.token_hex(12)
            # Durable intention before create; cleanup handles partially created containers.
            containers.append(name); report['containers'] = list(containers); atomic(evidence, report)
            report['images'][version] = dict(image, **launch(container, project, reference, folder,
                                                          'factures', role, password, name, command))
            after = snapshot(container, 'factures', command, scratch=staging)
            if after != before: raise ValueError('Copy mutated during validation')
            command(['docker', 'rm', '-f', name])
        report['beforeHash'] = before; report['afterHash'] = after
        report['status'] = 'passed'
        return report
    except BaseException as error:
        report['failure']={'stage':getattr(error,'stage','control'),'kind':type(error).__name__}
        report['status'] = 'failed'
        raise
    finally:
        cleaning=True
        failed = False
        for name in list(containers):
            try:
                command(['docker', 'rm', '-f', name])
            except BaseException:
                failed = True
        report['containers'] = list(containers); report['cleanup'] = not failed
        if failed:report['status']='cleanup-failed'
        report['seconds'] = round(time.monotonic() - started, 3)
        atomic(evidence, report)
        if failed:
            raise ValueError('Validator cleanup incomplete; preserve recovery state')
