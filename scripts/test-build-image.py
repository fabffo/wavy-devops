#!/usr/bin/env python3
"""Tests locaux de build-image : vrais dépôts Git, npm/Maven/Docker simulés."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class BuildImageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='wavy-build-image-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.devops = self.root / 'devops'
        scripts = self.devops / 'scripts'
        scripts.mkdir(parents=True)
        source = Path(__file__).resolve().parent
        for name in ('build-image.sh', '_common.sh'):
            shutil.copy2(source / name, scripts / name)
        (self.devops / 'docker').mkdir()
        (self.devops / 'docker/wavy-pwa.Dockerfile').write_text('FROM scratch\n')
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.log = self.root / 'commands.jsonl'
        mock = '''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ['TEST_COMMAND_LOG'], 'a') as log:
    log.write(json.dumps([name, os.getcwd(), args]) + '\\n')
if name == 'docker':
    if args[:2] == ['image', 'inspect']:
        if '--format' not in args:
            sys.exit(0 if os.environ.get('TEST_TAG_EXISTS') == '1' else 1)
        print('1048576' if args[args.index('--format') + 1] == '{{.Size}}' else 'sha256:test')
if name == os.environ.get('TEST_FAIL_COMMAND', 'WAVY_MAVEN_TEST_ARGS'):
    sys.exit(1)
'''
        for name in ('docker', 'npm', 'mvn'):
            path = self.bin / name
            path.write_text(mock)
            path.chmod(0o755)
        self.env = {**os.environ, 'PATH': f'{self.bin}:{os.environ["PATH"]}', 'TEST_COMMAND_LOG': str(self.log)}
        for key in ('WAVY_BUILD_REPOSITORY', 'TEST_TAG_EXISTS', 'TEST_FAIL_COMMAND', 'WAVY_MAVEN_TEST_ARGS'):
            self.env.pop(key, None)
        self.repo = self.make_repo('wavy-contrats-front', 'contrats-front')

    def git(self, repo, *args):
        return subprocess.check_output(['git', '-C', str(repo), *args], text=True, stderr=subprocess.PIPE).strip()

    def make_repo(self, name, component, java=False):
        repo = self.root / name
        repo.mkdir()
        self.git(repo, 'init', '-q')
        self.git(repo, 'config', 'user.email', 'test@example.invalid')
        self.git(repo, 'config', 'user.name', 'Build test')
        self.git(repo, 'remote', 'add', 'origin', f'https://github.com/fabffo/wavy-{component}.git')
        (repo / 'Dockerfile').write_text('FROM scratch\n')
        (repo / ('pom.xml' if java else 'package-lock.json')).write_text('{}\n')
        self.git(repo, 'add', '.')
        self.git(repo, 'commit', '-qm', 'Fixture')
        return repo

    def run_build(self, repo=None, component='contrats-front', **env):
        run_env = {**self.env, **env}
        if repo is not None:
            run_env['WAVY_BUILD_REPOSITORY'] = str(repo)
        return subprocess.run(['bash', str(self.devops / 'scripts/build-image.sh'), component, '1.2.3'],
                              env=run_env, text=True, capture_output=True)

    def commands(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def assert_build(self, repo, component='contrats-front', override=True):
        result = self.run_build(repo if override else None, component)
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = self.commands()
        builds = [args for name, _, args in commands if name == 'docker' and args[0] == 'build']
        self.assertEqual(len(builds), 1)
        build = builds[0]
        self.assertEqual(build[-1], str(repo))
        dockerfile = self.devops / 'docker/wavy-pwa.Dockerfile' if component == 'pwa' else repo / 'Dockerfile'
        self.assertEqual(build[build.index('--file') + 1], str(dockerfile))
        sha = self.git(repo, 'rev-parse', '--short=7', 'HEAD')
        self.assertIn(f'ghcr.io/fabffo/wavy-{component}:1.2.3-{sha}', build)
        for label in (f'revision={sha}', 'version=1.2.3', f'source=https://github.com/fabffo/wavy-{component}'):
            self.assertIn(f'org.opencontainers.image.{label}', build)
        self.assertFalse(any(args[0] in ('push', 'login') for name, _, args in commands if name == 'docker'))
        npm = [(cwd, args) for name, cwd, args in commands if name == 'npm']
        if component.endswith('-front') or component == 'pwa':
            self.assertEqual(npm, [(str(repo), ['ci']), (str(repo), ['test', '--', '--watch=false']),
                                   (str(repo), ['run', 'build', '--', '--configuration', 'production'])])
        else:
            self.assertIn(['mvn', str(repo), ['test']], commands)

    def test_default_repository(self):
        self.assert_build(self.repo, override=False)

    def test_clean_worktree_with_spaces_and_https_or_ssh_origin(self):
        worktree = self.root / 'clean worktree'
        self.git(self.repo, 'worktree', 'add', '--detach', str(worktree))
        self.assertTrue((worktree / '.git').is_file())
        (self.repo / 'Dockerfile').write_text('FROM changed-in-main-checkout\n')
        for origin in ('https://github.com/fabffo/wavy-contrats-front',
                       'https://github.com/fabffo/wavy-contrats-front.git',
                       'git@github.com:fabffo/wavy-contrats-front',
                       'git@github.com:fabffo/wavy-contrats-front.git',
                       'ssh://git@github.com/fabffo/wavy-contrats-front',
                       'ssh://git@github.com/fabffo/wavy-contrats-front.git'):
            with self.subTest(origin=origin):
                self.log.unlink(missing_ok=True)
                self.git(self.repo, 'remote', 'set-url', 'origin', origin)
                self.assert_build(worktree)

    def test_invalid_sources(self):
        subdir = self.repo / 'subdir'
        subdir.mkdir()
        plain = self.root / 'plain'
        plain.mkdir()
        bare = self.root / 'bare.git'
        subprocess.run(['git', 'init', '--bare', '-q', str(bare)], check=True)
        broken = self.root / 'broken'
        broken.mkdir()
        (broken / '.git').write_text('gitdir: /nonexistent/wavy-test-git-dir\n')
        for repo in (self.root / 'absent', plain, subdir, bare, broken, ''):
            with self.subTest(repo=str(repo)):
                self.assertNotEqual(self.run_build(repo).returncode, 0)
                self.assertEqual(self.commands(), [])

    def test_wrong_origins(self):
        for origin in ('https://github.com/fabffo/wavy-contrats-api.git',
                       'git@github.com:other/wavy-contrats-front.git',
                       'https://github.com.evil.invalid/fabffo/wavy-contrats-front.git',
                       'https://github.com/fabffo/wavy-contrats-front.git/extra'):
            with self.subTest(origin=origin):
                self.git(self.repo, 'remote', 'set-url', 'origin', origin)
                self.assertNotEqual(self.run_build(self.repo).returncode, 0)
                self.assertEqual(self.commands(), [])
        self.git(self.repo, 'remote', 'remove', 'origin')
        self.assertNotEqual(self.run_build(self.repo).returncode, 0)

    def test_dirty_worktree(self):
        worktree = self.root / 'dirty worktree'
        self.git(self.repo, 'worktree', 'add', '--detach', str(worktree))
        for staged in (False, True):
            with self.subTest(staged=staged):
                (worktree / 'Dockerfile').write_text('FROM changed\n')
                if staged:
                    self.git(worktree, 'add', 'Dockerfile')
                result = self.run_build(worktree)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('arbre Git propre', result.stderr)
        self.git(worktree, 'reset', '--hard', 'HEAD')
        (worktree / 'untracked').write_text('test')
        self.assertNotEqual(self.run_build(worktree).returncode, 0)
        self.assertFalse(any(name == 'npm' or args[0] == 'build' for name, _, args in self.commands()))

    def test_local_tag_immutable(self):
        result = self.run_build(self.repo, TEST_TAG_EXISTS='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('tag existe déjà', result.stderr)
        self.assertEqual(len(self.commands()), 1)

    def test_test_failure_blocks_docker_build(self):
        self.assertNotEqual(self.run_build(self.repo, TEST_FAIL_COMMAND='npm').returncode, 0)
        self.assertFalse(any(name == 'docker' and args[0] == 'build' for name, _, args in self.commands()))

    def test_missing_dockerfile(self):
        self.git(self.repo, 'rm', 'Dockerfile')
        self.git(self.repo, 'commit', '-qm', 'No Dockerfile')
        result = self.run_build(self.repo)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Dockerfile introuvable', result.stderr)
        self.assertFalse(any(name == 'docker' and args[0] == 'build' for name, _, args in self.commands()))

    def test_pwa_dockerfile_and_context(self):
        repo = self.make_repo('pwa source', 'pwa')
        self.assert_build(repo, 'pwa')

    def test_java_repository(self):
        repo = self.make_repo('api source', 'contrats-api', java=True)
        self.assert_build(repo, 'contrats-api')

    def java_fixture(self, wrapper):
        repo = self.make_repo('java source', 'factures-api', java=True)
        if wrapper:
            shutil.copy2(self.bin / 'mvn', repo / 'mvnw')
            self.git(repo, 'add', 'mvnw')
            self.git(repo, 'commit', '-qm', 'Wrapper fixture')
        return repo

    def test_maven_exact_args_and_other_steps_unchanged(self):
        args = ['-Dspring.datasource.hikari.maximum-pool-size=10',
                '-Dspring.datasource.hikari.minimum-idle=0',
                '-Dspring.test.context.cache.maxSize=2']
        for wrapper in (False, True):
            with self.subTest(wrapper=wrapper):
                repo = self.java_fixture(wrapper)
                baseline = self.run_build(repo, 'factures-api')
                self.assertEqual(baseline.returncode, 0, baseline.stderr)
                expected = self.commands()
                name = 'mvnw' if wrapper else 'mvn'
                self.assertIn([name, str(repo), ['test']], expected)
                for value, extra in ((" \t".join(args), args), ('', []),
                                     (' \t ', []),
                                     ('-Dspring.datasource.hikari.minimum-idle=00',
                                      ['-Dspring.datasource.hikari.minimum-idle=00'])):
                    self.log.unlink()
                    result = self.run_build(repo, 'factures-api', WAVY_MAVEN_TEST_ARGS=value)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    actual = self.commands()
                    self.assertEqual(actual, [[n, cwd, ['test', *extra] if n == name else a]
                                              for n, cwd, a in expected])
                    self.assertEqual(result.stdout, baseline.stdout)
                shutil.rmtree(repo)
                self.log.unlink()

    def test_maven_invalid_values_and_injection_are_private(self):
        repo = self.java_fixture(True)
        marker = self.root / 'injected'
        invalid = ['-X', '-Dpassword=SECRET_CANARY', 'test',
                   '-Dspring.datasource.hikari.maximum-pool-size=0',
                   '-Dspring.test.context.cache.maxSize=000',
                   '-Dspring.datasource.hikari.minimum-idle=-1']
        for prop in ('spring.datasource.hikari.maximum-pool-size',
                     'spring.datasource.hikari.minimum-idle', 'spring.test.context.cache.maxSize'):
            invalid.extend(f'-D{prop}={v}' for v in ('', '-2', '+1', '1.5', 'abc', '1=2', '１'))
        invalid.extend(['-Dspring.test.context.cache.maxSize=2 ' + suffix for suffix in
                        (f'; touch {marker}', f'$(touch {marker})', f'`touch {marker}`',
                         '*', '"2"', "'2'", '\\', '\n-X', '\r-X', '-Dpassword=SECRET_CANARY')])
        for value in invalid:
            with self.subTest(value=value):
                self.log.unlink(missing_ok=True)
                result = self.run_build(repo, 'factures-api', WAVY_MAVEN_TEST_ARGS=value)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('WAVY_MAVEN_TEST_ARGS invalide', result.stderr)
                self.assertNotIn(value, result.stdout + result.stderr)
                self.assertNotIn('SECRET_CANARY', result.stdout + result.stderr)
                self.assertFalse(marker.exists())
                self.assertFalse(any(n in ('mvn', 'mvnw', 'npm') or a[0] == 'build'
                                     for n, _, a in self.commands()))

    def test_maven_failure_still_blocks_docker_build(self):
        for wrapper in (False, True):
            with self.subTest(wrapper=wrapper):
                repo = self.java_fixture(wrapper)
                self.log.unlink(missing_ok=True)
                result = self.run_build(
                    repo, 'factures-api', TEST_FAIL_COMMAND='mvnw' if wrapper else 'mvn',
                    WAVY_MAVEN_TEST_ARGS='-Dspring.test.context.cache.maxSize=2')
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any(n == 'docker' and a[0] == 'build'
                                     for n, _, a in self.commands()))
                shutil.rmtree(repo)

    def test_frontend_ignores_maven_environment(self):
        baseline = self.run_build(self.repo)
        expected = self.commands()
        self.log.unlink()
        result = self.run_build(self.repo, WAVY_MAVEN_TEST_ARGS='-Dpassword=SECRET_CANARY')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.commands(), expected)
        self.assertEqual(result.stdout, baseline.stdout)
        self.assertNotIn('SECRET_CANARY', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
