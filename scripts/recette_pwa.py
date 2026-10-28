#!/usr/bin/env python3
"""Politique PWA du Compose RECETTE existant ; aucune opération de données."""
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
from urllib.parse import urlsplit

COMPONENTS = ('socle-api', 'tiers-api', 'gateway', 'factures-api', 'factures-front', 'pwa', 'erp-shell')
READ_CHECKS = ('https-session', 'pwa-routing', 'erp-iframe', 'mobile-login', 'roles-denied',
               'session-isolation', 'company-switch', 'private-storage', 'backup-restore',
               'note-role-allowed', 'tiers-me-allowed', 'merchant-read-allowed', 'direct-api-ports-private')
WRITE_CHECKS = ('notes-create-update', 'attachment-reload', 'cross-tenant-write-denied',
                'cross-company-write-denied', 'concurrent-attachment-isolation')


def literal(value):
    if value.startswith(('"', "'")):
        if len(value) < 2 or value[-1] != value[0]:
            raise ValueError('Valeur PWA entre quotes incomplètes')
        value = value[1:-1]
    if '"' in value or "'" in value:
        raise ValueError('Quote interne interdite dans les paramètres PWA')
    return value


def flag(machine, key):
    value = literal(machine.get(key, 'false'))
    if value not in ('true', 'false'):
        raise ValueError(f'{key} : true ou false requis')
    return value == 'true'


def policy(root, machine, images):
    enabled = flag(machine, 'WAVY_PWA_ENABLED')
    writes = flag(machine, 'WAVY_NOTES_WRITES_ENABLED')
    origin = literal(machine.get('WAVY_PWA_PUBLIC_ORIGIN', 'https://recette.wavyservices.fr'))
    url = urlsplit(origin)
    if not re.fullmatch(r'https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?', origin) or url.scheme != 'https' or not url.hostname or url.path or url.query or url.fragment or url.username or url.password or any(c in origin for c in '{};$"\\\n\r'):
        raise ValueError('WAVY_PWA_PUBLIC_ORIGIN : origine HTTPS exacte requise')
    volume = literal(machine.get('WAVY_FACTURES_JUSTIFICATIFS_VOLUME', ''))
    missing = []
    proof = None
    filename = literal(machine.get('WAVY_PWA_QUALIFICATION_FILE', ''))
    if filename:
        path = Path(filename)
        if not path.is_absolute():
            path = root/path
        if not path.is_file() or path.is_symlink() or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
            missing.append('qualification privée absente ou permissions différentes de 0600')
        else:
            try:
                proof = json.loads(path.read_text())
                if not isinstance(proof, dict):
                    proof = None
                    missing.append('qualification JSON objet requise')
            except (ValueError, OSError):
                missing.append('qualification illisible')
    else:
        missing.append('WAVY_PWA_QUALIFICATION_FILE absent')
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*', volume):
        missing.append('volume privé existant WAVY_FACTURES_JUSTIFICATIFS_VOLUME absent ou invalide')
    if proof is not None:
        if proof.get('environment') != 'recette' or proof.get('origin') != origin or proof.get('approved') is not True or not proof.get('reviewer'):
            missing.append('qualification non approuvée pour cette origine RECETTE')
        if proof.get('images') != {c: images[c] for c in COMPONENTS}:
            missing.append('qualification incompatible avec les images de la release')
        if proof.get('storageVolume') != volume:
            missing.append('qualification incompatible avec le stockage configuré')
        backup = proof.get('backup', {})
        if not isinstance(backup, dict) or not re.fullmatch(r'[0-9a-f]{64}', str(backup.get('manifestSha256',''))) or backup.get('restoredManifestSha256') != backup.get('manifestSha256'):
            missing.append('lot de sauvegarde et exercice de restauration non liés par SHA256')
        checks = READ_CHECKS + (WRITE_CHECKS if writes else ())
        observed = proof.get('checks', {})
        if not isinstance(observed, dict):
            observed = {}
        missing.extend(check for check in checks if observed.get(check) is not True)
    mode = literal(machine.get('WAVY_RECETTE_VALIDATION_MODE', 'qualification'))
    if mode not in ('qualification', 'technical'):
        raise ValueError('Mode de validation RECETTE invalide')
    if mode == 'technical':
        # RECETTE sert à la validation humaine après installation. Aucune
        # attestation fonctionnelle n'est fabriquée pour ouvrir les routes.
        missing = []
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*', volume):
            missing.append('volume privé WAVY_FACTURES_JUSTIFICATIFS_VOLUME absent ou invalide')
    if enabled or writes:
        cors = literal(machine.get('WAVY_CORS_ALLOWED_ORIGIN_PATTERNS', 'https://recette.wavyservices.fr'))
        if origin not in [value.strip() for value in cors.split(',')]:
            missing.append('origine PWA absente de la liste CORS exacte des APIs')
    return {'enabled': enabled, 'writes': writes, 'origin': origin, 'volume': volume,
            'missing': missing, 'go': not missing, 'environment': 'recette', 'mode': mode}


