"""Tests of the actions `register` and `check` of docgen/docgen.py: the project list and the checks of the site.

Each test works in a temporary site, so the site is not changed. The temporary site holds a copy of the
generator, a small project list and the pages of three projects.

The tests of the site checks use the real scripts/check.sh with a substitute for each part that it calls:
the tests, the build, the link check, the scanner and the lint. A substitute fails when a file with the name
`fail-<check>` exists. So the tests show that `check` reads the real output of scripts/check.sh.
The substitute for the tests is one test file. The real scripts/run_tests.py runs it.
"""

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PROJECTS = [
    {'slug': 'alpha', 'name': 'alpha', 'summary': 'The first project.', 'docs': 'full'},
    {'slug': 'beta', 'name': 'beta', 'summary': 'The second project.', 'docs': 'overview'},
]
VERSIONS = {'alpha': {'branch': 'portable', 'release': 'portable-v0.1.0'}}

PAGE = '---\ntitle: {project}\ndescription: "The page of {project}."\n---\n\nThe text of the page.\n'

# A part of scripts/check.sh: scan.py, lint_ste.py and check_links.py.
PART = '''import pathlib, sys
if pathlib.Path('fail-NAME').exists():
    print('stub NAME: one finding')
    sys.exit(1)
'''

# `npm run build`. The file `built` shows that the build ran.
BUILD = '''import { existsSync, writeFileSync } from 'node:fs';
writeFileSync('built', '');
if (existsSync('fail-build')) {
	console.error('stub build: one finding');
	process.exit(1);
}
'''

# A test file for scripts/run_tests.py. The site checks use the real runner.
TESTS = '''import pathlib, unittest

class StubTest(unittest.TestCase):
    def test_stub(self):
        self.assertFalse(pathlib.Path('fail-tests').exists(), 'stub tests: one finding')
'''


def data_text(data):
    """The format of the data files of the site."""
    return json.dumps(data, indent='\t', ensure_ascii=False) + '\n'


class SiteCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='docgen-register-test-')).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.site = self.tmp / 'site'
        shutil.copytree(ROOT / 'docgen', self.site / 'docgen', ignore=shutil.ignore_patterns('state', '__pycache__'))
        self.projects = self.site / 'src' / 'data' / 'projects.json'
        self.versions = self.site / 'src' / 'data' / 'versions.json'
        self.projects.parent.mkdir(parents=True)
        self.projects.write_text(data_text(PROJECTS))
        self.versions.write_text(data_text(VERSIONS))
        for project in ('alpha', 'beta', 'demo'):
            self.page(project).parent.mkdir(parents=True)
            self.page(project).write_text(PAGE.format(project=project))

    def page(self, project, path='index.mdx'):
        return self.site / 'src' / 'content' / 'docs' / project / path

    def state(self, project, doc_set='full', release='portable-v0.7.0', ref='portable'):
        """Write the state that `scaffold` writes for a project with one page."""
        record = {'order': 0, 'template': 'overview', 'tree': 'release', 'ref': ref, 'generated': False, 'sources': {}}
        state = {'docgen': 1, 'project': project, 'profile': 'v1', 'doc_set': doc_set, 'release': release,
                 'release_ref': ref, 'pages': {'index.mdx': record}}
        path = self.site / 'docgen' / 'state' / f'{project}.json'
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(state, indent=1, sort_keys=True) + '\n')

    def docgen(self, *words):
        return subprocess.run(['python3', str(self.site / 'docgen' / 'docgen.py'), *words],
                              cwd=self.tmp, capture_output=True, text=True)

    def command(self, action, project='demo'):
        """The complete command line that the script prints for one action."""
        return f"python3 {self.site / 'docgen' / 'docgen.py'} {action} --project {project}"

    def files(self):
        """The content and the change time of each file of the site."""
        return {str(path.relative_to(self.site)): (path.read_bytes(), path.stat().st_mtime_ns)
                for path in sorted(self.site.rglob('*')) if path.is_file()}

    def listed(self):
        return json.loads(self.projects.read_text())

    def released(self):
        return json.loads(self.versions.read_text())


