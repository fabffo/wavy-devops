#!/usr/bin/env python3
"""Protection Nginx avec Docker simulé ; aucun daemon, VM ou dépôt applicatif."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
MOCK = r'''
sleep() { printf 'sleep %s\n' "$*" >> "$MOCK_LOG"; }
docker() {
  printf 'docker %s\n' "$*" >> "$MOCK_LOG"
  local call="$*" container="${@: -1}" post=false
  [[ ! -f "$MOCK_LOG.reloaded" ]] || post=true
  if [[ "$1" == inspect ]]; then
    if [[ "$MOCK_CASE" == shell_absent && "$container" == wavy-erp-shell-preprod ]] ||
       [[ "$MOCK_CASE" == gateway_absent && "$container" == wavy-gateway-preprod ]]; then return 1; fi
    case "$3" in
      '{{.State.Running}}')
        if [[ "$MOCK_CASE" == shell_stopped && "$container" == wavy-erp-shell-preprod ]] ||
           [[ "$MOCK_CASE" == gateway_stopped && "$container" == wavy-gateway-preprod ]] ||
           [[ "$MOCK_CASE" == post_shell_stopped && "$container" == wavy-erp-shell-preprod && "$post" == true ]]; then echo false; else echo true; fi ;;
      *Health.Status*)
        if [[ "$container" == wavy-gateway-preprod && ( "$MOCK_CASE" == gateway_unhealthy || ( "$MOCK_CASE" == post_gateway_unhealthy && "$post" == true ) ) ]] ||
           [[ "$container" == wavy-erp-shell-preprod && "$MOCK_CASE" == post_shell_unhealthy && "$post" == true ]]; then echo unhealthy
        elif [[ "$MOCK_CASE" == health_missing ]]; then echo missing
        elif [[ "$MOCK_CASE" == health_timeout ]]; then echo starting
        elif [[ "$MOCK_CASE" == starting_once && ! -f "$MOCK_LOG.ready" ]]; then touch "$MOCK_LOG.ready"; echo starting
        else echo healthy; fi ;;
      '{{.Image}}') echo image-id ;;
      '{{.Config.Image}}') echo "ghcr.io/fake/wavy-$component@sha256:$(printf 'a%.0s' {1..64})" ;;
      *) return 97 ;;
    esac
    return 0
  fi
  if [[ "$1 $2" == 'image inspect' ]]; then
    [[ "$call" != *org.opencontainers* ]] || { echo abc1234; return; }
    echo image-id; return
  fi
  if [[ "$1 $2" == 'image tag' ]]; then return 0; fi
  if [[ "$1 $2" == 'info --format' ]]; then echo /tmp; return; fi
  if [[ "$1" != exec ]]; then return 97; fi
  shift 2
  case "$1" in
    getent)
      [[ "$MOCK_CASE" != dns_failure && !( "$MOCK_CASE" == post_dns_failure && "$post" == true ) ]] || return 1
      echo '172.18.0.18 wavy-gateway-preprod' ;;
    nginx)
      if [[ "$2" == -t ]]; then [[ "$MOCK_CASE" != config_failure ]]; return; fi
      [[ "$MOCK_CASE" != reload_failure ]] || return 1
      touch "$MOCK_LOG.reloaded" ;;
    wget)
      if [[ "$call" == *127.0.0.1/api/tiers/health* ]]; then
        [[ "$MOCK_CASE" != proxy_failure ]] || return 1
        if [[ "$MOCK_CASE" == proxy_retry && ! -f "$MOCK_LOG.retried" ]]; then touch "$MOCK_LOG.retried"; return 1; fi
        [[ "$MOCK_CASE" != proxy_html ]] || { echo '<html>SPA</html>'; return; }
        echo '{"module":"wavy-tiers-api","status":"OK"}'
      elif [[ "$call" == *actuator/health* ]]; then
        [[ "$MOCK_CASE" != http_failure && !( "$MOCK_CASE" == post_http_failure && "$post" == true ) ]] || return 1
        [[ "$MOCK_CASE" != health_down && !( "$MOCK_CASE" == post_health_down && "$post" == true ) ]] || { echo '{"status":"DOWN"}'; return; }
        echo '{"status": "UP"}'
      else echo front; fi ;;
    *) return 97 ;;
  esac
}
'''
RELEASE_MOCK = r'''
preprod_host_guard() { :; }
preprod_container_guard() { :; }
preprod_verify_image() { :; }
preprod_wait() { :; }
verify_image_digest() { :; }
component_version() { echo 0.1.0-abc1234; }
component_digest() { printf 'sha256:'; printf 'a%.0s' {1..64}; }
get_validated_digest() { component_digest; }
validated_history_file() { echo "$ROOT_DIR/fixture.tsv"; }
component_image() { echo "ghcr.io/fake/wavy-$2:0.1.0-abc1234"; }
record_validated_image() { echo validated >> "$MOCK_LOG"; }
preprod_compose() { printf 'compose %s\n' "$*" >> "$MOCK_LOG"; }
git() { :; }
df() { printf 'Filesystem blocks used available capacity mount\nfixture 99999999 0 99999999 0%% /\n'; }
'''


class Nginx(unittest.TestCase):
    def run_case(self, case='ok', command=None, conditional=False):
        with tempfile.TemporaryDirectory(prefix='wavy-nginx-test-') as tmp:
            root = Path(tmp)
            log = root/'calls'
            env = dict(os.environ, MOCK_LOG=str(log), MOCK_CASE=case)
            if command:
                scripts = root/'scripts'
                scripts.mkdir()
                for name in ('_common.sh', '_preprod.sh', 'release-preprod.sh', 'deploy.sh', 'rollback.sh'):
                    shutil.copyfile(ROOT/'scripts'/name, scripts/name)
                    (scripts/name).chmod(0o700)
                shutil.copyfile(ROOT/'wavy', root/'wavy')
                with (scripts/'_preprod.sh').open('a') as out:
                    out.write(MOCK + RELEASE_MOCK)
                (root/'fixture.tsv').write_text('version\tdigest\tcommit\tdate_validation\n')
                for name in ('validate-preprod-config.sh', 'backup-preprod.sh', 'healthcheck.sh', 'smoke-test.sh'):
                    (scripts/name).write_text('#!/usr/bin/env bash\nprintf "%s\\n" "'+name+'" >> "$MOCK_LOG"\n')
                    (scripts/name).chmod(0o700)
                env.update(WAVY_SMOKE_TENANT_ID='1', WAVY_SMOKE_USER_ID='1', WAVY_SMOKE_COMPANY_ID='1',
                           WAVY_SMOKE_USER='fictional', WAVY_SMOKE_PASSWORD='fictional')
                args = ['bash', str(root/command[0]), *command[1:]]
            else:
                shell = 'source "$1/scripts/_preprod.sh"\n' + MOCK
                if conditional:
                    shell += '\nif preprod_reload_erp_shell_nginx; then exit 0; else exit 42; fi\n'
                else:
                    shell += '\npreprod_reload_erp_shell_nginx\necho completed >> "$MOCK_LOG"\n'
                args = ['bash', '-c', shell, '_', str(ROOT)]
            result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=10)
            calls = log.read_text() if log.exists() else ''
            journal = root/'deployments/preprod.tsv'
            return result, calls, journal.read_text() if journal.exists() else ''

    def test_success_order_and_no_unconditional_sleep(self):
        result, calls, _ = self.run_case()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(calls.index('getent hosts'), calls.index('nginx -t'))
        self.assertLess(calls.index('actuator/health'), calls.index('nginx -t'))
        self.assertLess(calls.index('nginx -t'), calls.index('nginx -s reload'))
        after = calls.split('nginx -s reload', 1)[1]
        self.assertIn('Health.Status', after)
        self.assertIn('actuator/health', after)
        self.assertIn('127.0.0.1/api/tiers/health', after)
        self.assertNotIn('sleep ', calls)

    def test_preconditions_stop_before_reload(self):
        for case in ('shell_absent', 'shell_stopped', 'gateway_absent', 'gateway_stopped',
                     'gateway_unhealthy', 'health_missing', 'health_timeout', 'dns_failure',
                     'http_failure', 'health_down', 'config_failure'):
            with self.subTest(case=case):
                result, calls, _ = self.run_case(case, conditional=True)
                self.assertEqual(result.returncode, 42, result.stderr)
                self.assertIn('Protection Nginx PREPROD', result.stderr)
                self.assertNotIn('nginx -s reload', calls)

    def test_reload_and_postcheck_failures_propagate(self):
        for case in ('reload_failure', 'post_shell_stopped', 'post_shell_unhealthy',
                     'post_gateway_unhealthy', 'post_http_failure', 'post_dns_failure',
                     'post_health_down', 'proxy_failure', 'proxy_html'):
            with self.subTest(case=case):
                result, calls, _ = self.run_case(case, conditional=True)
                self.assertEqual(result.returncode, 42, result.stderr)
                self.assertIn('nginx -s reload', calls)
                self.assertIn('Protection Nginx PREPROD', result.stderr)

    def test_bounded_retry(self):
        for case in ('starting_once', 'proxy_retry'):
            result, calls, _ = self.run_case(case)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(calls.count('sleep 2'), 1)
        _, calls, _ = self.run_case('proxy_failure')
        self.assertEqual(calls.count('127.0.0.1/api/tiers/health'), 30)
        self.assertEqual(calls.count('sleep 2'), 29)

    def test_deploy_rollback_restart_use_helper_before_final_checks(self):
        commands = [
            ['scripts/deploy.sh', 'preprod', 'socle-api'],
            ['scripts/rollback.sh', 'preprod', 'gateway', '0.1.0-abc1234', '--yes'],
            ['scripts/rollback.sh', 'preprod', 'socle-api', '0.1.0-abc1234', '--yes'],
            ['wavy', 'restart', 'preprod', 'socle-api'],
            ['wavy', 'restart', 'preprod', 'gateway'],
            ['scripts/deploy.sh', 'preprod', 'socle-front'],
            ['scripts/deploy.sh', 'preprod', 'erp-shell'],
            ['scripts/deploy.sh', 'preprod', 'pwa'],
        ]
        for command in commands:
            with self.subTest(command=command):
                result, calls, journal = self.run_case(command=command)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(calls.count('nginx -s reload'), 1)
                self.assertLess(calls.index('--force-recreate'), calls.index('nginx -s reload'))
                self.assertLess(calls.index('nginx -s reload'), calls.index('healthcheck.sh'))
                self.assertLess(calls.index('healthcheck.sh'), calls.index('smoke-test.sh'))
                self.assertIn('\tOK\t', journal)
                result, calls, journal = self.run_case('config_failure', command=command)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('smoke-test.sh', calls)
                self.assertNotIn('validated\n', calls)
                self.assertIn('\tKO\t', journal)


if __name__ == '__main__':
    unittest.main()