def has_subpath(obj, target):
    for mount in obj.get('HostConfig', {}).get('Mounts', []):
        if mount.get('Target') == target and any(mount.get('VolumeOptions', {}).get(k) for k in ('Subpath','SubPath')):
            return True
    return any(m.get('Destination') == target and m.get('SubPath') for m in obj.get('Mounts', []))


def preserve_storage(state):
    result = subprocess.run(['docker', 'inspect', 'wavy-factures-api-recette'], capture_output=True, text=True)
    if result.returncode:
        # Une installation absente ne possède aucun montage à remplacer.
        if 'No such object' not in result.stderr and 'No such container' not in result.stderr:
            raise ValueError('PWA : impossible de vérifier le stockage existant')
        return
    obj = json.loads(result.stdout)[0]
    environment = dict(item.split('=', 1) for item in obj['Config'].get('Env', []) if '=' in item)
    old = environment.get('WAVY_FACTURES_STOCKAGE_JUSTIFICATIFS', '')
    if old or any(m.get('Destination') == '/app/justificatifs' for m in obj.get('Mounts', [])):
        mounts = [m for m in obj.get('Mounts', []) if m['Destination'] == old]
        if old != '/app/justificatifs' or len(mounts) != 1 or mounts[0].get('Type') != 'volume' or mounts[0].get('Name') != state['volume'] or has_subpath(obj,old):
            raise ValueError('PWA : préserver le stockage existant ; aucune migration ou suppression de montage automatique')


def runtime_check(state, images):
    """Lecture seule, exécutée sur l'hôte de lancement avant toute recréation."""
    for component in COMPONENTS:
        result = subprocess.run(['docker', 'inspect', 'wavy-'+component+'-recette'], capture_output=True, text=True)
        if result.returncode:
            raise ValueError(f'PWA : prérequis runtime absent : {component}')
        obj = json.loads(result.stdout)[0]
        local = subprocess.run(['docker', 'image', 'inspect', obj['Image']], capture_output=True, text=True, check=True)
        repository, digest = images[component].split('@')
        expected = repository.rsplit(':', 1)[0]+'@'+digest
        if expected not in json.loads(local.stdout)[0].get('RepoDigests', []):
            raise ValueError(f'PWA : image active non qualifiée : {component}')
        status = obj.get('State', {})
        if not status.get('Running') or status.get('Health', {}).get('Status', 'healthy') != 'healthy':
            raise ValueError(f'PWA : prérequis runtime indisponible : {component}')
        if component == 'factures-api':
            environment = dict(item.split('=', 1) for item in obj['Config'].get('Env', []) if '=' in item)
            mounts = [m for m in obj.get('Mounts', []) if m['Destination'] == '/app/justificatifs']
            if environment.get('WAVY_FACTURES_STOCKAGE_JUSTIFICATIFS') != '/app/justificatifs' or len(mounts) != 1 or mounts[0].get('Type') != 'volume' or mounts[0].get('Name') != state['volume'] or has_subpath(obj,'/app/justificatifs') or (state['writes'] and not mounts[0].get('RW')):
                raise ValueError('PWA : stockage existant non qualifié ; aucun remplacement ou provisionnement automatique')

    storage_permissions()
    direct_ports()


