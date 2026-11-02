#!/usr/bin/env python3
"""Audit local de clé IA ; aucun appel fournisseur, secret ou empreinte dans le JSON."""
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import termios
import unicodedata

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1] if __file__ != '<stdin>' else Path.cwd()
sys.path.insert(0, str(ROOT / 'scripts'))
KEY = 'WAVY_AI_API_KEY'
CLASS = 'BOOT-INF/classes/fr/wavy/factures/extractionia/client/AnthropicFactureIaClient.class'


def run(args, **kwargs):
    result = subprocess.run(args, capture_output=True, timeout=30, **kwargs)
    if result.returncode:
        raise ValueError('Commande de lecture indisponible ; détails masqués.')
    return result.stdout


def local_guard():
    if os.environ.get('DOCKER_HOST') or os.environ.get('DOCKER_CONTEXT'):
        raise ValueError('Contexte Docker distant refusé.')
    context = json.loads(run(['docker', 'context', 'inspect']))[0]
    if context['Endpoints']['docker']['Host'] != 'unix:///var/run/docker.sock':
        raise ValueError('Socket Docker système local requis.')


def parse_env(entries):
    values = {}
    duplicates = set()
    for entry in entries:
        if '=' not in entry:
            continue
        key, value = entry.split('=', 1)
        if key in values:
            duplicates.add(key)
        values[key] = value
    return values, duplicates


def key_hygiene(value):
    # Aucun préfixe/suffixe, longueur ou empreinte n'est publié.
    return {
        'present': bool(value),
        'blank': not value or value.isspace(),
        'leadingWhitespace': bool(value and value[0].isspace()),
        'trailingWhitespace': bool(value and value[-1].isspace()),
        'whitespaceAnywhere': any(c.isspace() for c in value),
        'carriageReturnOrNewline': '\r' in value or '\n' in value,
        'invisibleOrControl': any(unicodedata.category(c) in ('Cc', 'Cf', 'Zl', 'Zp') for c in value),
        'nonAscii': not value.isascii(),
        'literalEscapedWhitespace': any(v in value for v in (r'\r', r'\n', r'\t')),
        'quoteAtBoundary': bool(value and (value[0] in "\"'" or value[-1] in "\"'")),
        'unresolvedInterpolation': bool(re.search(r'\$\{[^}]*\}|\$[A-Za-z_]', value)),
        'looksLikeAnthropicApiKey': value.startswith('sk-ant-api'),
    }


def safe_identity(values):
    provider, model = values.get('WAVY_AI_PROVIDER', ''), values.get('WAVY_AI_MODEL', '')
    return {
        'provider': provider if provider.lower() in ('anthropic', 'none', '') else 'autre (masqué)',
        'model': model if re.fullmatch(r'claude-[A-Za-z0-9._-]{1,100}', model) else ('présent (masqué)' if model else 'absent'),
    }


def intended_environment(root, environment):
    if environment == 'preprod':
        import preprod_config
        command, clean = preprod_config.compose_args(root / '.env.preprod', ['config', '--format', 'json'])
        config = json.loads(run(command, env=clean))
        name = 'wavy-factures-api-preprod'
    else:
        from release_images import recette_compose
        config = recette_compose(root, ['config', '--format', 'json'], capture=True)
        name = 'wavy-factures-api-recette'
    # Défaire uniquement l'échappement de sérialisation Compose ; jamais strip sur la clé.
    return {k: str(v or '').replace('$$', '$') for k, v in config['services'][name]['environment'].items()}


def dotenv_shape(root, environment):
    path = root / ('.env.preprod' if environment == 'preprod' else '.env.recette')
    if not path.is_file():
        return {'available': False}
    text = path.read_bytes().decode('utf-8')
    count = sum(bool(re.match(r'^\s*(?:export\s+)?WAVY_AI_API_KEY\s*=', line)) for line in text.splitlines())
    return {'available': True, 'keyAssignments': count, 'fileContainsCrlf': '\r\n' in text,
            'fileStartsWithBom': text.startswith('\ufeff')}