class RegisterTest(SiteCase):
    def test_register_adds_a_project(self):
        self.state('demo')
        done = self.docgen('register', '--project', 'demo')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('added    demo', done.stdout)
        self.assertIn('release  demo is at portable-v0.7.0 of the branch portable', done.stdout)
        # The note says what the agent does with it. The last line is the complete next command.
        self.assertIn('note     the text and the diagram of the home page src/content/docs/index.mdx name each project. '
                      '`register` does not change them. Do not change the home page. Put this line into your report.',
                      done.stdout.splitlines())
        self.assertEqual(done.stdout.splitlines()[-1], 'next     ' + self.command('check'))
        demo = {'slug': 'demo', 'name': 'demo', 'summary': 'The page of demo.', 'docs': 'full'}
        self.assertEqual(self.listed(), PROJECTS + [demo])
        self.assertEqual(self.released(), {**VERSIONS, 'demo': {'branch': 'portable', 'release': 'portable-v0.7.0'}})
        # The files keep the format of the tracked files.
        self.assertEqual(self.projects.read_text(), data_text(PROJECTS + [demo]))
        self.assertTrue(self.versions.read_text().startswith('{\n\t"alpha": {\n\t\t"branch": "portable",\n'))

    def test_a_second_run_changes_no_file(self):
        self.state('demo')
        self.assertEqual(self.docgen('register', '--project', 'demo').returncode, 0)
        before = self.files()
        done = self.docgen('register', '--project', 'demo')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('No file changed.', done.stdout)
        self.assertEqual(self.files(), before)

    def test_register_does_not_write_a_file_whose_data_does_not_change(self):
        # The list of releases has spaces, not tabs. Only the project list changes.
        self.versions.write_text(json.dumps(VERSIONS, indent=2) + '\n')
        releases = self.versions.read_bytes()
        done = self.docgen('register', '--project', 'demo', '--docs', 'overview')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.listed()[-1]['slug'], 'demo')
        self.assertEqual(self.versions.read_bytes(), releases)

    def test_register_changes_overview_to_full(self):
        self.state('beta', release='main-v2.0.0', ref='main')
        done = self.docgen('register', '--project', 'beta')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('changed  beta from overview to full', done.stdout)
        # The project keeps its place, its name and its summary.
        self.assertEqual(self.listed(), [PROJECTS[0], {**PROJECTS[1], 'docs': 'full'}])
        self.assertEqual(self.released()['beta'], {'branch': 'main', 'release': 'main-v2.0.0'})
        before = self.files()
        self.assertEqual(self.docgen('register', '--project', 'beta').returncode, 0)
        self.assertEqual(self.files(), before)

    def test_register_does_not_change_full_to_overview(self):
        before = self.files()
        done = self.docgen('register', '--project', 'alpha', '--docs', 'overview')
        self.assertEqual(done.returncode, 2)
        self.assertIn('does not change a full doc set to an overview', done.stderr)
        # A state with an overview doc set does not change the project.
        self.state('alpha', doc_set='overview', release='portable-v0.1.0')
        before = self.files()
        done = self.docgen('register', '--project', 'alpha')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.files(), before)

    def test_register_stops_for_a_full_doc_set_with_no_release_tag(self):
        # With no release tag, the release of the survey is a commit. A tag of another form is no release also.
        for release in ('0a1b2c3', 'portable-validated', 'portable/wip', 'portable-v01.0.0', 'main-v1.0.0'):
            with self.subTest(release=release):
                self.state('demo', release=release)
                before = self.files()
                done = self.docgen('register', '--project', 'demo')
                self.assertEqual(done.returncode, 2)
                self.assertIn(f"error: '{release}' is not a release tag of the branch portable. A project with a full doc set "
                              'needs a tag of the form portable-v<major>.<minor>.<patch> and portable/<date>-<hash>. '
                              'Do not make the tag. Stop and tell the user this line.', done.stderr)
                self.assertEqual(self.files(), before)
        # An option gives the same stop.
        done = self.docgen('register', '--project', 'demo', '--docs', 'full', '--release', '0a1b2c3', '--branch', 'portable')
        self.assertEqual(done.returncode, 2)
        # A project with an overview only keeps the release of the survey.
        self.state('demo', doc_set='overview', release='0a1b2c3')
        done = self.docgen('register', '--project', 'demo')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.released()['demo'], {'branch': 'portable', 'release': '0a1b2c3'})

    def test_register_sets_a_new_release(self):
        self.state('alpha', release='portable-v0.2.0')
        done = self.docgen('register', '--project', 'alpha')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.released(), {'alpha': {'branch': 'portable', 'release': 'portable-v0.2.0'}})
        self.assertEqual(self.listed(), PROJECTS)

    def test_register_takes_each_value_from_an_option(self):
        done = self.docgen('register', '--project', 'demo', '--docs', 'overview', '--name', 'Demo',
                           '--summary', 'A project for the tests.')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.listed()[-1], {'slug': 'demo', 'name': 'Demo', 'summary': 'A project for the tests.',
                                             'docs': 'overview'})
        # An overview with no release gets no entry in the list of releases.
        self.assertEqual(self.released(), VERSIONS)
        done = self.docgen('register', '--project', 'demo', '--docs', 'full', '--release', 'main-v3.0.0', '--branch', 'main')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.listed()[-1]['docs'], 'full')
        self.assertEqual(self.released()['demo'], {'branch': 'main', 'release': 'main-v3.0.0'})

    def test_register_stops_on_a_wrong_input(self):
        host_path = ''.join(('See /ho', 'me/alice/demo.'))
        cases = (
            (('--project', 'absent', '--docs', 'overview'), 'has no overview page'),
            (('--project', 'Demo_1', '--docs', 'overview'), 'is not a project name'),
            (('--project', 'demo'), 'the size of the doc set'),
            (('--project', 'demo', '--docs', 'full'), 'the release of'),
            (('--project', 'demo', '--docs', 'overview', '--summary', host_path), 'an absolute path of one host'),
            (('--project', 'demo', '--docs', 'overview', '--summary', 'word ' * 40), 'must be one line'),
        )
        before = self.files()
        for words, message in cases:
            with self.subTest(words=words[:4]):
                done = self.docgen('register', *words)
                self.assertEqual(done.returncode, 2, done.stdout)
                self.assertIn(message, done.stderr)
                self.assertEqual(self.files(), before)

    def test_a_stop_of_register_names_the_complete_scaffold_command(self):
        # The agent works in the project repository. Each command of a line runs from there.
        cases = (
            (('--project', 'absent'), "error: the project 'absent' has no overview page src/content/docs/absent/index.mdx. "
             'Run first: ' + self.command('scaffold', 'absent')),
            (('--project', 'demo'), "error: the size of the doc set of 'demo' is not known. The option `--docs` gives it, and "
             '`scaffold` records it. Run first: ' + self.command('scaffold')),
            (('--project', 'demo', '--docs', 'full'), "error: the release of 'demo' is not known. The options `--release` and "
             '`--branch` give it, and `scaffold` records it. Run first: ' + self.command('scaffold')),
        )
        for words, line in cases:
            with self.subTest(words=words):
                done = self.docgen('register', *words)
                self.assertEqual((done.returncode, done.stderr.strip()), (2, line))

    def test_register_needs_a_description_or_a_summary(self):
        self.page('demo').write_text('---\ntitle: demo\n---\n\nThe text of the page.\n')
        done = self.docgen('register', '--project', 'demo', '--docs', 'overview')
        self.assertEqual(done.returncode, 2)
        self.assertIn('Give --summary', done.stderr)

    def test_the_data_files_of_the_site_have_the_format_of_register(self):
        # So the first run of `register` on the site changes only the lines of its project.
        for name in ('projects.json', 'versions.json'):
            text = (ROOT / 'src' / 'data' / name).read_text()
            self.assertEqual(text, data_text(json.loads(text)), name)