def overlay(root, machine, images, mutation=False, enforce=True):
    state = policy(root, machine, images)
    if enforce and (state['enabled'] or state['writes']) and not state['go']:
        raise ValueError('PWA RECETTE NO-GO : '+', '.join(state['missing']))
    if state['volume'] and not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*', state['volume']):
        raise ValueError('Volume justificatifs invalide')
    if mutation:
        preserve_storage(state)
    if mutation and (state['enabled'] or state['writes']):
        if state['mode'] == 'technical':
            from recette_storage import check_volume
            check_volume(state['volume'], images['factures-api'])
        else:
            runtime_check(state, images)
    directory = root/'docker/recette-pwa'
    def mount(filename, target):
        source = directory/filename
        if not source.is_file():
            raise ValueError('Configuration Nginx PWA absente : '+filename)
        return {'type': 'bind', 'source': str(source), 'target': target, 'read_only': True,
                'bind': {'create_host_path': False}}
    mounts = [mount('shell.conf.template', '/etc/nginx/templates/default.conf.template'),
              mount('routes-open.conf' if state['enabled'] else 'routes-closed.conf', '/etc/nginx/pwa-route.conf'),
              mount('integration-open.json' if state['enabled'] else 'integration-closed.json', '/usr/share/nginx/html/pwa-integration.json'),
              mount('notes-write.conf' if state['writes'] else 'notes-read.conf', '/etc/nginx/wavy-pwa/notes.conf')]
    result = {'services': {'wavy-erp-shell-recette': {'volumes': mounts, 'environment': {
        'WAVY_PWA_PUBLIC_ORIGIN': state['origin'],
        'NGINX_ENVSUBST_FILTER': '_UPSTREAM$|^WAVY_PWA_PUBLIC_ORIGIN$'}}}}
    if state['volume']:
        result['services']['wavy-factures-api-recette'] = {
            'environment': {'WAVY_FACTURES_STOCKAGE_JUSTIFICATIFS': '/app/justificatifs'},
            'volumes': [{'type': 'volume', 'source': 'recette-justificatifs', 'target': '/app/justificatifs', 'volume': {'nocopy': True}}]}
        result['volumes'] = {'recette-justificatifs': {'name': state['volume'], 'external': True}}
    return result


STORAGE_PROBE = r"""set -eu
root=/app/justificatifs
uid="$(id -u)"; gid="$(id -g)"
test "$uid" -ne 0
test -d "$root"; test ! -L "$root"; test -r "$root"; test -w "$root"
test "$(stat -c '%u:%g:%a' "$root")" = "$uid:$gid:700"
test -z "$(find "$root" ! -type f ! -type d -print -quit)"
test -z "$(find "$root" ! -user "$uid" -print -quit)"
test -z "$(find "$root" ! -group "$gid" -print -quit)"
test -z "$(find "$root" -type d ! -perm 0700 -print -quit)"
test -z "$(find "$root" -type f ! -perm 0600 -print -quit)"
available="$(df -Pk "$root" | awk 'NR==2 {print $4}')"
test "$available" -ge 1048576
printf 'private-storage-ok\n'
"""


def storage_permissions(container="wavy-factures-api-recette", require_capacity=True):
    # Exécuté avec l'utilisateur applicatif ; aucune création/chmod/chown/lecture de document.
    result = subprocess.run(['docker','exec',container,'sh','-ec',STORAGE_PROBE if require_capacity else STORAGE_PROBE.replace('-ge 1048576','-ge 0')],
                            capture_output=True,text=True,timeout=30)
    if result.returncode or result.stdout.strip()!='private-storage-ok':
        raise ValueError('Stockage privé : UID/GID, modes 0700/0600, absence de liens et espace libre à vérifier')