def audit(root, environment):
    local_guard()
    container = 'wavy-factures-api-' + ('preprod' if environment == 'preprod' else 'recette')
    obj = json.loads(run(['docker', 'inspect', container]))[0]
    if not obj.get('State', {}).get('Running'):
        raise ValueError('Conteneur Factures arrêté ; aucun démarrage effectué.')
    if run(['docker', 'exec', container, 'cat', '/proc/1/comm']).strip() != b'java':
        raise ValueError('Le processus PID 1 ne peut pas être confirmé comme Java.')
    configured, config_duplicates = parse_env(obj['Config'].get('Env', []))
    # Lire l'environnement hérité par le processus PID 1, pas celui d'un nouveau shell.
    raw = run(['docker', 'exec', container, 'cat', '/proc/1/environ'])
    process, process_duplicates = parse_env(raw.decode('utf-8').split('\0'))
    key = process.get(KEY, '')
    report = {'readOnly': True, 'environment': environment, 'providerRequestExecuted': False,
              'javaProcessVerified': True,
              'identity': safe_identity(process), 'keyHygiene': key_hygiene(key),
              'dockerConfigEqualsProcessKey': hmac.compare_digest(configured.get(KEY, '').encode(), key.encode()),
              'duplicateKeyInConfigOrProcess': KEY in config_duplicates or KEY in process_duplicates,
              'imageId': obj['Image'], 'dotenv': dotenv_shape(root, environment)}
    try:
        desired = intended_environment(root, environment)
        report['intendedConfiguration'] = {'available': True, 'identity': safe_identity(desired),
            'keyHygiene': key_hygiene(desired.get(KEY, '')),
            'sameKeyAsProcess': hmac.compare_digest(desired.get(KEY, '').encode(), key.encode()),
            'sameProviderAsProcess': desired.get('WAVY_AI_PROVIDER', '') == process.get('WAVY_AI_PROVIDER', ''),
            'sameModelAsProcess': desired.get('WAVY_AI_MODEL', '') == process.get('WAVY_AI_MODEL', '')}
    except Exception:
        report['intendedConfiguration'] = {'available': False, 'details': 'Rendu indisponible ; valeurs et erreurs brutes masquées.'}
    overrides = ('SPRING_APPLICATION_JSON', 'SPRING_CONFIG_LOCATION', 'SPRING_CONFIG_ADDITIONAL_LOCATION',
                 'SPRING_CONFIG_IMPORT', 'WAVY_AI_APIKEY')
    report['overridePresence'] = {k: bool(process.get(k)) for k in overrides}
    args = [str(v) for v in (obj['Config'].get('Cmd') or []) + (obj['Config'].get('Entrypoint') or [])]
    jvm_options = ' '.join([*args, process.get('JAVA_TOOL_OPTIONS', ''), process.get('JDK_JAVA_OPTIONS', '')])
    report['jvmAiOrSpringOverridePresent'] = bool(re.search(r'wavy[._-]ai|spring[._-](?:config|application)', jvm_options, re.I))
    report['networkHints'] = {k: bool(process.get(k)) for k in ('HTTPS_PROXY', 'HTTP_PROXY', 'ALL_PROXY')}
    report['networkHints']['jvmProxyOrTruststoreSettingPresent'] = bool(re.search(r'(?:https?\.proxy|java\.net\.useSystemProxies|javax\.net\.ssl\.trustStore)', jvm_options))
    try:
        bytecode = run(['docker', 'exec', container, 'unzip', '-p', '/app/app.jar', CLASS])
        report['requestContract'] = {
            'evidence': 'constantes du client dans le JAR actif ; aucune requête réseau interceptée ou exécutée',
            'endpoint': 'https://api.anthropic.com/v1/messages',
            'reviewedConstantsPresent': all(v in bytecode for v in
                (b'https://api.anthropic.com/v1', b'/messages', b'x-api-key', b'anthropic-version', b'2023-06-01')),
            'artifactOverridePresent': any(m.get('Destination') == '/app/app.jar' for m in obj.get('Mounts', []))}
    except Exception:
        report['requestContract'] = {'evidenceAvailable': False}
    eligible = bool(key and not key.isspace() and not report['duplicateKeyInConfigOrProcess'])
    return report, key.encode('utf-8'), eligible


