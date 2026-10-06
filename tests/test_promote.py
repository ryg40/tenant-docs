"""Offline tests of the portable snapshot command in temporary repositories."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCLUDES = [line.strip() for line in (ROOT / 'scripts/portable-exclude').read_text().splitlines()
            if line.strip() and not line.lstrip().startswith('#')]
SCRIPTS = ('promote.sh', 'release-policy.sh', 'portable-exclude', 'scan.py',
           'host-values.regex', 'host-values.allow')
IDENTITY = 'tenant-docs portable <portable@example.invalid>'


@unittest.skipUnless(shutil.which('git') and shutil.which('node'), 'needs Git and Node.js')
class PromoteTest(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix='promote-test-'))
        self.addCleanup(shutil.rmtree, self.base)
        self.repo = self.base / 'repo'
        self.repo.mkdir()
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith('GIT_') and key != 'SCAN_LOCAL_DENY'}
        self.env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1',
                        GIT_AUTHOR_NAME='Example', GIT_AUTHOR_EMAIL='example@example.invalid',
                        GIT_COMMITTER_NAME='Example', GIT_COMMITTER_EMAIL='example@example.invalid',
                        PYTHONDONTWRITEBYTECODE='1')
        self.git('init', '-q')
        self.git('symbolic-ref', 'HEAD', 'refs/heads/main')
        self.git('config', 'core.hooksPath', os.devnull)
        self.put('.gitignore', 'scripts/host-values.local.deny\n')
        self.put('scripts/host-values.local.deny', 'synthetic-private-value.invalid\n')
        for name in SCRIPTS:
            shutil.copyfile(ROOT / 'scripts' / name, self.repo / 'scripts' / name)
        self.put('AGENTS.md', 'The spec lives on the development tracker.\n')
        (self.repo / 'CLAUDE.md').symlink_to('AGENTS.md')
        self.put('README.md', 'A public example.\n')
        self.set_version('0.1.0')
        for path in EXCLUDES:
            self.put(path.rstrip('/') + '/example.txt', 'synthetic-private-value.invalid\n')
        self.commit()
        self.source = self.git('rev-parse', 'main')
        self.origin = self.base / 'origin.git'
        self.git('init', '--bare', '-q', str(self.origin))
        self.git('remote', 'add', 'origin', str(self.origin))

    def put(self, name, text):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def git(self, *args):
        result = subprocess.run(['git', *args], cwd=self.repo, env=self.env,
                                capture_output=True, text=True, check=True)
        return result.stdout.strip()

    def commit(self):
        self.git('add', '-A')
        self.git('commit', '-qm', 'Example change')

    def set_version(self, version):
        self.put('package.json', json.dumps({'version': version}) + '\n')
        self.put('package-lock.json', json.dumps({'version': version, 'packages': {'': {'version': version}}}) + '\n')

    def run_promote(self, *args):
        return subprocess.run(['sh', 'scripts/promote.sh', *args], cwd=self.repo,
                              env=self.env, capture_output=True, text=True)

    def promote(self, *args):
        result = self.run_promote(*args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def refused(self, pattern, *args, code=1):
        before = self.git('show-ref')
        result = self.run_promote(*args)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertIn(pattern, result.stderr)
        self.assertEqual(self.git('show-ref'), before, 'a refusal must leave refs unchanged')

    def test_every_excluded_path_is_absent_from_the_built_snapshot(self):
        self.assertEqual(EXCLUDES, ['docs/agents/', '.gitea/'])
        before = self.git('show-ref')
        output = self.promote()
        self.assertEqual(self.git('show-ref'), before)
        tree = next(line.split()[-1] for line in output.splitlines() if 'snapshot tree' in line)
        for path in EXCLUDES:
            with self.subTest(path=path):
                self.assertTrue(self.git('ls-tree', '-r', '--name-only', 'main', '--', path))
                self.assertEqual(self.git('ls-tree', '-r', '--name-only', tree, '--', path), '')
        self.assertIn('no refs changed', output)
        self.promote('--version', '0.1.0')
        self.assertEqual(self.git('rev-parse', 'portable^{tree}'), tree)
        self.assertEqual(self.git('show', 'portable:CLAUDE.md'), 'AGENTS.md')
        self.assertEqual((self.repo / 'CLAUDE.md').read_text(), (self.repo / 'AGENTS.md').read_text())
        self.assertEqual(self.git('ls-tree', 'portable', 'CLAUDE.md').split()[0], '120000')

    def test_bootstrap_and_snapshot_have_neutral_unsigned_history(self):
        self.git('config', 'commit.gpgSign', 'true')
        self.git('config', 'tag.gpgSign', 'true')
        self.git('config', 'gpg.program', 'absent-example-program')
        self.promote('--version', '0.1.0')
        self.assertEqual(self.git('rev-list', '--count', 'portable'), '2')
        self.assertEqual(self.git('show', '-s', '--format=%P', 'portable^'), '')
        self.assertEqual(self.git('show', '-s', '--format=%B', 'portable^'), 'Bootstrap portable')
        self.assertEqual(self.git('ls-tree', '-r', 'portable^'), '')
        self.assertNotIn(self.source, self.git('rev-list', 'portable').splitlines())
        self.assertEqual(self.git('show', '-s', '--format=%B', 'portable'), f'Promote main {self.source}')
        identities = self.git('log', '--format=%an <%ae>%n%cn <%ce>', 'portable').splitlines()
        self.assertEqual(set(identities), {IDENTITY})
        self.assertNotIn('gpgsig', self.git('cat-file', 'commit', 'portable'))
        self.assertEqual(self.git('cat-file', '-t', 'portable-v0.1.0'), 'tag')
        self.assertEqual(self.git('for-each-ref', '--format=%(taggername) <%(taggeremail:trim)>',
                                  'refs/tags/portable-v0.1.0'), IDENTITY)
        self.assertNotIn('SIGNATURE', self.git('cat-file', 'tag', 'portable-v0.1.0'))

    def test_later_promotion_keeps_the_chain_and_removes_deleted_files(self):
        self.promote('--version', '0.1.0')
        old = self.git('rev-parse', 'portable')
        (self.repo / 'README.md').unlink()
        self.set_version('0.1.1')
        self.commit()
        self.promote('--version', '0.1.1')
        self.assertEqual(self.git('rev-parse', 'portable^'), old)
        self.assertEqual(self.git('rev-list', '--count', 'portable'), '3')
        self.assertEqual(self.git('ls-tree', 'portable', '--', 'README.md'), '')
        self.assertEqual(self.git('rev-parse', 'portable-v0.1.0^{commit}'), old)

    def test_explicit_push_and_resume_send_only_main_and_the_named_tag(self):
        release = self.base / 'release.git'
        self.git('init', '--bare', '-q', str(release))
        self.git('remote', 'add', 'release', str(release))
        self.git('config', 'push.followTags', 'true')
        self.promote('--version', '0.1.0')
        before = self.git('for-each-ref', '--format=%(objectname) %(refname)', 'refs/heads/', 'refs/tags/')
        self.promote('--allow-public', '--version', '0.1.0', '--push', '--remote', 'release')
        self.assertEqual(self.git('for-each-ref', '--format=%(objectname) %(refname)', 'refs/heads/', 'refs/tags/'), before)
        refs = {line.split()[1] for line in self.git('ls-remote', '--refs', 'release').splitlines()}
        self.assertEqual(refs, {'refs/heads/main', 'refs/tags/portable-v0.1.0'})
        self.promote('--allow-public', '--version', '0.1.0', '--push', '--remote', 'release')
        self.assertEqual(self.git('for-each-ref', '--format=%(objectname) %(refname)', 'refs/heads/', 'refs/tags/'), before)

    def test_dirty_tree_and_unsafe_options_are_refused(self):
        self.put('untracked.txt', 'A new file.\n')
        self.refused('working tree is not clean')
        (self.repo / 'untracked.txt').unlink()
        self.refused('--push needs --version', '--push')
        for option in ('--force', '--all', '--tags', '--follow-tags', '--mirror', '--root'):
            with self.subTest(option=option):
                self.refused('usage:', option, code=2)

    def test_shallow_repository_is_refused(self):
        self.put('.git/shallow', self.source + '\n')
        self.refused('repository is shallow')

    def test_topic_tree_must_match_main(self):
        self.git('checkout', '-qb', 'topic/example')
        self.put('README.md', 'Different content.\n')
        self.commit()
        self.refused('checkout does not hold the tree of main')

    def test_public_remote_needs_allow_public_without_a_network_call(self):
        self.git('remote', 'add', 'github', 'https://github.com/example/tenant-docs.git')
        tools = self.base / 'bin'
        tools.mkdir()
        gh = tools / 'gh'
        gh.write_text('#!/bin/sh\nprintf "false\\n"\n')
        gh.chmod(0o755)
        self.env['PATH'] = str(tools) + os.pathsep + self.env['PATH']
        self.refused('public releases need --allow-public', '--version', '0.1.0', '--push')

    def test_package_versions_and_increasing_tags_are_required(self):
        self.refused('differs from package version', '--version', '0.2.0')
        self.put('package-lock.json', json.dumps({'version': '0.1.1', 'packages': {'': {'version': '0.1.0'}}}))
        self.commit()
        self.refused('versions differ', '--version', '0.1.0')
        self.set_version('0.1.0')
        self.commit()
        self.promote('--version', '0.1.0')
        self.refused('tag portable-v0.1.0 exists', '--version', '0.1.0')
        self.set_version('0.0.9')
        self.commit()
        self.refused('does not increase', '--version', '0.0.9')

    def test_missing_deny_and_snapshot_findings_leave_refs_unchanged(self):
        (self.repo / 'scripts/host-values.local.deny').unlink()
        self.refused('public snapshot scan failed')
        self.put('scripts/host-values.local.deny', 'synthetic-private-value.invalid\n')
        self.put('README.md', 'synthetic-private-value.invalid\n')
        self.commit()
        self.refused('public snapshot scan failed', '--version', '0.1.0')

    def test_complete_history_scan_checks_content_missing_from_the_candidate_tree(self):
        self.promote('--version', '0.1.0')
        self.put('scripts/host-values.local.deny', 'A public example.\n')
        self.put('README.md', 'A changed public example.\n')
        self.set_version('0.1.1')
        self.commit()
        self.refused('complete candidate history scan failed', '--version', '0.1.1')

    def test_unchanged_dry_run_still_scans_the_complete_history(self):
        self.promote('--version', '0.1.0')
        self.put('README.md', 'A changed public example.\n')
        self.set_version('0.1.1')
        self.commit()
        self.promote('--version', '0.1.1')
        self.put('scripts/host-values.local.deny', 'A public example.\n')
        self.refused('complete candidate history scan failed')

    def test_remote_development_history_cannot_receive_a_release(self):
        release = self.base / 'release.git'
        self.git('init', '--bare', '-q', str(release))
        self.git('remote', 'add', 'release', str(release))
        self.git('push', '-q', 'release', 'refs/heads/main:refs/heads/main')
        self.refused('remote branch is not an ancestor', '--allow-public', '--version', '0.1.0',
                     '--push', '--remote', 'release')
        self.assertEqual(self.git('ls-remote', '--refs', 'release').split()[0], self.source)

    def test_invalid_exclude_list_is_refused(self):
        self.put('scripts/portable-exclude', '../README.md\n')
        self.commit()
        self.refused('invalid exclude list')

    def test_checked_out_portable_and_invalid_history_are_refused(self):
        self.promote('--version', '0.1.0')
        self.git('worktree', 'add', '-q', str(self.base / 'portable'), 'portable')
        self.refused('has portable checked out')
        self.git('worktree', 'remove', str(self.base / 'portable'))
        self.git('update-ref', 'refs/heads/portable', self.source)
        self.refused('invalid portable history')

    def test_upstream_and_git_replacement_refs_are_refused(self):
        self.git('remote', 'add', 'upstream', str(self.origin))
        self.refused('remote named upstream')
        self.git('remote', 'remove', 'upstream')
        self.promote('--version', '0.1.0')
        self.git('replace', self.git('rev-parse', 'portable'), self.source)
        self.refused('replacement refs refused')


if __name__ == '__main__':
    unittest.main()