def direct_ports():
    names = ['wavy-'+c+'-recette' for c in ('socle-api','tiers-api','contrats-api','factures-api','tresorerie-api','gateway','pwa','erp-shell','socle-front','tiers-front','contrats-front','factures-front','tresorerie-front')]
    names += [c+'-db-recette' for c in ('socle','tiers','contrats','factures','tresorerie')]
    result = subprocess.run(['docker','inspect',*names],capture_output=True,text=True,timeout=30)
    if result.returncode:
        raise ValueError('Ports directs : services RECETTE absents ou non inspectables')
    exposed = []
    objects = json.loads(result.stdout)
    if {obj['Name'].lstrip('/') for obj in objects} != set(names):
        raise ValueError('Ports directs : inventaire RECETTE incomplet')
    for obj in objects:
        for bindings in obj.get('HostConfig',{}).get('PortBindings',{}).values():
            if any(binding.get('HostIp') not in ('127.0.0.1','::1') for binding in bindings or []):
                exposed.append(obj['Name'].lstrip('/'))
    if exposed:
        raise ValueError('Ports directs publiés hors loopback : '+', '.join(sorted(set(exposed))))


def local_daemon():
    if os.environ.get('DOCKER_HOST') or os.environ.get('DOCKER_CONTEXT'):
        raise ValueError('Diagnostic runtime : daemon Docker local uniquement')
    result = subprocess.run(['docker','context','inspect','--format','{{.Endpoints.docker.Host}}'],capture_output=True,text=True,timeout=10)
    if result.returncode or not result.stdout.strip().startswith('unix://'):
        raise ValueError('Diagnostic runtime : socket Docker local requis')


def qualification_plan(images, origin):
    return {'environment':'recette','origin':origin,'images':{c:images[c] for c in COMPONENTS},
            'writesExecuted':False,'requiredChecks':list(READ_CHECKS+WRITE_CHECKS),
            'accounts':['NOTE_DE_FRAIS tenant A société A1','NOTE_DE_FRAIS tenant A société A2',
                        'NOTE_DE_FRAIS tenant B','rôle sans Notes','SUPER_NOTE_DE_FRAIS'],
            'clients':['ERP iframe','navigateur smartphone Android','navigateur smartphone iOS','PWA installée'],
            'procedure':'docs/pwa-recette-qualification.md',
            'cases':[
                {'id':'AUTH-01','scope':'ERP et mobile','action':'session absente ou expirée','expected':'401, aucun contexte client accepté','businessWrite':False},
                {'id':'AUTH-02','scope':'ERP et mobile','action':'connexion valide / invalide','expected':'200 avec cookie Secure HttpOnly / 401','businessWrite':False},
                {'id':'ROLE-01','scope':'NOTE_DE_FRAIS','action':'Notes + tiers/me + lecture/reconnaissance marchands','expected':'200 et association au porteur du contexte','businessWrite':False},
                {'id':'ROLE-02','scope':'NOTE_DE_FRAIS','action':'PUT/DELETE tiers, alias ou marchand générique','expected':'403, aucune modification','businessWrite':False},
                {'id':'ROLE-03','scope':'rôle sans Notes','action':'menu, iframe et API Notes','expected':'menu absent, guard refuse, API 403','businessWrite':False},
                {'id':'UI-01','scope':'ERP','action':'ouvrir Mobile PWA à droite puis naviguer','expected':'iframe /pwa/, query strings conservées, pas de nouvelle fenêtre imposée','businessWrite':False},
                {'id':'MOB-01','scope':'Android et iOS','action':'connexion autonome puis installation et réouverture','expected':'HTTPS valide, scope service worker /pwa/, session réelle','businessWrite':False},
                {'id':'ISO-01','scope':'deux tenants','action':'lire note et justificatif du tenant A avec session B','expected':'403/404, aucun octet privé reçu','businessWrite':False},
                {'id':'ISO-02','scope':'deux sociétés du tenant A','action':'changer de société puis réutiliser URL et cache','expected':'contexte renouvelé, documents hors société refusés','businessWrite':False},
                {'id':'WRITE-01','scope':'visibilité true, écritures false','action':'POST/PUT/DELETE Notes depuis ERP et mobile','expected':'403, aucune ligne ou pièce modifiée','businessWrite':False},
                {'id':'WRITE-02','scope':'compte et données de test approuvés','action':'création/modification avec JPEG PNG PDF','expected':'succès limité aux droits du compte, hash identique après reconnexion','businessWrite':True},
                {'id':'ISO-03','scope':'deux tenants/sociétés','action':'modifier une note étrangère ou remplacer son justificatif','expected':'403/404, hashes et lignes d’origine inchangés','businessWrite':True},
                {'id':'STO-01','scope':'volume privé','action':'inspection UID/GID, modes, liens et capacité','expected':'utilisateur applicatif non root, 0700/0600, pas de lien','businessWrite':False},
                {'id':'BKP-01','scope':'lot complet','action':'backup coordonné et vérification intégrité','expected':'cinq dumps et archive privée, writers repris, lot complet','businessWrite':False},
                {'id':'REST-01','scope':'ressources isolées seulement','action':'restaurer les cinq DB et documents, comparer liens et hashes','expected':'données cohérentes, aucune ressource active référencée','businessWrite':False},
                {'id':'NET-01','scope':'client extérieur Wi-Fi/4G','action':'tester les ports Docker directs connus sans authentification','expected':'API, DB et fronts directs inaccessibles ; seul le HTTPS prévu est exposé','businessWrite':False},
                {'id':'PERM-01','scope':'après qualification','action':'redémarrage standard autorisé puis fin des tests','expected':'paramètres conservés, aucune fermeture, expiration ou suppression automatique','businessWrite':False}]}