def response_for(key, challenge):
    if not re.fullmatch(r'[0-9a-f]{64}', challenge):
        raise ValueError('Défi invalide.')
    return hmac.new(key, b'wavy-ai-key-equality-v1\0' + bytes.fromhex(challenge), hashlib.sha256).hexdigest()


def read_hidden(terminal, prompt):
    # Échec fermé : contrairement à getpass, aucun repli vers une saisie en écho.
    with open('/dev/tty', 'r') as reader:
        settings = termios.tcgetattr(reader.fileno())
        hidden = settings.copy()
        hidden[3] &= ~termios.ECHO
        termios.tcsetattr(reader.fileno(), termios.TCSAFLUSH, hidden)
        try:
            terminal.write(prompt); terminal.flush()
            value = reader.readline()
            if not value:
                raise ValueError('Comparaison interrompue.')
            return value.rstrip('\r\n')
        finally:
            termios.tcsetattr(reader.fileno(), termios.TCSAFLUSH, settings)
            terminal.write('\n'); terminal.flush()


def interactive_compare(key, environment, challenge=None):
    # Ne jamais émettre de preuve dans stdout, un fichier, un argument ou un journal.
    if os.environ.get('TERM') in (None, '', 'dumb'):
        raise ValueError('Terminal interactif requis pour la comparaison.')
    with open('/dev/tty', 'w', buffering=1) as terminal:
        if not terminal.isatty():
            raise ValueError('Terminal interactif requis.')
        if challenge:
            response = response_for(key, challenge)
            try:
                terminal.write('\x1b[?1049h\x1b[2J\x1b[H')
                terminal.write('Preuve temporaire à transférer uniquement dans la saisie masquée MSI.\nNe pas enregistrer, capturer ou envoyer dans le chat.\n\n' + response + '\n\n')
                terminal.flush()
                read_hidden(terminal, 'Après transfert, Entrée pour effacer cet écran : ')
            finally:
                terminal.write('\x1b[2J\x1b[H\x1b[?1049l'); terminal.flush()
            return {'proofDisplayedOnTemporaryTerminalOnly': True, 'sameKeyAsPeer': 'non déterminé sur cet hôte'}
        challenge = secrets.token_hex(32)
        terminal.write('Défi NON SECRET à utiliser sur l’autre machine :\n' + challenge + '\n')
        terminal.write('Commande sur cet autre hôte : python3 -B scripts/diagnose-anthropic-key.py --environment recette --challenge ' + challenge + '\n')
        terminal.flush()
        other = read_hidden(terminal, 'Preuve temporaire de l’autre hôte (saisie masquée) : ')
        if not re.fullmatch(r'[0-9a-f]{64}', other):
            raise ValueError('Preuve invalide ; aucune comparaison publiée.')
        return {'sameKeyAsPeer': hmac.compare_digest(response_for(key, challenge), other),
                'comparison': 'HMAC-SHA256 sur défi aléatoire unique ; octets exacts UTF-8, sans normalisation'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment', choices=('msi', 'recette', 'preprod'), required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--compare', action='store_true')
    modes.add_argument('--challenge', help='Défi public de 64 caractères hexadécimaux fourni par MSI ; jamais une clé')
    args = parser.parse_args()
    try:
        if args.challenge and not re.fullmatch(r'[0-9a-f]{64}', args.challenge):
            raise ValueError('Défi invalide.')
        report, key, eligible = audit(ROOT, args.environment)
        if args.compare or args.challenge:
            if not eligible:
                raise ValueError('Comparaison impossible : clé absente/vide ou définition dupliquée.')
            result = interactive_compare(key, args.environment, args.challenge)
            if args.compare:
                print('Clés identiques' if result['sameKeyAsPeer'] else 'Clés différentes')
        else:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (Exception, KeyboardInterrupt):
        print(json.dumps({'readOnly': True, 'providerRequestExecuted': False,
                          'error': 'Diagnostic indisponible ou comparaison interrompue ; détails masqués. Aucun changement effectué.'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
