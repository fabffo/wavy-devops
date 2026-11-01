#!/usr/bin/env python3
"""Diagnostic de l'installateur existant. Lecture seule ; sorties sans secrets."""
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys

from release_images import COMPONENTS, manifest, recette_compose, release
from recette_pwa import policy, has_subpath, storage_permissions, EMPTY_STORAGE_PROBE

DATABASES = ('socle','tiers','contrats','factures','tresorerie')


class Report:
    def __init__(self):
        self.rows = []
        self.components = {}

    def add(self, code, status, message, evidence=None):
        # L'origine publique termine sur Caddy Windows, pas sur le daemon VM.
        if code.startswith('https.') and status == 'error': status = 'warning'
        category = 'BLOQUANT' if status == 'error' else ('AVERTISSEMENT' if status == 'warning' else 'INFORMATION')
        row={'code':code, 'status':status, 'category':category, 'message':message}
        if evidence is not None: row['evidence']=evidence
        if row not in self.rows: self.rows.append(row)

    def check(self, condition, message, code='configuration'):
        if not condition: self.add(code, 'error', message)

    def attempt(self, code, operation, unavailable='error'):
        try:
            return operation()
        except (ValueError, KeyError, IndexError, TypeError, OSError, subprocess.SubprocessError) as error:
            # Aucune sortie brute Docker/Compose, aucune valeur dotenv dans le rapport.
            if getattr(error,'delivery_security_risk',False):
                self.add('security.cors','error',str(error),evidence='ECART_OBSERVE')
            else:
                self.add(code, unavailable, str(error) if isinstance(error, ValueError) else 'Contrôle impossible : '+type(error).__name__, evidence='NON_VERIFIE')
            return None

    def result(self):
        errors = sum(row['status'] == 'error' for row in self.rows)
        warnings = sum(row['category'] == 'AVERTISSEMENT' for row in self.rows)
        return {'environment':'recette', 'mutations':False, 'decision':'NO-GO' if errors else ('GO avec avertissements' if warnings else 'GO prérequis'),
                'errors':errors, 'warnings':warnings, 'checks':self.rows, 'components':self.components,
                'limit':'Pas de garantie de migration, sauvegarde ou disponibilité future ; leurs contrôles restent obligatoires pendant installation.'}


def command(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=30,
                            env={**os.environ,'GIT_OPTIONAL_LOCKS':'0'})
    if result.returncode:
        raise ValueError('Commande de lecture refusée : '+args[0]+' '+args[1])
    return result.stdout.rstrip("\n")


def git_status(root):
    paths = ['wavy','scripts','docker',':(glob)docker-compose*.yml','versions']
    paths += [f':(exclude,literal)versions/history/recette/{c}.tsv' for c in COMPONENTS]
    return command(['git','-C',str(root),'status','--porcelain','--untracked-files=all','--',*paths])


def read_machine(root, report):
    from delivery_check import dotenv_literal
    path = root/'.env.recette'
    if not path.is_file():
        report.add('dotenv', 'error', '.env.recette absent')
        return {}
    report.check(not path.is_symlink() and path.stat().st_uid == os.getuid() and not path.stat().st_mode & 0o077,
                 '.env.recette doit appartenir à l’opérateur et être privé (0600)', 'dotenv.permissions')
    values = {}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip() or line.lstrip().startswith('#'): continue
        match = re.fullmatch(r'([A-Z][A-Z0-9_]*)=(.*)', line.strip())
        if not match:
            report.add('dotenv.syntax', 'error', f'Syntaxe dotenv invalide à la ligne {number}')
            continue
        key, raw = match.groups()
        value = report.attempt('dotenv.'+key, lambda: dotenv_literal(raw))
        if key in values:
            if values[key]==value:
                report.add('dotenv.duplicate','warning','Variable répétée avec la même valeur : '+key)
            else:
                report.add('dotenv.duplicate','error','Variable dupliquée contradictoire : '+key)
        if value is not None: values[key] = value
        if key=='WAVY_GATEWAY_CORS_ALLOWED_ORIGIN_PATTERNS':
            report.add('dotenv.legacy','warning','Ancienne variable CORS Gateway ignorée ; seule la variable CORS commune rendue est utilisée.')
        report.check(not (key.endswith(('_VERSION','_DIGEST')) or key == 'WAVY_IMAGE_REGISTRY'),
                     'Variable machine incompatible : '+key, 'dotenv.override')
    return values