class SiteCheckTest(SiteCase):
    def setUp(self):
        super().setUp()
        scripts = self.site / 'scripts'
        scripts.mkdir()
        for script in ('check.sh', 'run_tests.py'):
            shutil.copy(ROOT / 'scripts' / script, scripts / script)
        for script, name in (('scan.py', 'scan'), ('lint_ste.py', 'lint'), ('check_links.py', 'links')):
            (scripts / script).write_text(PART.replace('NAME', name))
        (self.site / 'tests').mkdir()
        (self.site / 'tests' / 'test_stub.py').write_text(TESTS)
        (self.site / 'package.json').write_text(json.dumps({'private': True, 'scripts': {'build': 'node build.mjs'}}))
        (self.site / 'build.mjs').write_text(BUILD)
        (self.site / 'node_modules').mkdir()
        (self.site / 'astro.config.mjs').write_text('export default {};\n')
        self.state('demo')
        self.assertEqual(self.docgen('register', '--project', 'demo').returncode, 0)

    def check(self, *failing):
        """Run `check` while the named site checks fail."""
        for name in failing:
            (self.site / f'fail-{name}').write_text('')
        done = self.docgen('check', '--project', 'demo')
        for name in failing:
            (self.site / f'fail-{name}').unlink()
        return done

    @unittest.skipUnless(shutil.which('npm'), 'the build of the site needs npm')
    def test_check_passes_when_each_site_check_passes(self):
        done = self.check()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn('0 finding(s) in 1 page(s) of demo', done.stdout)
        for name in ('tests', 'build', 'links', 'scan', 'lint'):
            self.assertRegex(done.stdout, rf'(?m)^site     {name} +ok$')
        self.assertNotIn('check failed', done.stdout)
        self.assertTrue((self.site / 'built').exists())
        # The step after a check that passes: the commit of the doc set.
        self.assertEqual(done.stdout.splitlines()[-1], 'next     ' + self.command('commit'))

    @unittest.skipUnless(shutil.which('npm'), 'the build of the site needs npm')
    def test_check_fails_and_names_each_site_check_that_fails(self):
        for failing in (('tests',), ('build',), ('links',), ('scan', 'lint')):
            with self.subTest(failing=failing):
                done = self.check(*failing)
                self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
                self.assertEqual(done.stdout.splitlines()[-1], f"check failed: {', '.join(failing)}. Correct each finding "
                                 'above. Then run again: ' + self.command('check'))
                self.assertNotIn('next ', done.stdout)
                for name in ('tests', 'build', 'links', 'scan', 'lint'):
                    if name in failing:
                        self.assertRegex(done.stdout, rf'(?m)^site     {name} +FAIL$')
                        # The output of the failed check shows.
                        self.assertIn(f'stub {name}: one finding', done.stdout)
                    elif name == 'links' and 'build' in failing:
                        self.assertRegex(done.stdout, r'(?m)^site     links  skipped \(no build\)$')
                    else:
                        self.assertRegex(done.stdout, rf'(?m)^site     {name} +ok$')

    @unittest.skipUnless(shutil.which('npm'), 'the build of the site needs npm')
    def test_a_failed_test_shows_also_when_many_test_files_pass_after_it(self):
        # `check` prints the last 30 lines of a failed check. The runner prints the output of a failed file last.
        for number in range(12):
            (self.site / 'tests' / f'test_t{number:02}.py').write_text(
                'import unittest\n\n\nclass LaterTest(unittest.TestCase):\n    def test_later(self):\n        pass\n')
        done = self.check('tests')
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        shown = done.stdout.splitlines()
        below = shown[shown.index('site     tests  FAIL') + 1:shown.index('site     build  ok')]
        self.assertRegex(below[0], r'^\.\.\. \d+ line\(s\) before these\. ')
        self.assertEqual(len(below), 31)
        self.assertIn('AssertionError: True is not false : stub tests: one finding', below)
        self.assertRegex(below[-2], r'^FAIL  test  test_stub\.py  FAIL: test_stub \(test_stub\.StubTest')
        self.assertRegex(below[-1], r'^tests: 1 failed file\(s\)\. 13 file\(s\), 13 test\(s\), ')

    def test_the_site_checks_do_not_run_when_a_page_has_a_finding(self):
        self.page('demo').write_text('---\ntitle: demo\n---\n\nThe text of the page.\n')
        done = self.check()
        self.assertEqual(done.returncode, 1)
        self.assertIn('frontmatter', done.stdout)
        self.assertIn('site     not run', done.stdout)
        self.assertFalse((self.site / 'built').exists())

    def test_check_asks_for_register_first(self):
        self.projects.write_text(data_text(PROJECTS))
        done = self.check()
        self.assertEqual(done.returncode, 1)
        self.assertEqual(done.stdout.splitlines()[-1], f"{self.projects}:1: not-registered: the project list or the release "
                         f"of 'demo' is not current. Fix: run `{self.command('register')}`.")
        self.assertFalse((self.site / 'built').exists())

    @unittest.skipUnless(shutil.which('npm'), 'the build of the site needs npm')
    def test_a_line_of_a_failed_site_check_names_the_absolute_path_of_its_file(self):
        # A check of the site prints a path that is relative to the site. The agent works in the project repository.
        (self.site / 'scripts' / 'lint_ste.py').write_text(
            "import sys\nprint('src/content/docs/demo/index.mdx:6: sentence-length: the sentence has 31 words.')\n"
            "print('src/content/docs/demo/absent.mdx:1: a file that does not exist')\nsys.exit(1)\n")
        done = self.check()
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn(f"{self.page('demo')}:6: sentence-length: the sentence has 31 words.", done.stdout.splitlines())
        self.assertIn('src/content/docs/demo/absent.mdx:1: a file that does not exist', done.stdout.splitlines())

    @unittest.skipUnless(shutil.which('npm'), 'the build of the site needs npm')
    def test_a_failed_build_shows_its_error_lines_also_when_they_are_not_the_last_lines(self):
        # The build prints the cause first, and many lines of a page after it.
        lines = ['route /demo/', '00:00:01 [ERROR] the component expects one list', '  Location:',
                 '    src/content/docs/demo/index.mdx:6:1'] + [f'line {number} of the page' for number in range(80)]
        (self.site / 'build.mjs').write_text(f'console.log({json.dumps(lines)}.join("\\n"));\nprocess.exit(1);\n')
        done = self.check()
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        shown = done.stdout.splitlines()
        start = shown.index('site     build  FAIL')
        self.assertEqual(shown[start + 1:start + 4], ['00:00:01 [ERROR] the component expects one list', 'Location:',
                                                      f"{self.page('demo')}:6:1"])
        # The command of this line is complete: the agent works in the project repository, and not in the site.
        self.assertRegex(shown[start + 4], r'^\.\.\. \d+ line\(s\) before these\. This command prints each line of each check: '
                         + re.escape(f"sh {self.site / 'scripts' / 'check.sh'}") + '$')
        self.assertEqual(shown.count('00:00:01 [ERROR] the component expects one list'), 1)

    def test_check_fails_when_the_site_checks_cannot_run(self):
        (self.site / 'node_modules').rmdir()
        done = self.check()
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertIn('node_modules is absent', done.stdout)
        self.assertIn('check failed: scripts/check.sh stopped with the exit code 2.', done.stdout)
        (self.site / 'scripts' / 'check.sh').unlink()
        done = self.check()
        self.assertEqual(done.returncode, 2)
        self.assertIn('the site has no scripts/check.sh', done.stderr)

    def test_a_directory_with_no_site_gets_the_page_checks_only(self):
        (self.site / 'astro.config.mjs').unlink()
        done = self.check()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn('site     not run', done.stdout)
        self.assertFalse((self.site / 'built').exists())


if __name__ == '__main__':
    unittest.main()