def main(argv=None):
    import argparse
    from release_images import release, manifest
    parser = argparse.ArgumentParser(prog='./wavy pwa recette check')
    parser.add_argument('environment'); parser.add_argument('action')
    parser.add_argument('--runtime',action='store_true',help='inspection du daemon local, métadonnées et permissions seulement')
    parser.add_argument('--backup-dir',type=Path,help='vérification locale du lot DB + justificatifs existant')
    parser.add_argument('--plan',action='store_true',help='plan ERP/smartphone, aucun test métier exécuté')
    args = parser.parse_args(argv)
    if (args.environment,args.action)!=('recette','check'):
        raise ValueError('Usage : ./wavy pwa recette check (PREPROD inchangé)')
    root = Path(__file__).resolve().parent.parent
    _, _, images = release(root,'recette')
    state = policy(root,manifest(root/'.env.recette',strict=False),images)
    report = {'environment':'recette','requestedVisibility':state['enabled'],'requestedNotesWrites':state['writes'],
              'decision':'GO configuration' if state['go'] else 'NO-GO activation','missing':list(state['missing']),
              'runtimeVerified':False,'mutations':False}
    if args.backup_dir:
        from recette_documents import verify
        try: report['backup'] = verify(args.backup_dir)
        except (ValueError,OSError,KeyError,tarfile.TarError) as error: report['missing'].append(str(error))
    if args.runtime:
        try:
            local_daemon(); preserve_storage(state); runtime_check(state,images)
            report['runtimeVerified'] = True
        except (ValueError,OSError,subprocess.SubprocessError) as error:
            report['missing'].append(str(error) if isinstance(error,ValueError) else 'Inspection locale refusée')
    if args.plan: report['qualificationPlan'] = qualification_plan(images,state['origin'])
    if report['missing']: report['decision']='NO-GO activation'
    report['activationDecision']='GO technique' if state['go'] and report['runtimeVerified'] and not report['missing'] else 'NO-GO : qualification et runtime requis'
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if not report['missing'] else 1


if __name__ == '__main__':
    import sys
    sys.dont_write_bytecode = True
    try: sys.exit(main())
    except (ValueError,OSError,KeyError,tarfile.TarError) as error:
        print('PWA : '+str(error),file=sys.stderr);sys.exit(1)