def lock_check(path, report):
    # Ne pas créer un verrou pour un diagnostic. flock n'écrit pas dans le fichier.
    if path.is_symlink():
        report.add('lock', 'error', 'Verrou symbolique refusé : '+path.name)
    elif path.exists():
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally: os.close(fd)
        except (OSError, ValueError):
            report.add('lock', 'error', 'Opération concurrente ou verrou inaccessible : '+path.name)


def config_checks(root, values, report):
    from delivery_check import rendered_checks, valid_profile
    status = report.attempt('git', lambda: git_status(root))
    if status is not None:
        report.check(not status, 'Livraison non synchronisée avec Git ; fichiers concernés : '+', '.join(line[3:] for line in status.splitlines()), 'git.dirty')
    report.check(values.get('COMPOSE_PROJECT_NAME','wavy-recette') == 'wavy-recette', 'Projet attendu : wavy-recette', 'project')
    report.check(values.get('WAVY_INSTALL_HOSTNAME') == socket.gethostname().split('.')[0], 'WAVY_INSTALL_HOSTNAME doit identifier cet hôte', 'host')
    for path in (root/'deployments/recette-https-reservation.json', Path.home()/'.local/state/wavy/recettelocal/runtime-info.json'):
        report.check(not path.exists(), 'Session MSI réservée : '+path.name, 'reservation')
    lock_check(root/'deployments/recette.lock', report)
    lock_check(root/'backups/.recette-backup.lock', report)
    for name in ('WAVY_PWA_ENABLED','WAVY_NOTES_WRITES_ENABLED'):
        report.check(values.get(name,'false') == 'true', name+'=true requis pour le parcours PWA demandé', name)
    report.check(values.get('WAVY_RECETTE_VALIDATION_MODE','qualification') == 'technical', 'Installation standard : WAVY_RECETTE_VALIDATION_MODE=technical requis', 'policy.mode')
    report.check(values.get('WAVY_RECETTE_PROVISION_JUSTIFICATIFS','false') in ('true','false'), 'Provision justificatifs : true ou false attendu', 'storage.provision')
    wait = values.get('WAVY_INSTALL_WAIT_SECONDS','600')
    report.check(re.fullmatch(r'[0-9]+',wait) and 180 <= int(wait) <= 3600, 'WAVY_INSTALL_WAIT_SECONDS : entier entre 180 et 3600', 'wait')
    for c in ('socle-api','tiers-api','contrats-api','factures-api','tresorerie-api','gateway'):
        key = 'WAVY_'+c.upper().replace('-API','').replace('-','_')+'_SPRING_PROFILES_ACTIVE'
        value = values.get(key,'local' if c=='socle-api' else 'recette')
        report.check(valid_profile(c,value), 'Profil incohérent : recette/'+c, 'profile.'+c)
    for db in DATABASES:
        key = 'WAVY_'+db.upper()+'_DB_PASSWORD'
        if not values.get(key) or values[key] in ('motdepasse_recette','CHANGE_ME'):
            report.add('credentials.'+db,'warning','Déclaration absente ou valeur historique : '+key+' ; le rendu et sa cohérence avec les conteneurs existants font foi, sans réinitialisation')
    for key in ('WAVY_TIERS_SERVICE_USERNAME','WAVY_TIERS_SERVICE_PASSWORD'):
        report.check(bool(values.get(key)), 'Compte interservices incomplet : '+key, 'credentials.tiers')
    volume=values.get('WAVY_FACTURES_JUSTIFICATIFS_VOLUME','')
    report.check(bool(re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*',volume)), 'Nom du volume justificatifs absent ou invalide', 'storage.name')
    images = {}
    for c in COMPONENTS:
        result = report.attempt('release.'+c, lambda c=c: release(root,'recette',components=[c]))
        if result: images.update(result[2])
    state = None
    if len(images) == 13:
        # Valider les paramètres techniques indépendamment du mode historique ;
        # policy.mode ci-dessus reste bloquant si le mode attendu n'est pas sélectionné.
        state = report.attempt('policy', lambda: policy(root,{**values,'WAVY_RECETTE_VALIDATION_MODE':'technical'},images))
        if state:
            for missing in state['missing']: report.add('policy', 'error', missing)
    config = report.attempt('compose', lambda: recette_compose(root,['config','--format','json'],capture=True))
    if config:
        rendered_checks(config,'recette',images,state['origin'] if state else None,check=report.check)
        for c in COMPONENTS:
            svc = config.get('services',{}).get(f'wavy-{c}-recette',{})
            env = svc.get('environment',{})
            report.components[c] = {'image':svc.get('image'), 'profile':env.get('SPRING_PROFILES_ACTIVE','sans objet (Nginx)'),
                                    'healthcheck':svc.get('healthcheck',{}).get('start_period','image / défaut')}
            if c in ('socle-api','tiers-api') and env.get('SPRING_PROFILES_ACTIVE') == 'local':
                report.add('profile.'+c, 'warning', c+' : profil local historique conservé, sans activation implicite de secure ; les backends restent privés et le changement de profil reste contrôlé.')
        for name, svc in config['services'].items():
            for key, value in svc.get('environment',{}).items():
                if key.endswith('PASSWORD'):
                    report.check(bool(value), 'Secret candidat vide : '+name+'/'+key, 'credentials.rendered')
        tiers = config['services'].get('wavy-tiers-api-recette',{}).get('environment',{})
        report.check(bool(tiers.get('WAVY_TIERS_SERVICE_USERNAME')), 'Compte interservices Tiers absent', 'credentials.username')
        factures = config['services'].get('wavy-factures-api-recette',{}).get('environment',{})
        if not all(factures.get(k) for k in ('WAVY_AI_PROVIDER','WAVY_AI_MODEL','WAVY_AI_API_KEY')):
            report.add('ai', 'warning', 'IA non entièrement configurée : provider/modèle/clé ; aucun appel fournisseur ni test métier exécuté')
    return images, state, config


def mounts_check(obj, svc, config, report):
    """Tous les volumes de données existants doivent rester attachés au même endroit."""
    name = obj['Name'].lstrip('/')
    desired = {m['target']:m for m in svc.get('volumes',[]) if m['type']=='volume'}
    for mount in obj.get('Mounts',[]):
        if mount.get('Type') not in ('volume','bind') or mount.get('Destination') not in (
                '/var/lib/postgresql/data','/app/justificatifs','/app/data/contrats/pieces-jointes'): continue
        target = mount['Destination']; wanted = desired.get(target,{})
        volume = config.get('volumes',{}).get(wanted.get('source'),{}).get('name')
        report.check(mount.get('Type')=='volume' and mount.get('Name')==volume and not has_subpath(obj,target) and mount.get('RW') is True,
                     'Montage existant à préserver : '+name+target, 'mounts')


def document_layout(report):
    from recette_documents import validate_document_path
    # Métadonnées seulement ; aucun octet de document lu ou archivé.
    script = """find /app/justificatifs -mindepth 1 -type d -exec sh -ec 'for p do printf "D\\t%s\\n" "${p#/app/justificatifs/}"; done' sh {} +
find /app/justificatifs -mindepth 1 -type f -exec sh -ec 'for p do printf "F\\t%s\\t%s\\n" "$(stat -c %s "$p")" "${p#/app/justificatifs/}"; done' sh {} +"""
    output=report.attempt('backup.layout',lambda: command(['docker','exec','wavy-factures-api-recette','sh','-ec',script]))
    if output is None: return
    for line in output.splitlines():
        fields=line.split('\t')
        if fields[0]=='D' and len(fields)==2:
            report.attempt('backup.layout',lambda fields=fields: validate_document_path(fields[1],True))
        elif fields[0]=='F' and len(fields)==3 and fields[1].isdigit():
            report.attempt('backup.layout',lambda fields=fields: validate_document_path(fields[2],False,int(fields[1])))
        else: report.add('backup.layout','error','Métadonnées documentaires inexploitables pour le futur scellement')


def runtime_checks(root, values, images, state, config, report):
    from delivery_check import profiles, request, cors_runtime
    # Aucune commande du daemon tant que la destination locale n'est pas établie.
    if os.environ.get('DOCKER_HOST') or os.environ.get('DOCKER_CONTEXT'):
        report.add('docker.context', 'error', 'Overrides Docker interdits ; aucune inspection runtime effectuée')
        report.add('runtime','pending','Docker, registre, stockage, backup et HTTPS non vérifiés : destination interdite')
        return
    endpoint = report.attempt('docker.context', lambda: command(['docker','context','inspect','--format','{{.Endpoints.docker.Host}}']))
    if endpoint != 'unix:///var/run/docker.sock':
        report.add('docker.context', 'error', 'Socket Docker système local requis ; runtime non inspecté')
        report.add('runtime','pending','Inventaire, volumes, capacité, backup, registre et HTTPS non vérifiés : daemon indisponible')
        return
    report.attempt('docker.info', lambda: command(['docker','info','--format','{{.ServerVersion}}']))
    report.attempt('docker.compose', lambda: command(['docker','compose','version']))
    help_text=report.attempt('docker.compose.capabilities',lambda:command(['docker','compose','up','--help']))
    if help_text is not None:
        for option in ('--wait','--wait-timeout','--no-build'):
            report.check(option in help_text, 'Docker Compose ne fournit pas '+option, 'docker.compose.capabilities')
    if values.get('WAVY_INSTALL_HOSTNAME') != socket.gethostname().split('.')[0]:
        report.add('runtime', 'pending', 'Hôte non désigné par WAVY_INSTALL_HOSTNAME : inspections et HTTPS cible non exécutés')
        return
    objects = {}
    names = [f'wavy-{c}-recette' for c in COMPONENTS]+[f'{db}-db-recette' for db in DATABASES]
    services = config.get('services',{}) if config else {}
    by_name = {s.get('container_name',key):s for key,s in services.items()}
    for name in names:
        data = report.attempt('container.'+name, lambda name=name: json.loads(command(['docker','inspect',name])))
        if not data: continue
        obj = data[0]; objects[name] = obj
        report.check(obj.get('Config',{}).get('Labels',{}).get('com.docker.compose.project')=='wavy-recette', 'Conteneur hors projet : '+name, 'container.project')
        if name.startswith('wavy-') and '-api-' not in name and name!='wavy-gateway-recette':
            if not obj.get('State',{}).get('Running'):
                report.add('container.running','planned','Front arrêté, sans écriture métier : Compose le démarrera : '+name)
        else:
            report.check(obj.get('State',{}).get('Running'), 'Service nécessaire à la sauvegarde arrêté : '+name, 'container.running')
        active = dict(x.split('=',1) for x in obj.get('Config',{}).get('Env',[]) if '=' in x)
        desired = by_name.get(name,{}).get('environment',{})
        if 'SPRING_PROFILES_ACTIVE' in desired:
            previous = profiles(active.get('SPRING_PROFILES_ACTIVE',''))
            wanted = profiles(desired['SPRING_PROFILES_ACTIVE'])
            report.check(previous == wanted, 'Transition de profil à qualifier : '+name+' ('+','.join(previous)+' → '+','.join(wanted)+')', 'profile.transition')
        if config: mounts_check(obj,by_name.get(name,{}),config,report)
        exposed=any(binding.get('HostIp') not in ('127.0.0.1','::1')
                    for bindings in obj.get('HostConfig',{}).get('PortBindings',{}).values() for binding in bindings or [])
        if exposed:
            if name=='wavy-erp-shell-recette':
                report.add('network.proxy','warning','Entrée ERP HTTP réservée au chemin Caddy Windows ; son bind configuré est conservé. Le filtrage et la joignabilité de ce chemin ne sont pas attestés ici.')
            else:
                report.add('network.'+name,'planned','Backend actuellement exposé : le candidat le réserve à loopback sans modifier les données : '+name)
        for key in ('POSTGRES_DB','POSTGRES_USER','POSTGRES_PASSWORD','SPRING_DATASOURCE_URL','SPRING_DATASOURCE_USERNAME','SPRING_DATASOURCE_PASSWORD'):
            if key in desired and key in active:
                report.check(desired[key]==active[key], 'Configuration DB différente de l’existant : '+name+'/'+key, 'database.identity')
    for db in DATABASES:
        name=f'{db}-db-recette'; obj=objects.get(name)
        if not obj or not obj.get('State',{}).get('Running'): continue
        env=dict(x.split('=',1) for x in obj['Config'].get('Env',[]) if '=' in x)
        for binary in ('pg_dump','pg_restore'):
            report.attempt('backup.'+db+'.'+binary, lambda binary=binary,name=name: command(['docker','exec',name,binary,'--version']))
        report.attempt('backup.'+db+'.connection', lambda name=name,env=env: command(['docker','exec',name,'psql','-v','ON_ERROR_STOP=1','-U',env.get('POSTGRES_USER',''),'-d',env.get('POSTGRES_DB',''),'-Atc','SELECT 1']))
    for directory in (root, root/'backups', root/'deployments'):
        existing = directory if directory.exists() else directory.parent
        stats=report.attempt('disk',lambda existing=existing: os.statvfs(existing),unavailable='warning')
        if stats:
            report.check(stats.f_bavail>0, 'Disque plein : '+directory.name, 'disk.full')
            if 0 < stats.f_bavail*stats.f_frsize < 1024**3:
                report.add('disk','warning','Moins de 1 Gio disponible : '+directory.name+' ; seuil indicatif, la réussite du backup reste obligatoire.')
        report.check(os.access(existing,os.W_OK|os.X_OK), 'Répertoire non inscriptible : '+directory.name, 'permissions')
    docker_root = report.attempt('docker.disk',lambda: command(['docker','info','--format','{{.DockerRootDir}}']),unavailable='warning')
    if docker_root:
        stats=report.attempt('docker.disk',lambda: os.statvfs(docker_root),unavailable='warning')
        if stats:
            report.check(stats.f_bavail>0,'Disque Docker plein','disk.full')
            if 0 < stats.f_bavail*stats.f_frsize < 1024**3:
                report.add('docker.disk','warning','Moins de 1 Gio disponible pour les images ; aucun manque effectif d’espace n’est confirmé.')
    if state:
        obj=objects.get('wavy-factures-api-recette')
        if obj:
            report.attempt('backup.tar',lambda:command(['docker','exec','wavy-factures-api-recette','sh','-ec','command -v tar >/dev/null']))
            env=dict(x.split('=',1) for x in obj['Config'].get('Env',[]) if '=' in x)
            old=env.get('WAVY_FACTURES_STOCKAGE_JUSTIFICATIFS','')
            report.check(not old or old=='/app/justificatifs', 'Stockage Factures non standard : migration explicite requise', 'storage.existing')
            if old == '/app/justificatifs':
                report.attempt('storage.permissions',storage_permissions)
                document_layout(report)
            elif not old:
                report.attempt('storage.initial',lambda: command(['docker','exec','wavy-factures-api-recette','sh','-ec',
                    EMPTY_STORAGE_PROBE]))
                report.add('storage.initial','planned','Premier rattachement vide : UID/GID et permissions seront contrôlés avant sauvegarde, sans modification de l’existant')
        volume=state['volume']
        volumes=report.attempt('storage.volumes',lambda: command(['docker','volume','ls','--format','{{.Name}}']))
        if volumes is not None and volume:
            if volume not in volumes.splitlines():
                report.check(values.get('WAVY_RECETTE_PROVISION_JUSTIFICATIFS')=='true', 'Volume absent : création initiale non autorisée', 'storage.absent')
                if values.get('WAVY_RECETTE_PROVISION_JUSTIFICATIFS')=='true': report.add('storage.create','planned','Volume absent : création initiale privée autorisée ; aucun volume existant ne sera chowné')
            else:
                meta=report.attempt('storage.volume',lambda: json.loads(command(['docker','volume','inspect',volume]))[0])
                if meta:
                    report.check(meta.get('Driver')=='local' and not meta.get('Options'), 'Volume documentaire local sans options requis', 'storage.driver')
                    if obj and not any(m.get('Destination')=='/app/justificatifs' for m in obj.get('Mounts',[])):
                        mountpoint=meta.get('Mountpoint')
                        if mountpoint:
                            try:
                                nonempty=next(Path(mountpoint).iterdir(),None) is not None
                                report.check(not nonempty, 'Volume initial non vide : rattachement automatique refusé pour préserver les documents', 'storage.initial.volume')
                            except OSError:
                                report.add('storage.initial.volume','pending','Volume non monté et racine inaccessible à l’opérateur : contrôle de vacuité/permissions non prouvé sans conteneur ; contrôle obligatoire avant backup')
                        else:
                            report.add('storage.initial.volume','pending','Métadonnée Mountpoint absente : vacuité et permissions initiales non vérifiées')

        for code,op in [('https.tls',lambda: request(state['origin'],'/')),('https.session',lambda:request(state['origin'],'/api/auth/session',(401,))),('https.cors',lambda:cors_runtime(state['origin']))]:
            report.attempt(code,op)
        report.add('https.pwa','planned','Routes ERP/PWA et manifeste ouvert contrôlés après installation : la fermeture actuelle peut être corrigée par le rendu candidat')
    # Vérifier l'accès registre pour chaque image sans docker pull ni création de conteneur.
    for c,image in images.items():
        cached=None
        try:
            cached=json.loads(command(['docker','image','inspect',image]))[0]
        except (ValueError,IndexError,OSError,subprocess.SubprocessError):
            pass  # Une image absente du cache pourra être téléchargée, après le diagnostic.
        if cached:
            repo,digest=image.split('@')
            report.check(repo.rsplit(':',1)[0]+'@'+digest in cached.get('RepoDigests',[]), 'Cache image incompatible : '+c, 'image.cache.'+c)
            report.add('image.cache.'+c,'planned','Image épinglée présente : aucun téléchargement requis pour '+c)
        else:
            report.attempt('registry.'+c,lambda image=image: command(['docker','manifest','inspect',image]))
    report.add('execution','pending','Arrêt coordonné, pg_dump, intégrité archive, migrations et disponibilité après remplacement restent des contrôles d’exécution ; aucun succès anticipé')


def diagnose(root, live=True):
    report=Report()
    for name in ('docker','git','python3','flock'):
        report.check(shutil.which(name) is not None, 'Commande requise absente : '+name, 'command.'+name)
    report.check(sys.version_info >= (3,11), 'Python 3.11 minimum requis par le scellement SHA256 existant', 'python')
    values=report.attempt('dotenv',lambda:read_machine(root,report)) or {}
    images,state,config=config_checks(root,values,report)
    if live: runtime_checks(root,values,images,state,config,report)
    else: report.add('runtime','pending','Inspections Docker, registre et HTTPS non exécutés dans ce test statique')
    return report.result()
