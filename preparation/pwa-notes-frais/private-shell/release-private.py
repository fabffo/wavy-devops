#!/usr/bin/env python3
"""Orchestrateur privé candidat. Inactif sans --execute-on-approved-host."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import sys
import time
import uuid

sys.dont_write_bytecode = True
P = Path(__file__).resolve().parent
ROOT = P.parents[2]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

public = load(P.parent/'scripts/release_pwa_preprod.py', 'private_shared_release')
op = public.operation
fingerprint = public.fingerprint
now = public.now
ORDER = public.ORDER
PROFILE = 'private-tunnel-v1'
PREREQUISITES = ['approved-maintenance', 'rollback-schema-compatible', 'synthetic-data-only',
                 'session-isolation-plan', 'backup-key-available', 'isolated-restore-capacity']
FUNCTIONAL = ['session-isolation', 'company-switch', 'jpeg-png-pdf', 'real-ai-extraction',
              'note-create-update', 'attachment-reload', 'erp-consultation', 'client-cleanup']


def read_plan():
    plan = public.config.read_plan(P.parent/'release-plan.json')
    # Les exigences HTTPS du plan public ne sont ni supprimées ni certifiées ici.
    plan['privateProfile'] = PROFILE
    return plan


class Engine(public.Engine):
    def evidence(self, proof, checks, backup=None):
        self.attest(proof, checks)
        if (proof.get('profile') != PROFILE or proof.get('run') != self.run_id
                or proof.get('origin') != 'http://localhost:24443'):
            raise ValueError('Preuve privée hors run/origine')
        if backup is not None and proof.get('backup') != backup:
            raise ValueError('Preuve de restauration hors sauvegarde')

    def step(self, name, function, *args):
        # Une interruption avant/après l'effet laisse un pointeur durable. La reprise
        # est explicite, jamais une réexécution silencieuse d'une mutation ambiguë.
        self.state['pending'] = name; self.save()
        result = self.operation(name, function, *args)
        self.state['pending'] = None; self.save()
        return result

    def closed(self):
        self.state['closureConfirmed'] = False; self.save()
        self.backend.close()
        self.state['closureConfirmed'] = True; self.save()

    def prepare(self, proof):
        self.require_phase(('reserved',))
        self.evidence(proof, PREREQUISITES)
        self.state['prerequisites'] = proof; self.save()
        self.step('preflight', self.backend.preflight, self.plan)
        self.step('verify-images', self.backend.images, self.plan)
        self.state['previous'] = self.step('snapshot', self.backend.snapshot, self.plan); self.save()
        # Barrière d'entrée avant backup/provision/API : image Shell actuelle conservée.
        self.state['mutationStarted'] = True; self.save()
        self.step('install-barrier', self.backend.barrier, self.state['previous'])
        self.closed()
        self.state['baseline'] = self.step('baseline-backup', self.backend.backup, True); self.save()
        # Le backup a pu durer : ne pas antidater ni rajeunir des contrôles anciens.
        checked_at = time.time()
        self.evidence(self.state['prerequisites'], PREREQUISITES)
        self.step('preflight', self.backend.preflight, self.plan)
        self.closed()
        self.evidence(self.state['prerequisites'], PREREQUISITES)
        self.state['phase'] = 'preparing'
        self.state['storagePreconditions'] = {
            'run': self.run_id, 'checkedAt': checked_at, 'closed': True, 'preflight': True,
            'snapshotHash': fingerprint(self.state['previous']), 'attempt': uuid.uuid4().hex}
        self.save()
        # issue/consume/claim_once restent ceux de V3, pas une copie ni un timestamp autonome.
        self.state['pending'] = 'provision-storage'; self.save()
        fd = public.storage_auth.issue(self.directory, self.reservation, self.run_id, self.plan)
        try:
            self.operation('provision-storage', self.backend.provision_storage, fd)
        finally:
            os.close(fd)
            receipt = self.directory/'storage-authorization.json'
            if op.read_private(receipt).get('action') == 'provision-storage':
                op.atomic_json(receipt, {'invalidated': True, 'run': self.run_id})
        self.state['pending'] = None; self.save()
        self.step('storage', self.backend.storage)
        self.state['backup'] = self.step('backup', self.backend.backup, False)
        self.state['phase'] = 'awaiting-restore'; self.save()

    def restore(self, proof=None):
        self.require_phase(('awaiting-restore',))
        self.closed()
        result = self.step('isolated-restore', self.backend.restore, self.state['backup'])
        self.evidence(result, ['five-databases', 'contracts-and-notes', 'hmac', 'catalogues',
                               'document-hashes', 'notes-permissions'], self.state['backup'])
        self.state['restore'] = result
        self.state['phase'] = 'restored'; self.save()

    def deploy(self, proof=None):
        self.require_phase(('restored',))
        self.evidence(self.state['prerequisites'], PREREQUISITES)
        self.evidence(self.state['restore'], ['five-databases', 'contracts-and-notes', 'hmac',
                                             'catalogues', 'document-hashes', 'notes-permissions'], self.state['backup'])
        self.closed()
        self.step('preflight', self.backend.preflight, self.plan)
        self.step('verify-images', self.backend.images, self.plan)
        self.step('verify-backup', self.backend.verify_backup, self.state['backup'])
        self.step('storage', self.backend.storage)
        self.state['observed'] = {}; self.state['completed'] = []; self.save()
        for component in ORDER:
            self.state['mutationStarted'] = True; self.save()
            self.step('deploy-'+component, self.backend.deploy, component, self.plan, 'closed')
            self.backend.healthy(component)
            self.state['observed'][component] = self.backend.observed(component, self.plan)
            self.state['completed'].append(component); self.save()
        self.step('erp-checks', self.backend.checks)
        self.closed()
        self.state['preparedAt'] = now(); self.state['phase'] = 'prepared'; self.save()

    def open_test(self, proof):
        self.require_phase(('prepared',))
        self.evidence(proof, ['approved-test-session', 'synthetic-data-only'])
        if proof.get('observed') != self.state['observed'] or proof.get('backup') != self.state['backup']:
            raise ValueError('Autorisation de test hors cohorte')
        self.evidence(self.state['prerequisites'], PREREQUISITES)
        self.evidence(self.state['restore'], ['five-databases','contracts-and-notes','hmac','catalogues',
                                             'document-hashes','notes-permissions'], self.state['backup'])
        self.closed(); self.verify_current()
        self.backend.verify_backup(self.state['backup']); self.backend.storage(); self.backend.checks()
        self.evidence(self.state['prerequisites'], PREREQUISITES)
        self.evidence(self.state['restore'], ['five-databases','contracts-and-notes','hmac','catalogues',
                                             'document-hashes','notes-permissions'], self.state['backup'])
        self.evidence(proof, ['approved-test-session', 'synthetic-data-only'])
        deadlines=[datetime.fromisoformat(item['checkedAt']).timestamp()+86400
                   for item in (proof,self.state['prerequisites'],self.state['restore'])]
        proof=dict(proof,notAfter=min(deadlines))
        self.state['phase'] = 'testing'; self.state['testStartedAt'] = now(); self.state['testOwnerPid'] = os.getpid(); self.save()
        # Reste au premier plan et sous flock. Parent death + lease dans le gate.
        try:
            self.step('test-window', self.backend.test_window, proof)
        finally:
            self.closed()
        self.state['phase'] = 'tested'; self.state['testClosedAt'] = now(); self.save()

    def validate(self, proof):
        self.require_phase(('tested',))
        self.closed(); self.verify_current()
        self.evidence(proof, FUNCTIONAL, self.state['backup'])
        if (proof.get('observed') != self.state['observed'] or
                datetime.fromisoformat(proof['checkedAt']) < datetime.fromisoformat(self.state['testClosedAt'])):
            raise ValueError('Preuve fonctionnelle antérieure à la fermeture')
        self.backend.checks()
        self.state['validation'] = proof; self.state['phase'] = 'validated'; self.save()

    def close(self, proof=None):
        self.closed()
        if self.state['phase'] == 'testing':
            self.state['phase'] = 'tested'; self.state['testClosedAt'] = now()
        self.save()

    def resume(self, proof):
        self.require_phase(('failed', 'preparing', 'reserved', 'awaiting-restore', 'restored',
                            'testing', 'prepared', 'tested', 'validated'))
        self.closed()
        # Pas de rejeu provision/backup/deploy à l'aveugle après SIGKILL. Le relecteur
        # atteste la classification exacte de l'étape interrompue ; snapshot conservé.
        self.evidence(proof, ['interrupted-effect-inspected'])
        if proof.get('pending') != self.state.get('pending'):
            raise ValueError('Reprise hors étape interrompue')
        target = proof.get('resumePhase')
        if target not in ('awaiting-restore','restored','prepared','tested'):
            raise ValueError('Point de reprise non sûr')
        if not self.state.get('backup'): raise ValueError('Sauvegarde complète requise ; rollback/abandon explicite')
        self.backend.verify_backup(self.state['backup'])
        if target in ('restored','prepared','tested'):
            self.evidence(self.state.get('restore', {}), ['five-databases','contracts-and-notes','hmac',
                          'catalogues','document-hashes','notes-permissions'], self.state['backup'])
        if target in ('prepared','tested'): self.verify_current(); self.backend.checks()
        self.state.pop('validation', None)
        if target == 'tested':
            if not self.state.get('testStartedAt'): raise ValueError('Test jamais ouvert')
            self.state['testClosedAt'] = now()
        self.state['phase'] = target; self.state['pending'] = None; self.save()

    def rollback(self, proof=None):
        if self.state.get('previous') is None: raise ValueError('Snapshot absent')
        self.closed()
        self.evidence(proof or self.state['prerequisites'], ['rollback-schema-compatible'])
        self.backend.images(self.state['previous'])
        self.state['phase'] = 'rolling-back'; self.save()
        # Shell TOUJOURS démarré avec la barrière privée, jamais --no-start.
        for component in ORDER:
            self.step('rollback-'+component, self.backend.deploy, component, self.state['previous'], 'rollback')
            self.backend.healthy(component); self.backend.observed(component, self.state['previous'])
            self.closed()
        self.backend.checks(); self.closed()
        self.state['phase'] = 'rolled-back'; self.save()

    def abandon(self, proof=None):
        self.closed()
        if self.state['mutationStarted'] and self.state['phase'] not in ('rolled-back','validated'):
            raise ValueError('Rollback ou validation complète requis')
        self.backend.checks()
        self.state['phase'] = 'abandoned'; self.save()
        op.atomic_json(self.directory/('archive-'+self.run_id+'.json'), self.state)
        self.owner.release(self.run_id)

    def run(self, action, evidence=None, run_id=None):
        # Operation est aussi le contrat des commandes actives. Refus concurrent/hors
        # propriétaire AVANT toute fermeture de la session de l'autre opération.
        with op.Operation(self.backend.root, owner=run_id) as owner:
            self.owner = owner; self.backend.lock_fd = owner.fd
            if action == 'reserve':
                self.backend.host_guard()
                if self.path.exists() and op.read_private(self.path).get('phase') != 'abandoned':
                    raise ValueError('État antérieur non abandonné')
                self.run_id = self.backend.run_id = uuid.uuid4().hex
                owner.reserve(self.run_id, fingerprint(self.plan), now())
                self.state = {'run': self.run_id, 'profile': PROFILE, 'planHash': fingerprint(self.plan),
                              'phase':'reserved', 'previous':None, 'observed':{}, 'completed':[],
                              'mutationStarted':False, 'closureConfirmed':False,
                              'configurationHash':self.backend.identity(), 'pending':None}
                self.save()
                return self.run_id
            self.run_id = self.backend.run_id = run_id
            reserved = op.read_private(self.reservation)
            if not run_id or reserved['run'] != run_id or reserved['planHash'] != fingerprint(self.plan):
                raise ValueError('Run/plan incompatible')
            self.state = None
            try:
                # Propriétaire établi avant de fermer ; aucun besoin de Docker ou de
                # charger un état éventuellement interrompu pour retirer le socket.
                if action != 'status': self.backend.close_socket()
                self.state = op.read_private(self.path)
                if (self.state['run'] != run_id or self.state.get('profile') != PROFILE
                        or self.state['planHash'] != fingerprint(self.plan)):
                    raise ValueError('État/profil incompatible')
                if action == 'status':
                    return {key:self.state[key] for key in ('run','profile','planHash','phase','pending','backup',
                            'observed','testStartedAt','testClosedAt','testOwnerPid') if key in self.state}
                self.backend.host_guard()
                # Fermer AVANT lecture de preuve/config : une preuve illisible ne laisse
                # jamais l'ancien test ouvert. Les refus de propriétaire restent hors try.
                self.backend.close_socket()
                if self.state['configurationHash'] != self.backend.identity(): raise ValueError('Configuration modifiée')
                self.backend.select(self.plan)
                proof = op.read_private(evidence) if isinstance(evidence, (str,Path)) else evidence
                self.event(action, 'START')
                getattr(self, action.replace('-', '_'))(proof)
                self.event(action, 'OK')
            except BaseException:
                try:
                    self.backend.close()
                    if self.state: self.state['closureConfirmed'] = True
                except BaseException:
                    if self.state: self.state['closureConfirmed'] = False
                if self.state:
                    self.state['phase'] = 'rollback-failed' if action == 'rollback' else 'failed'
                    self.save(); self.event(action, 'FAILED')
                raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['reserve','prepare','restore','deploy','open-test','validate',
                                         'close','resume','rollback','abandon','status'])
    parser.add_argument('--env', type=Path, default=ROOT/'.env.preprod')
    parser.add_argument('--gate-dir', type=Path, default=Path('/run/wavy-private-pwa-gate'))
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--run-id')
    parser.add_argument('--session-cookie-file', type=Path)
    parser.add_argument('--seconds', type=int, default=900)
    parser.add_argument('--execute-on-approved-host', action='store_true')
    args = parser.parse_args()
    if not args.execute_on_approved_host: parser.exit(2,'Candidat inactif ; exécution explicite requise.\n')
    if (socket.gethostname().split('.')[0] != 'wavy-preprod' or os.environ.get('DOCKER_HOST')
            or os.environ.get('DOCKER_CONTEXT')): parser.exit(2,'Hôte PREPROD local requis.\n')
    if args.action != 'reserve' and not args.run_id: parser.error('--run-id requis')
    for sig in (signal.SIGINT,signal.SIGTERM):
        signal.signal(sig, lambda *_: (_ for _ in ()).throw(InterruptedError()))
    try:
        backend_module = load(P/'private-backend.py','private_backend')
        plan = read_plan()
        directory = ROOT/'deployments/pwa-release'
        backend = backend_module.Backend(args.env.resolve(), directory, args.gate_dir.resolve(),
                                         args.session_cookie_file, args.seconds)
        signal.signal(signal.SIGUSR1, lambda *_: setattr(backend,'stop_requested',True))
        engine = Engine(backend,directory,plan,ROOT/'deployments/preprod.lock')
        result = engine.run(args.action,args.evidence,args.run_id)
        if result: print(json.dumps(result,sort_keys=True,indent=2) if isinstance(result,dict) else result)
        else: print('Action privée terminée ; état/journal privés à vérifier.')
    except BaseException:
        parser.exit(1,'Action privée refusée/échouée ; consulter état privé et fermeture.\n')

if __name__ == '__main__': main()
