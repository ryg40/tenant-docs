"""Tests of scripts/check-version.sh: each form of a release tag, and each exit code.

Each test makes a small Git repository as the source of the project `demo`.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / 'scripts' / 'check-version.sh'

# Git gives these variables to a hook. No command of a test gets them. See tests/test_docgen.py.
GIT_LOCAL = ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR', 'GIT_OBJECT_DIRECTORY',
             'GIT_ALTERNATE_OBJECT_DIRECTORIES', 'GIT_PREFIX', 'GIT_NAMESPACE', 'GIT_CONFIG', 'GIT_CONFIG_COUNT',
             'GIT_CONFIG_PARAMETERS', 'GIT_GRAFT_FILE', 'GIT_IMPLICIT_WORK_TREE', 'GIT_NO_REPLACE_OBJECTS',
             'GIT_REPLACE_REF_BASE', 'GIT_SHALLOW_FILE', 'GIT_INTERNAL_SUPER_PREFIX')

SPEC = importlib.util.spec_from_file_location('release_tag', ROOT / 'docgen' / 'release_tag.py')
release_tag = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_tag)

DATED = ('portable/20260101-1a2b3c4', 'portable/20260103-3c4d5e6')
NUMBERED = ('portable-v1.1.0', 'portable-v1.2.0')


@unittest.skipUnless(shutil.which('git') and shutil.which('node'), 'the script needs git and node')
class CheckVersionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='check-version-test-'))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.source = self.tmp / 'demo'
        self.source.mkdir()
        self.versions = self.tmp / 'versions.json'
        self.env = {name: value for name, value in os.environ.items() if name not in GIT_LOCAL and name != 'DEMO_SOURCE'}
        self.env['VERSIONS_FILE'] = str(self.versions)
        self.clock = 0
        self.git('init', '-q', '-b', 'portable')
        self.git('commit', '-q', '--allow-empty', '-m', 'First commit')

    def git(self, *words, same_time=False):
        # Each commit and each tag is one day later than the one before. `same_time` gives the time of the one before.
        self.clock += 0 if same_time else 1
        date = f'@{1767225600 + self.clock * 86400} +0000'
        env = {**self.env, 'GIT_AUTHOR_DATE': date, 'GIT_COMMITTER_DATE': date}
        done = subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.com', *words],
                              cwd=self.source, capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)

    def release(self, tag, annotated=True, same_time=False):
        if not same_time:
            self.git('commit', '-q', '--allow-empty', '-m', f'Release {tag}')
        self.git('tag', *(('-a', '-m', tag) if annotated else ()), tag, same_time=same_time)

    def newest(self, expected):
        """The script names `expected` as the newest release, and no other tag."""
        self.documented(expected)
        done = self.check()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(f'the documented release {expected} is the newest release', done.stdout)

    def documented(self, release, branch='portable'):
        self.versions.write_text(json.dumps({'demo': {'branch': branch, 'release': release}}))

    def check(self, *words):
        done = subprocess.run(['sh', str(SCRIPT), 'demo', *(words or (str(self.source),))],
                              capture_output=True, text=True, env=self.env)
        # A message never holds the source location.
        self.assertNotIn(str(self.tmp), done.stdout + done.stderr)
        return done

    def test_each_form_of_a_release_tag(self):
        for form, (older, newer) in (('<branch>/<date>-<hash>', DATED), ('<branch>-v<major>.<minor>.<patch>', NUMBERED)):
            for annotated in (True, False):
                with self.subTest(form=form, annotated=annotated):
                    self.setUp()
                    self.release(older, annotated)
                    self.release(newer, annotated)
                    self.documented(newer)
                    done = self.check()
                    self.assertEqual(done.returncode, 0, done.stderr)
                    self.assertIn(f'demo: the documented release {newer} is the newest release of the source.', done.stdout)
                    # The source is ahead of the older release.
                    self.documented(older)
                    done = self.check()
                    self.assertEqual(done.returncode, 1)
                    self.assertIn(f'documented release (src/data/versions.json): {older}', done.stderr)
                    self.assertIn(f'newest release of the source:                {newer}', done.stderr)

    def test_the_source_does_not_hold_the_documented_release(self):
        for absent, present in ((DATED[0], DATED[1]), (NUMBERED[0], NUMBERED[1])):
            with self.subTest(absent=absent):
                self.setUp()
                self.release(present)
                self.documented(absent)
                done = self.check()
                self.assertEqual(done.returncode, 2)
                self.assertIn('does not hold the documented release', done.stderr)

    def test_a_tag_of_another_form_is_not_a_release(self):
        self.release(NUMBERED[0])
        # Each of these tags is newer than the release, and none is a release of the branch `portable`.
        for tag in ('pre-split-2026-01-05', 'portable-v2', 'portable-v2.0', 'portable-v2.0.0.0', 'portable-v2.0.0-rc1',
                    'portable-validated', 'main/20260105-0a0a0a0', 'v9.9.9', 'portable/wip', 'portable/2026010-0a0a0a0',
                    'portable/20260105-0a0a0a', 'portable/20260105-0A0A0A0', 'portable/20260105-wip0000',
                    'portable/20260105', 'portable-v01.02.03', 'portable-v2.00.0', 'portable-v2.0.03', 'xportable-v3.0.0'):
            self.release(tag)
        self.newest(NUMBERED[0])

    def test_a_tag_of_another_form_is_not_a_release_of_the_date_form(self):
        self.release(DATED[0])
        for tag in ('portable/wip', 'portable/99999999', 'portable/20260105-0a0a0a', 'portable/latest-0a0a0a0'):
            self.release(tag)
        self.newest(DATED[0])
        # Only such tags: the source has no release tag.
        self.git('tag', '-d', DATED[0])
        done = self.check()
        self.assertEqual(done.returncode, 2)
        self.assertIn('has no release tag of the branch portable', done.stderr)

    def test_the_newest_version_is_the_highest_number_and_not_the_last_tag(self):
        # A sort by the time of the tag gives v1.9.1. A sort by the name gives v1.9.1 also.
        for tag in ('portable-v1.9.0', 'portable-v1.10.0', 'portable-v1.9.1'):
            self.release(tag)
        self.newest('portable-v1.10.0')
        self.documented('portable-v1.9.1')
        done = self.check()
        self.assertEqual(done.returncode, 1)
        self.assertIn('newest release of the source:                portable-v1.10.0', done.stderr)
        # Each part is a number: 2.0.0 is higher than 1.10.0, and 2.0.10 is higher than 2.0.9.
        for tag in ('portable-v2.0.0', 'portable-v2.0.10', 'portable-v2.0.9', 'portable-v1.11.0'):
            self.release(tag)
        self.newest('portable-v2.0.10')

    def test_two_version_tags_of_the_same_time(self):
        for order in (('portable-v1.2.0', 'portable-v1.10.0'), ('portable-v1.10.0', 'portable-v1.2.0')):
            for annotated in (True, False):
                with self.subTest(order=order, annotated=annotated):
                    self.setUp()
                    self.release(order[0], annotated)
                    self.release(order[1], annotated, same_time=True)
                    self.newest('portable-v1.10.0')

    def test_the_newest_dated_tag_has_the_latest_date_in_its_name(self):
        # The tag with the older date in its name is made last. A sort by the time of the tag gives it.
        self.release('portable/20260110-aaaaaaa')
        self.release('portable/20260105-fffffff')
        self.newest('portable/20260110-aaaaaaa')
        # The same date in the name: the tag that was made last. A sort by the name gives fffffff.
        self.release('portable/20260120-fffffff')
        self.release('portable/20260120-0000000')
        self.newest('portable/20260120-0000000')
        # The same date and the same time: the last name in the order of the characters.
        self.release('portable/20260125-1111111')
        self.release('portable/20260125-2222222', same_time=True)
        self.newest('portable/20260125-2222222')

    def test_a_source_with_both_forms(self):
        # The version form wins, also when a tag of the date form is made later.
        self.release('portable/20260105-0a0a0a0')
        self.release('portable-v1.0.0')
        self.release('portable/20260120-0b0b0b0')
        self.newest('portable-v1.0.0')

    def test_the_rule_as_a_function(self):
        # docgen.py calls this function. The script calls the same file as a command.
        tags = [('portable-v1.9.0', 1), ('portable-v1.10.0', 2), ('portable-v1.9.1', 3), ('portable-validated', 4),
                ('portable/wip', 5), ('portable-v01.0.0', 6), ('portable/20260101-0a0a0a0', 7), ('main-v9.0.0', 8)]
        self.assertEqual(release_tag.newest_first(tags, 'portable'),
                         ['portable-v1.10.0', 'portable-v1.9.1', 'portable-v1.9.0', 'portable/20260101-0a0a0a0'])
        self.assertEqual(release_tag.newest_first(tags, 'main'), ['main-v9.0.0'])
        self.assertEqual(release_tag.newest_first(tags, 'stable'), [])

    def test_git_cannot_read_the_tags(self):
        self.release(NUMBERED[0])
        self.documented(NUMBERED[0])
        # A `git` that fails only for the list of the tags. The message must not be "no release tag".
        tools = self.tmp / 'tools'
        tools.mkdir()
        real = shutil.which('git')
        (tools / 'git').write_text(f'#!/bin/sh\ncase " $* " in *" for-each-ref "*) exit 128;; esac\nexec {real} "$@"\n')
        (tools / 'git').chmod(0o755)
        done = subprocess.run(['sh', str(SCRIPT), 'demo', str(self.source)], capture_output=True, text=True,
                              env={**self.env, 'PATH': f"{tools}{os.pathsep}{self.env['PATH']}"})
        self.assertEqual(done.returncode, 2)
        self.assertIn('error: Git cannot read the tags of the source of demo.', done.stderr)
        self.assertNotIn('no release tag', done.stderr)

    def test_a_source_with_no_release_tag(self):
        self.release('pre-split-2026-01-05')
        self.documented('0a1b2c3')
        done = self.check()
        self.assertEqual(done.returncode, 2)
        self.assertIn('error: the source of demo has no release tag of the branch portable.', done.stderr)
        self.assertIn('accepted forms: portable-v<major>.<minor>.<patch> and portable/<date>-<hash>', done.stderr)

    def test_the_release_tags_of_another_branch(self):
        self.release('portable-v1.0.0')
        self.release('stable-v3.0.0')
        self.documented('stable-v3.0.0', branch='stable')
        self.assertEqual(self.check().returncode, 0)
        self.documented('portable-v1.0.0')
        self.assertEqual(self.check().returncode, 0)

    def test_the_source_from_the_variable_and_the_usage_errors(self):
        self.release(NUMBERED[0])
        self.documented(NUMBERED[0])
        done = subprocess.run(['sh', str(SCRIPT), 'demo'], capture_output=True, text=True,
                              env={**self.env, 'DEMO_SOURCE': str(self.source)})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.check(str(self.tmp / 'absent')).returncode, 2)
        self.assertEqual(self.check('a', 'b').returncode, 2)
        self.versions.write_text('{}')
        done = self.check()
        self.assertEqual(done.returncode, 2)
        self.assertIn('has no release and branch for demo', done.stderr)


if __name__ == '__main__':
    unittest.main()
