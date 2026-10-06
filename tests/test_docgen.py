"""Tests of docgen/docgen.py with a small fixture repository.

Each test works in a temporary copy of the docgen directory, so the site is not changed.
"""

import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent

# The generator as a module, for its patterns and its slot reader. No test calls an action of this module.
SPEC = importlib.util.spec_from_file_location('docgen_under_test', ROOT / 'docgen' / 'docgen.py')
docgen = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(docgen)

CLI = '''import argparse

def main():
    parser = argparse.ArgumentParser()
    actions = parser.add_subparsers(dest="action")
    actions.add_parser("build")
    actions.add_parser("check")
    parser.parse_args()

if __name__ == "__main__":
    main()
'''

PAGES = ('index.mdx', 'install/index.mdx', 'use/commands/index.mdx', 'use/commands/build.mdx',
         'use/commands/check.mdx', 'develop/workflow.mdx', 'reference/index.mdx')
STEPS = '''1. Copy the example file.

   ```sh
   cp .env.example .env
   ```

   Result: the file `.env` exists.

2. Make the output directory.

   ```sh
   mkdir -p out
   ```

   Result: the command ends with no error.'''


# Git gives these variables to a hook. With them, a `git` command of a test writes into the repository
# of the hook, and not into the fixture repository. So no command of a test gets them.
GIT_LOCAL = ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR', 'GIT_OBJECT_DIRECTORY',
             'GIT_ALTERNATE_OBJECT_DIRECTORIES', 'GIT_PREFIX', 'GIT_NAMESPACE', 'GIT_CONFIG', 'GIT_CONFIG_COUNT',
             'GIT_CONFIG_PARAMETERS', 'GIT_GRAFT_FILE', 'GIT_IMPLICIT_WORK_TREE', 'GIT_NO_REPLACE_OBJECTS',
             'GIT_REPLACE_REF_BASE', 'GIT_SHALLOW_FILE', 'GIT_INTERNAL_SUPER_PREFIX')


def run(*words, cwd):
    # The scanner of the site reads SCAN_LOCAL_DENY. No test depends on the list of this host.
    env = {name: value for name, value in os.environ.items() if name not in GIT_LOCAL and name != 'SCAN_LOCAL_DENY'}
    return subprocess.run(words, cwd=cwd, capture_output=True, text=True, env=env)


def make_project(repo):
    """A fixture project: a README, a setup guide, a command line with two actions, a test file,
    one merged topic branch, a release branch and a tag."""
    for name in ('docs', 'scripts', 'tests'):
        (repo / name).mkdir(parents=True)
    (repo / 'README.md').write_text('# demo\n\nStatus: prototype.\n\ndemo builds a small thing.\n\n## Parts\n')
    (repo / 'docs' / 'setup.md').write_text('# Setup\n\n## Steps\n\nRun `python3 scripts/cli.py build`.\n')
    (repo / 'docs' / 'build.md').write_text('# The action build <draft>\n')
    (repo / 'scripts' / 'cli.py').write_text(CLI)
    (repo / 'tests' / 'test_demo.py').write_text('import unittest\n')
    for words in (
        ('init', '-q', '-b', 'main'),
        ('add', '-A'),
        ('commit', '-q', '-m', 'First commit'),
        ('switch', '-q', '-c', 'topic/i7-more'),
        ('commit', '-q', '--allow-empty', '-m', 'More'),
        ('switch', '-q', 'main'),
        ('merge', '-q', '--no-ff', 'topic/i7-more', '-m', 'Merge topic/i7-more: more (issue 7)'),
        ('branch', 'portable'),
        ('tag', 'portable-v0.1.0', 'portable'),
        *((('commit', '-q', '--allow-empty', '-m', 'x'),) * 4),
    ):
        done = run('git', '-c', 'user.name=t', '-c', 'user.email=t@example.com', *words, cwd=repo)
        assert done.returncode == 0, done.stderr


def next_command(output):
    """The command of the one `next` line of an output."""
    lines = [line for line in output.splitlines() if line.startswith('next ')]
    assert len(lines) == 1, output
    return lines[0].split(None, 1)[1]


def words_of(body):
    """The word count of a slot, as the generator counts it."""
    return len(re.findall(r"[\w'-]+", re.sub(r'`[^`]*`|<[^>]+>', 'x', body)))


def sample(slot):
    """Text of the right form and length for one slot."""
    form, low = slot['form'] or 'text', max(int(slot['min']), 12)
    start = re.search(r'starts with `([^`]+)`', slot['text'])
    if form == 'command':
        return start.group(1) if start else 'python3 scripts/cli.py build'
    if form == 'steps':
        return STEPS
    if form == 'table':
        lines = ['| Part | What it is |', '| --- | --- |']
        while words_of('\n'.join(lines)) < low:
            lines.append('| word | word word word word |')
        return '\n'.join(lines)
    if form in ('list', 'numbered'):
        lines = []
        while not lines or words_of('\n'.join(lines)) < low:
            lines.append(('- ' if form == 'list' else f'{len(lines) + 1}. ') + 'word word word word')
        return '\n'.join(lines)
    return (start.group(1) + ' ' if start else '') + ' '.join(['word'] * low) + '.'


def fill(page, only=None, text=None):
    """Write each open slot of one page, or the slot `only` with `text`."""
    out, slot = [], None
    for line in page.read_text().splitlines():
        opened = docgen.SLOT_OPEN.search(line)
        if opened:
            slot = opened.groupdict()
        elif slot and docgen.SLOT_END in line:
            slot = None
        elif slot and (only is None or slot['id'] == only):
            if docgen.TODO.search(line):
                out.append(text if text is not None else sample(slot))
                continue
        out.append(line)
    page.write_text('\n'.join(out) + '\n')


class DocgenTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='docgen-test-')).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        # A temporary site that holds only the generator and the capture script.
        self.site = self.tmp / 'site'
        shutil.copytree(ROOT / 'docgen', self.site / 'docgen', ignore=shutil.ignore_patterns('state', '__pycache__'))
        (self.site / 'src' / 'content' / 'docs').mkdir(parents=True)
        (self.site / 'scripts').mkdir()
        shutil.copy(ROOT / 'scripts' / 'capture.py', self.site / 'scripts' / 'capture.py')
        self.docgen = str(self.site / 'docgen' / 'docgen.py')
        self.docs = self.site / 'src' / 'content' / 'docs' / 'demo'

        self.repo = self.tmp / 'demo'
        make_project(self.repo)

    def git(self, *words):
        done = run('git', '-c', 'user.name=t', '-c', 'user.email=t@example.com', *words, cwd=self.repo)
        self.assertEqual(done.returncode, 0, done.stderr)

    def docgen_run(self, *words):
        return run('python3', self.docgen, *words, cwd=self.repo)

    def prepare(self, doc_set='full'):
        for words in (('survey', '--repo', '.'), ('plan', '--project', 'demo', '--doc-set', doc_set),
                      ('scaffold', '--project', 'demo')):
            done = self.docgen_run(*words)
            self.assertEqual(done.returncode, 0, done.stderr)
        return done

    def page(self, path):
        return self.site / 'src' / 'content' / 'docs' / 'demo' / path

    def command(self, action, *words):
        """The complete command line that the script prints for one action."""
        return ' '.join(('python3', self.docgen, action, '--project', 'demo', *words))

    def spec(self, name):
        return self.site / 'captures' / 'demo' / f'{name}.json'

    def files(self):
        return {p: p.read_bytes() for p in self.site.rglob('*') if p.is_file() and '.docgen' not in p.parts}

    def fill_all(self):
        for path in PAGES:
            fill(self.page(path))

    def write_slot(self, path, slot, text):
        """Replace the text of one slot of a page. The two lines of a command slot stay. Return the line of the slot."""
        lines = self.page(path).read_text().splitlines()
        first = next(n for n, line in enumerate(lines) if f'docgen:slot {slot} ' in line)
        last = next(n for n in range(first, len(lines)) if docgen.SLOT_END in lines[n])
        keep = [line for line in lines[first + 1:last] if line.strip() in (docgen.COMMAND_OPEN, docgen.COMMAND_END)]
        body = [keep[0], text, keep[1]] if keep else [text]
        self.page(path).write_text('\n'.join(lines[:first + 1] + body + lines[last:]) + '\n')
        return first + 1

    # ----- the fixture -----

    def test_no_command_writes_into_the_repository_of_a_hook(self):
        # A second repository stands for the repository of a hook. Git gives its location to the hook.
        other = self.tmp / 'other'
        other.mkdir()
        self.assertEqual(run('git', 'init', '-q', '-b', 'main', cwd=other).returncode, 0)
        with mock.patch.dict(os.environ, {'GIT_DIR': str(other / '.git'), 'GIT_INDEX_FILE': str(other / '.git' / 'index')}):
            self.git('commit', '-q', '--allow-empty', '-m', 'In the fixture')
            self.prepare()
        self.assertNotEqual(run('git', 'rev-parse', '--verify', '-q', 'HEAD', cwd=other).returncode, 0)
        self.assertEqual(run('git', 'status', '--porcelain', cwd=other).stdout, '')
        self.assertIn('In the fixture', run('git', 'log', '-1', '--format=%s', cwd=self.repo).stdout)
        facts = json.loads((self.site / '.docgen' / 'demo' / 'facts.json').read_text())
        self.assertEqual(facts['release']['name'], 'portable-v0.1.0')

    # ----- survey, plan and scaffold -----

    def test_survey_takes_the_release_by_the_rule_of_the_version_check(self):
        # Each of these tags is made later than the release tags, and none is a release.
        for tag in ('portable-v0.9.0', 'portable-v0.10.0', 'portable-v0.9.1', 'portable-validated', 'portable/wip',
                    'portable-v01.0.0', 'v9.9.9', 'pre-split-2026-01-05'):
            self.git('tag', tag, 'portable')
        self.assertEqual(self.docgen_run('survey', '--repo', '.').returncode, 0)
        facts = json.loads((self.site / '.docgen' / 'demo' / 'facts.json').read_text())
        self.assertEqual(facts['release']['name'], 'portable-v0.10.0')
        self.assertEqual(facts['release']['recent_tags'], ['portable-v0.10.0', 'portable-v0.9.1', 'portable-v0.9.0',
                                                           'portable-v0.1.0'])
        # scripts/check-version.sh gives the same release for the same repository.
        versions = self.tmp / 'versions.json'
        versions.write_text(json.dumps({'demo': {'branch': 'portable', 'release': facts['release']['name']}}))
        env = {name: value for name, value in os.environ.items() if name not in GIT_LOCAL}
        done = subprocess.run(['sh', str(ROOT / 'scripts' / 'check-version.sh'), 'demo', str(self.repo)],
                              capture_output=True, text=True, env={**env, 'VERSIONS_FILE': str(versions)})
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_survey_of_a_project_with_no_release_tag(self):
        self.git('tag', '-d', 'portable-v0.1.0')
        self.git('tag', 'portable-validated', 'portable')
        done = self.docgen_run('survey', '--repo', '.')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('note           the project has no release tag of the branch portable', done.stdout)
        self.assertIn('portable-v<major>.<minor>.<patch> and portable/<date>-<hash>', done.stdout)
        facts = json.loads((self.site / '.docgen' / 'demo' / 'facts.json').read_text())
        self.assertEqual(facts['release']['recent_tags'], [])
        self.assertRegex(facts['release']['name'], r'^[0-9a-f]{7,40}$')

    def test_survey_finds_the_facts(self):
        self.assertEqual(self.docgen_run('survey', '--repo', '.').returncode, 0)
        facts = json.loads((self.site / '.docgen' / 'demo' / 'facts.json').read_text())
        self.assertEqual(facts['release'], {'ref': 'portable', 'name': 'portable-v0.1.0', 'recent_tags': ['portable-v0.1.0']})
        self.assertTrue(facts['history']['uses_topic_branches'])
        self.assertEqual(facts['history']['recent_merges'][0]['issue'], 7)
        release = facts['trees']['release']
        self.assertEqual(release['readme']['status'], 'prototype.')
        self.assertEqual(release['readme']['summary'], 'demo builds a small thing.')
        cli = [e for e in release['entry_points'] if e['kind'] == 'python-cli']
        self.assertEqual(cli[0]['actions'], ['build', 'check'])

    def test_plan_has_one_page_for_each_action(self):
        self.prepare()
        plan = json.loads((self.site / '.docgen' / 'demo' / 'plan.json').read_text())
        self.assertEqual([p['path'] for p in plan['pages']], list(PAGES))
        build = plan['pages'][3]
        self.assertEqual(build['vars'], {'action': 'build', 'index': 0})
        # The sources of an action page: the command line, the file with the name of the action, the README.
        self.assertEqual(list(build['sources']), ['scripts/cli.py', 'docs/build.md', 'README.md'])
        self.assertEqual(list(plan['pages'][4]['sources']), ['scripts/cli.py', 'README.md'])

    def test_plan_skips_the_action_pages_of_a_project_with_no_action(self):
        (self.repo / 'scripts' / 'cli.py').write_text('print("no command line")\n')
        self.git('switch', '-q', 'portable')
        self.git('commit', '-q', '-am', 'No command line')
        self.assertEqual(self.docgen_run('survey', '--repo', '.').returncode, 0)
        done = self.docgen_run('plan', '--project', 'demo')
        self.assertRegex(done.stdout, r'skipped\s+command\s+the project has no command line with actions')
        self.assertRegex(done.stdout, r'skipped\s+commands\s+the project has no entry point')

    def test_a_workflow_script_is_not_the_command_line_of_the_project(self):
        def cli(path, actions):
            return {'path': path, 'kind': 'python-cli', 'actions': actions}
        tree = {'entry_points': [cli('scripts/scan.py', ['all', 'staged', 'selftest']), cli('scripts/tool.py', ['run']),
                                 cli('build.py', [])],
                'workflow': {'scanner': ['scripts/scan.py'], 'hooks': []}}
        self.assertEqual(docgen.main_cli(tree)['path'], 'scripts/tool.py')
        self.assertEqual(docgen.commands_of(tree), ['python3 scripts/scan.py', 'run', 'python3 build.py'])
        tree['entry_points'] = tree['entry_points'][:1]
        self.assertIsNone(docgen.main_cli(tree))
        self.assertEqual(docgen.actions_of(tree), [])

    def test_scaffold_writes_pages_and_never_overwrites(self):
        self.prepare()
        for path in PAGES:
            self.assertTrue(self.page(path).exists(), path)
        self.page('index.mdx').write_text('---\ntitle: demo\ndescription: d\n---\n\nA person wrote this.\n')
        self.assertEqual(self.docgen_run('scaffold', '--project', 'demo').returncode, 0)
        self.assertIn('A person wrote this.', self.page('index.mdx').read_text())

    def test_second_run_changes_no_file(self):
        self.prepare()
        before = self.files()
        self.prepare()
        self.assertEqual(before, self.files())
        # Also with written slots: the second run after the specs follow the pages.
        self.fill_all()
        self.assertEqual(self.docgen_run('scaffold', '--project', 'demo').returncode, 0)
        before = self.files()
        self.prepare()
        self.assertEqual(before, self.files())

    # ----- templates -----

    def test_each_template_slot_has_a_form_and_a_reachable_range(self):
        for template in sorted((ROOT / 'docgen' / 'profiles' / 'v1').glob('*.mdx')):
            text = template.read_text()
            slots = docgen.slots_of(text)
            ids = [slot['id'] for slot in slots]
            self.assertEqual(len(ids), len(set(ids)), f'{template.name}: a slot id is not unique')
            self.assertEqual(text.count('docgen:slot '), len(slots), f'{template.name}: a slot comment has a wrong form')
            self.assertEqual(len(docgen.TODO.findall(text)), len(slots), template.name)
            for slot in slots:
                self.assertIn(slot['form'], docgen.FORMS, f"{template.name}: {slot['id']}")
                self.assertTrue(slot['open'], f"{template.name}: {slot['id']}")
                fallback = docgen.fallback_of(slot)
                if fallback:
                    # The sentence for "the files have no answer" passes the length check and the form check.
                    self.assertTrue(int(slot['min']) <= words_of(fallback) <= int(slot['max']),
                                    f"{template.name}: {slot['id']}: the fallback has {words_of(fallback)} words")
                    self.assertEqual(docgen.slot_problems({**slot, 'open': False, 'written': [fallback]}), [])

    def test_pages_of_the_release_show_the_release(self):
        self.prepare()
        for path in PAGES:
            text = self.page(path).read_text()
            self.assertNotIn('{{', text, path)
            self.assertEqual('<DocVersion project="demo" />' in text, path != 'develop/workflow.mdx', path)
        install = self.page('install/index.mdx').read_text()
        self.assertEqual(install.count('<Stage n={'), 4)
        self.assertEqual(install.count('```mermaid'), 1)
        self.assertIn('This page describes the branch `main` of demo.', self.page('develop/workflow.mdx').read_text())
        # The diagrams that a larger model draws.
        done = self.docgen_run('diagrams', '--project', 'demo')
        self.assertIn('2 diagram(s) to draw', done.stdout)

    def test_script_made_parts_of_the_pages(self):
        self.prepare()
        overview = self.page('index.mdx').read_text()
        self.assertIn('description: "demo builds a small thing."', overview)
        for href in ('/demo/install/', '/demo/use/commands/', '/demo/develop/workflow/', '/demo/reference/'):
            self.assertIn(f'href="{href}"', overview)
        summary = self.page('use/commands/index.mdx').read_text()
        self.assertIn('- [`build`](/demo/use/commands/build/)', summary)
        self.assertIn('in this order: `build`, `check`.', summary)
        self.assertNotIn('## Examples', summary)
        build = self.page('use/commands/build.mdx').read_text()
        self.assertIn('title: "build"', build)
        self.assertIn('  order: 2', build)
        self.assertIn('  order: 3', self.page('use/commands/check.mdx').read_text())
        reference = self.page('reference/index.mdx').read_text()
        self.assertIn('## Top-level files', reference)
        self.assertIn('## Files in `docs/`', reference)
        # Text of a project file can not start a tag in the page.
        self.assertIn('| `docs/build.md` | The action build &lt;draft> |', reference)
        self.assertIn('- [Install](/demo/install/): ', reference)

    def test_overview_doc_set_has_one_page(self):
        done = self.prepare('overview')
        self.assertEqual([p.name for p in self.page('').rglob('*.mdx')], ['index.mdx'])
        overview = self.page('index.mdx').read_text()
        self.assertIn('This site has one overview page for this project.', overview)
        self.assertNotIn('<CardGrid>', overview)
        self.assertNotIn('captures', done.stdout)
        self.assertFalse((self.site / 'captures').exists())

    def test_long_summary_gives_a_fixed_description(self):
        self.assertEqual(docgen.description_of('demo', 'demo builds a "small" thing. It has parts.'),
                         "demo builds a 'small' thing.")
        long = 'demo ' + 'is long ' * 20 + 'text.'
        self.assertEqual(docgen.description_of('demo', long), 'What demo is, who it is for and what its status is.')
        self.assertEqual(docgen.description_of('demo', ''), 'What demo is, who it is for and what its status is.')

    # ----- capture specs -----

    def marks(self):
        found = []
        for path in PAGES:
            found += [m.group('name') for m in docgen.CAPTURE_MARK.finditer(self.page(path).read_text())]
        return found

    def test_scaffold_writes_one_spec_for_each_command_slot(self):
        done = self.prepare()
        marks = self.marks()
        self.assertEqual(sorted(marks), ['cmd-build', 'cmd-check', 'dev-tests', 'help', 'help-build', 'help-check',
                                         'stage1-clone', 'stage3-start', 'stage4-check'])
        self.assertEqual(sorted(p.stem for p in (self.site / 'captures' / 'demo').glob('*.json')), sorted(marks))
        self.assertIn('captures 9 command slot(s), 9 spec(s) written', done.stdout)
        for name in marks:
            self.assertIn(f'<Capture id="demo/{name}" />', ''.join(self.page(p).read_text() for p in PAGES))

        self.assertEqual(json.loads(self.spec('stage1-clone').read_text()), {
            'title': 'Clone the repository', 'stage': 1, 'order': 100,
            'command': 'git clone \'<the URL of the demo repository>\' "$HOME/demo"',
            'setup': ['ln -s /srv/demo.git "$HOME/<the URL of the demo repository>"'], 'mode': 'scripted'})
        self.assertEqual(json.loads(self.spec('help-check').read_text()), {
            'title': 'The help text of the action check', 'order': 154,
            'command': 'python3 scripts/cli.py check --help', 'setup': ['cd "$HOME/demo"'], 'mode': 'scripted'})
        self.assertEqual(json.loads(self.spec('dev-tests').read_text())['command'],
                         'python3 -m unittest discover -s tests -q')
        # The spec of an open command slot waits. The capture script does not run it.
        waiting = json.loads(self.spec('cmd-build').read_text())
        self.assertEqual((waiting['command'], waiting['mode'], waiting['order']), ('', 'manual', 600))
        state = json.loads((self.site / 'docgen' / 'state' / 'demo.json').read_text())
        self.assertEqual(state['captures']['cmd-build'], {'page': 'use/commands/build.mdx', 'source': 'slot example-command'})

    def load_specs(self):
        """The spec reader of scripts/capture.py: the scripted specs in run order, and the other specs."""
        code = ('import json, sys; sys.path.insert(0, "scripts"); import capture; '
                'scripted, other = capture.load_specs("demo"); '
                'print(json.dumps([[s["name"] for s in scripted], other]))')
        done = run('python3', '-c', code, cwd=self.site)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn('warning', done.stdout)
        return json.loads(done.stdout.splitlines()[-1])

    def test_capture_script_accepts_each_spec(self):
        self.prepare()
        scripted, other = self.load_specs()
        self.assertEqual(scripted, ['stage1-clone', 'help', 'help-build', 'help-check', 'dev-tests'])
        self.assertEqual(sorted(other), ['cmd-build', 'cmd-check', 'stage3-start', 'stage4-check'])
        # After the slots have their commands, each spec is a scripted capture, in the order of the pages.
        self.fill_all()
        self.assertEqual(self.docgen_run('scaffold', '--project', 'demo').returncode, 0)
        scripted, other = self.load_specs()
        self.assertEqual(scripted, ['stage1-clone', 'help', 'help-build', 'help-check', 'stage3-start', 'stage4-check',
                                    'cmd-build', 'cmd-check', 'dev-tests'])
        self.assertEqual(other, [])

    def test_scaffold_copies_the_command_of_a_slot_into_its_spec(self):
        self.prepare()
        fill(self.page('use/commands/build.mdx'), 'example-command', 'python3 scripts/cli.py build \\\n  --fast')
        fill(self.page('install/index.mdx'), 'stage-3-command', 'python3 scripts/cli.py build')
        done = self.docgen_run('scaffold', '--project', 'demo')
        self.assertIn('updated  captures/demo/cmd-build.json: scripted', done.stdout)
        self.assertIn('captures 9 command slot(s), 2 spec(s) written', done.stdout)
        spec = json.loads(self.spec('cmd-build').read_text())
        self.assertEqual((spec['command'], spec['mode']), ('python3 scripts/cli.py build \\\n  --fast', 'scripted'))
        self.assertEqual(json.loads(self.spec('stage3-start').read_text())['command'], 'python3 scripts/cli.py build')
        self.assertEqual(json.loads(self.spec('cmd-check').read_text())['mode'], 'manual')

        # A person changes the spec. The next run keeps each field but the command.
        spec.update(setup=['cd "$HOME/demo"', 'mkdir -p out'], exit=1, mode='manual')
        self.spec('cmd-build').write_text(json.dumps(spec, indent=2) + '\n')
        before = self.files()
        self.assertEqual(self.docgen_run('scaffold', '--project', 'demo').returncode, 0)
        self.assertEqual(before, self.files())
        page = self.page('use/commands/build.mdx')
        page.write_text(page.read_text().replace('  --fast', '  --slow'))
        self.assertEqual(self.docgen_run('scaffold', '--project', 'demo').returncode, 0)
        after = json.loads(self.spec('cmd-build').read_text())
        self.assertEqual(after, {**spec, 'command': 'python3 scripts/cli.py build \\\n  --slow'})

    def test_scaffold_keeps_a_spec_that_it_did_not_write(self):
        self.spec('help').parent.mkdir(parents=True)
        self.spec('help').write_text('{"title": "By hand", "command": "true", "mode": "manual"}\n')
        done = self.prepare()
        self.assertIn('kept     captures/demo/help.json: the spec exists and docgen did not write it', done.stdout)
        self.assertEqual(json.loads(self.spec('help').read_text())['title'], 'By hand')
        self.assertIn('captures 9 command slot(s), 8 spec(s) written', done.stdout)

    def test_scaffold_reports_a_slot_with_two_commands(self):
        self.prepare()
        fill(self.page('use/commands/build.mdx'), 'example-command', 'python3 scripts/cli.py build\nls')
        done = self.docgen_run('scaffold', '--project', 'demo')
        self.assertIn('skipped  captures/demo/cmd-build.json: use/commands/build.mdx: the slot holds more than one command line.',
                      done.stdout)
        self.assertEqual(json.loads(self.spec('cmd-build').read_text())['command'], '')

    # ----- next -----

    def test_next_prints_the_form_and_the_line_to_replace(self):
        self.prepare()
        done = self.docgen_run('next', '--project', 'demo')
        self.assertIn('slot         what-it-is', done.stdout)
        self.assertIn('form         text', done.stdout)
        self.assertIn('rules        Write only what the files say.', done.stdout)
        self.assertRegex(done.stdout, r'git -C \S+ show portable:README\.md')
        self.assertRegex(done.stdout, r'replace this one line of the page with your text:\n\s+TODO\(docgen:what-it-is\)\n')
        fill(self.page('index.mdx'))
        for slot in ('goal', 'requirements'):
            fill(self.page('install/index.mdx'), slot, sample(next(
                s for s in docgen.slots_of(self.page('install/index.mdx').read_text()) if s['id'] == slot)))
        done = self.docgen_run('next', '--project', 'demo')
        self.assertIn('slot         stage-2-steps', done.stdout)
        self.assertIn('form         steps', done.stdout)
        self.assertIn('                ```sh', done.stdout)
        self.assertIn('facts        manifest files: none', done.stdout)
        self.assertRegex(done.stdout, r'your text:\n\s+1\. TODO\(docgen:stage-2-steps\)\n')

    def test_next_prints_the_facts_of_the_workflow_page(self):
        self.prepare()
        for path in PAGES[:5]:
            fill(self.page(path))
        done = self.docgen_run('next', '--project', 'demo')
        # The agent works in the project repository. So the line has the absolute path of the page.
        self.assertIn(f"page         {self.page('develop/workflow.mdx')}", done.stdout)
        self.assertIn('facts        branches: main, portable, topic/i7-more', done.stdout)
        self.assertIn('release branch: portable. Develop branch: main.', done.stdout)
        self.assertIn('topic branches in the merges: yes.', done.stdout)
        self.assertIn('test commands: python3 -m unittest discover -s tests -q', done.stdout)
        self.assertIn('merge: Merge topic/i7-more: more (issue 7)', done.stdout)

    def test_next_reports_a_fault_in_a_written_slot_first(self):
        self.prepare()
        cases = (
            ('index.mdx', 'what-it-is', 'Give the file <name> to the tool. ' + 'word ' * 30, 'outside backticks'),
            ('index.mdx', 'parts', 'The parts are a program and a file. ' + 'word ' * 30, 'is not one Markdown table'),
            ('index.mdx', 'audience', 'Each user of the project. ' + 'word ' * 15, 'is not one list'),
            ('install/index.mdx', 'stage-2-steps', '1. Copy the file.\n\n```sh\ncp a b\n```\n\n   Result: the file exists.',
             'is not inside a step. Put three spaces before it.'),
            ('install/index.mdx', 'stage-2-result', 'The file exists now.', 'does not start with `**Result:**`'),
            ('use/commands/build.mdx', 'example-command', 'python3 other.py build',
             'does not start with `python3 scripts/cli.py build`'),
            ('use/commands/build.mdx', 'example-command', 'python3 scripts/cli.py build\nls',
             'more than one command line'),
            ('use/commands/build.mdx', 'example-command', '```sh\npython3 scripts/cli.py build\n```',
             'The command has no code block.'),
            ('use/commands/build.mdx', 'example-command', 'python3 scripts/cli.py build docs/*/a.md',
             'the command holds `*/`'),
            ('install/index.mdx', 'stage-2-steps', '\n'.join(f'{n}. Do the thing.' for n in range(1, 11)),
             'more than nine steps'),
            ('develop/workflow.mdx', 'loop', '## The loop\n\nA change starts as an issue. ' + 'word ' * 30, 'has a heading'),
        )
        for path, slot, text, problem in cases:
            with self.subTest(slot=slot, problem=problem):
                original = self.page(path).read_text()
                fill(self.page(path), slot, text)
                done = self.docgen_run('next', '--project', 'demo')
                self.assertIn(f'correct      the slot {slot} ', done.stdout)
                self.assertIn(problem, done.stdout)
                self.assertNotIn('open slots', done.stdout)
                self.page(path).write_text(original)
        # The sentence that an instruction gives for "the files have no answer" is no fault.
        fill(self.page('index.mdx'), 'limits', 'The README states no limit.')
        fill(self.page('install/index.mdx'), 'stage-2-steps', '1. The sources state no configuration step.')
        fill(self.page('install/index.mdx'), 'stage-3-command', 'The sources state no command that starts the project.')
        self.assertIn('open slots', self.docgen_run('next', '--project', 'demo').stdout)

    def test_a_command_slot_without_its_comment_lines_is_a_fault(self):
        self.prepare()
        page = self.page('use/commands/build.mdx')
        fill(page, 'example-command', 'python3 scripts/cli.py build')
        page.write_text(page.read_text().replace('{/* docgen:command\n', '```sh\n').replace('\n*/}\n', '\n```\n'))
        done = self.docgen_run('next', '--project', 'demo')
        self.assertIn('correct      the slot example-command ', done.stdout)
        self.assertIn('is not between the line `{/* docgen:command` and the line `*/}`', done.stdout)

    # ----- a stage with no command: a sentence and no frame -----

    NO_COMMAND = (
        ('a project with no start command', 'stage-3-command', 'stage3-start', 'stage4-check',
         'The sources state no command that starts the project.', 'Start the project with the command in the frame.'),
        ('a project with no test command', 'stage-4-command', 'stage4-check', 'stage3-start',
         'The sources state no test of the install.', 'Test the install with the command in the frame.'),
    )

    def no_tests(self):
        """Remove the tests of the fixture project. The facts of the survey then hold no test command."""
        self.git('switch', '-q', 'portable')
        self.git('rm', '-q', '-r', 'tests')
        self.git('commit', '-q', '-m', 'No tests')
        self.git('switch', '-q', 'main')

    def test_a_stage_with_no_command_has_a_sentence_and_no_frame(self):
        for case, slot, capture, other, sentence, step in self.NO_COMMAND:
            with self.subTest(case):
                self.setUp()
                if slot == 'stage-4-command':
                    # The facts then hold no test command, so `check` prints no `unused-fact` note for this slot.
                    self.no_tests()
                self.prepare()
                self.fill_all()
                page = self.page('install/index.mdx')
                self.assertIn(step, page.read_text())
                self.assertNotIn(f'*/}}\n{sentence}\n', page.read_text())
                self.assertTrue(self.spec(capture).exists())
                # The agent writes the sentence of the slot. Before the next scaffold, `check` names the fix.
                page.write_text(page.read_text().replace(
                    '{/* docgen:command\npython3 scripts/cli.py build\n*/}\n{/* docgen:end */}\n\n{/* docgen:with ' + slot,
                                                '{/* docgen:command\n' + sentence + '\n*/}\n{/* docgen:end */}\n\n{/* docgen:with ' + slot))
                self.assertIn('{/* docgen:command\n' + sentence, page.read_text())
                done = self.docgen_run('check', '--project', 'demo')
                self.assertEqual(done.returncode, 1)
                self.assertRegex(done.stdout, rf"install/index\.mdx:\d+: stale-part: the slot '{slot}' states no command, and the "
                                              r"page still has the step with the frame\. Fix: run `"
                                              + re.escape(self.command('scaffold')) + '`')
                done = self.docgen_run('scaffold', '--project', 'demo')
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertRegex(done.stdout, r'updated  install/index\.mdx\s+the parts of the page agree with its command slots')
                self.assertIn(f'removed  captures/demo/{capture}.json: the page has no frame for this capture', done.stdout)

                # The stage has one sentence. It has no frame, no spec, and no text that points to a frame.
                text = page.read_text()
                self.assertIn(f'{{/* docgen:without {slot} */}}\n{sentence}\n{{/* docgen:end-without */}}', text)
                self.assertNotIn(step, text)
                self.assertNotIn(f'demo/{capture}', text)
                self.assertNotIn(f'docgen:capture {capture} ', text)
                self.assertEqual(text.count('The frame of the last step shows its command in a clean container.'), 1)
                self.assertFalse(self.spec(capture).exists())
                state = json.loads((self.site / 'docgen' / 'state' / 'demo.json').read_text())
                self.assertNotIn(capture, state['captures'])
                # The other stage keeps its frame and its spec.
                self.assertIn(f'<Capture id="demo/{other}" />', text)
                self.assertEqual(json.loads(self.spec(other).read_text())['mode'], 'scripted')
                scripted, waiting = self.load_specs()
                self.assertNotIn(capture, scripted + list(waiting))

                # A second run changes no file, and the checks of the pages pass.
                before = self.files()
                done = self.docgen_run('scaffold', '--project', 'demo')
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertNotIn('updated', done.stdout)
                self.assertNotIn('removed', done.stdout)
                self.assertEqual(before, self.files())
                done = self.docgen_run('check', '--project', 'demo')
                self.assertEqual(done.returncode, 0, done.stdout)
                self.assertIn('No open slot.', self.docgen_run('next', '--project', 'demo').stdout)

                # The sources get the command later: the step, the frame and the spec come back.
                page.write_text(text.replace('{/* docgen:command\n' + sentence, '{/* docgen:command\npython3 scripts/cli.py check'))
                done = self.docgen_run('scaffold', '--project', 'demo')
                self.assertEqual(done.returncode, 0, done.stderr)
                text = page.read_text()
                self.assertIn(step, text)
                self.assertIn(f'   <Capture id="demo/{capture}" />', text)
                self.assertNotIn(f'*/}}\n{sentence}\n', text)
                self.assertEqual(json.loads(self.spec(capture).read_text())['command'], 'python3 scripts/cli.py check')
                self.assertEqual(self.docgen_run('check', '--project', 'demo').returncode, 0)

    def test_a_project_with_no_start_command_and_no_test_command(self):
        self.no_tests()
        self.prepare()
        self.fill_all()
        page = self.page('install/index.mdx')
        text = page.read_text()
        for _, slot, _, _, sentence, _ in self.NO_COMMAND:
            text = text.replace('{/* docgen:command\npython3 scripts/cli.py build\n*/}\n{/* docgen:end */}\n\n{/* docgen:with ' + slot,
                                '{/* docgen:command\n' + sentence + '\n*/}\n{/* docgen:end */}\n\n{/* docgen:with ' + slot)
        page.write_text(text)
        self.assertEqual(self.docgen_run('scaffold', '--project', 'demo').returncode, 0)
        text = page.read_text()
        self.assertNotIn('in the frame.', text)
        self.assertNotIn('The frame of the last step', text)
        self.assertEqual(sorted(p.stem for p in (self.site / 'captures' / 'demo').glob('stage*.json')), ['stage1-clone'])
        self.assertEqual(self.docgen_run('check', '--project', 'demo').returncode, 0)

    # ----- the one command form -----

    def code_blocks(self):
        """Each line of each code block of the pages, without the diagrams."""
        lines, fenced = [], False
        for path in PAGES:
            for line in self.page(path).read_text().splitlines():
                if line.strip().startswith('```'):
                    fenced = not fenced
                elif fenced:
                    lines.append(line.strip())
        return lines

    def test_a_command_with_a_capture_has_no_code_block(self):
        self.prepare()
        self.fill_all()
        self.assertEqual(self.docgen_run('scaffold', '--project', 'demo').returncode, 0)
        blocks = self.code_blocks()
        specs = sorted((self.site / 'captures' / 'demo').glob('*.json'))
        self.assertEqual(len(specs), 9)
        for spec in specs:
            command = json.loads(spec.read_text())['command']
            self.assertTrue(command, spec.name)
            self.assertNotIn(command, blocks, f'{spec.name}: the page shows the command also in a code block')
        # The frame of a step is inside the step: three spaces before it.
        install = self.page('install/index.mdx').read_text()
        for name in ('stage1-clone', 'stage3-start', 'stage4-check'):
            self.assertIn(f'\n   <Capture id="demo/{name}" />\n', install)
        # A command slot is a comment. The page does not show its command.
        build = self.page('use/commands/build.mdx').read_text()
        self.assertIn('{/* docgen:command\npython3 scripts/cli.py build\n*/}', build)

    def test_scaffold_takes_a_command_only_from_a_command_slot(self):
        self.prepare()
        page = self.page('install/index.mdx')
        page.write_text(page.read_text().replace('| slot stage-3-command */}', '| slot stage-3-steps */}'))
        fill(page, 'stage-3-steps', STEPS)
        done = self.docgen_run('scaffold', '--project', 'demo')
        self.assertIn("skipped  captures/demo/stage3-start.json: install/index.mdx: the slot 'stage-3-steps' "
                      'does not have the form `command`', done.stdout)
        self.assertEqual(json.loads(self.spec('stage3-start').read_text())['command'], '')

    def test_next_sends_the_agent_to_scaffold_when_no_slot_is_open(self):
        self.prepare()
        self.fill_all()
        done = self.docgen_run('next', '--project', 'demo')
        self.assertEqual(done.returncode, 0)
        self.assertIn('No open slot.', done.stdout)
        self.assertEqual(next_command(done.stdout), self.command('scaffold'))
        self.assertNotIn('then  ', done.stdout)

    # ----- check and status -----

    def test_check_reports_open_slots_then_passes(self):
        self.prepare()
        done = self.docgen_run('check', '--project', 'demo')
        self.assertEqual(done.returncode, 1)
        self.assertIn('open-slot', done.stdout)
        self.assertIn('note: the diagram', done.stdout)
        self.fill_all()
        # `scaffold` copies the command of each command slot into its spec. Without it, `check` reports each spec.
        self.assertEqual(self.docgen_run('scaffold', '--project', 'demo').returncode, 0)
        done = self.docgen_run('check', '--project', 'demo')
        self.assertEqual(done.returncode, 0, done.stdout)

    def test_check_finds_an_unknown_path(self):
        self.prepare()
        page = self.page('install/index.mdx')
        page.write_text(page.read_text().replace('TODO(docgen:goal)', 'Run `scripts/absent.py` now. ' + 'word ' * 12))
        done = self.docgen_run('check', '--project', 'demo')
        self.assertIn('unknown-path', done.stdout)

    def test_check_finds_an_unknown_path_in_a_command_slot(self):
        self.prepare()
        self.fill_all()
        fill_again = self.page('use/commands/build.mdx')
        fill_again.write_text(fill_again.read_text().replace(
            '{/* docgen:command\npython3 scripts/cli.py build\n', '{/* docgen:command\npython3 scripts/cli.py build scripts/absent.py\n'))
        done = self.docgen_run('check', '--project', 'demo')
        self.assertEqual(done.returncode, 1)
        self.assertIn('unknown-path: `scripts/absent.py` is not a file of the project', done.stdout)

    def test_check_finds_a_slot_of_a_wrong_form(self):
        self.prepare()
        self.fill_all()
        self.assertEqual(self.docgen_run('scaffold', '--project', 'demo').returncode, 0)
        self.assertEqual(self.docgen_run('check', '--project', 'demo').returncode, 0)
        cases = (
            ('index.mdx', 'parts', 'The parts are a program and a file. ' + 'word ' * 30, 'is not one Markdown table'),
            ('index.mdx', 'what-it-is', 'Give the file <name> to the tool. ' + 'word ' * 30, 'outside backticks'),
            ('use/commands/build.mdx', 'example-command', 'python3 scripts/cli.py build\nls', 'more than one command line'),
        )
        for path, slot, text, problem in cases:
            with self.subTest(slot=slot):
                page, original = self.page(path), self.page(path).read_text()
                line = self.write_slot(path, slot, text)
                done = self.docgen_run('check', '--project', 'demo')
                self.assertEqual(done.returncode, 1)
                # The finding names the file with its absolute path, the line of the slot, the rule and the slot.
                self.assertRegex(done.stdout, rf"(?m)^{re.escape(str(self.page(path)))}:{line}: slot-form: "
                                              rf"the slot '{slot}' has a fault of its form: .*{re.escape(problem)}.* Fix: ")
                self.assertIn('site     not run', done.stdout)
                page.write_text(original)
        self.assertEqual(self.docgen_run('check', '--project', 'demo').returncode, 0)

    def test_check_finds_a_command_in_a_code_block_and_in_a_frame(self):
        self.prepare()
        self.fill_all()
        page = self.page('install/index.mdx')
        fill_text = page.read_text().replace('   mkdir -p out\n', '   python3 scripts/cli.py build\n', 1)
        page.write_text(fill_text)
        line = fill_text.splitlines().index('   python3 scripts/cli.py build') + 1
        done = self.docgen_run('check', '--project', 'demo')
        self.assertEqual(done.returncode, 1)
        # The two captures of the fixture have the same command. One line gets one finding, and it names both.
        self.assertEqual(done.stdout.count('command-twice'), 1)
        # The finding starts with the absolute path of the page.
        self.assertIn(f"{self.page('install/index.mdx')}:{line}: command-twice: this code block and the frames "
                      "of the captures 'stage3-start' and 'stage4-check' show the same command. Fix: remove the step "
                      "with this code block from the slot 'stage-2-steps'. The frame shows the command. If the slot has "
                      "no step then, write: 1. The sources state no configuration step.", done.stdout.splitlines())

    def test_check_names_the_command_slot_when_the_script_wrote_the_code_block(self):
        self.prepare()
        self.fill_all()
        page = self.page('install/index.mdx')
        text = page.read_text()
        # Stage 1 of the template shows this command in a code block. The agent wrote it also as the start command.
        page.write_text(text.replace('{/* docgen:command\npython3 scripts/cli.py build\n', '{/* docgen:command\ncd "$HOME/demo"\n', 1))
        line = text.splitlines().index('   cd "$HOME/demo"') + 1
        done = self.docgen_run('check', '--project', 'demo')
        self.assertEqual(done.returncode, 1)
        self.assertEqual(done.stdout.count('command-twice'), 1)
        self.assertIn(f"{self.page('install/index.mdx')}:{line}: command-twice: this code block and the frame of "
                      "the capture 'stage3-start' show the same command. Fix: do not change this code block. The script "
                      "wrote it. Write in the slot 'stage-3-command' a command that this page does not show in a code "
                      "block. If the sources state no other command, write: The sources state no command that starts "
                      "the project.", done.stdout.splitlines())

    def test_status_lists_only_the_pages_of_a_changed_source(self):
        self.prepare()
        # A page with an open slot is an item of the list. So each slot has its text first.
        self.fill_all()
        self.assertEqual(self.docgen_run('scaffold', '--project', 'demo').returncode, 0)
        done = self.docgen_run('status', '--project', 'demo', '--repo', '.')
        self.assertEqual(done.returncode, 0)
        self.assertEqual(done.stdout.splitlines()[-2:], [
            '0 stale item(s)',
            'The pages of demo are current, and no file of the doc set waits for a commit. Nothing to do.'])
        (self.repo / 'docs' / 'setup.md').write_text('# Setup\n\nNew text.\n')
        self.git('switch', '-q', 'portable')
        self.git('commit', '-q', '-am', 'Change the setup')
        done = self.docgen_run('status', '--project', 'demo', '--repo', '.')
        self.assertEqual(done.returncode, 1)
        stale = [line.split()[1] for line in done.stdout.splitlines() if line.startswith('stale')]
        self.assertEqual(stale, ['install/index.mdx', 'reference/index.mdx'])
        self.assertIn('docs/setup.md changed', done.stdout)
        # The absolute path of the page to open, and the complete command that records its new sources.
        self.assertIn(f"           The page is the file {self.page('install/index.mdx')}", done.stdout)
        self.assertIn('           After you correct the page: ' + self.command('scaffold', '--refresh', 'install/index.mdx'),
                      done.stdout)
        self.assertNotIn('Nothing to do', done.stdout)
        self.assertNotIn('next ', done.stdout)

    # ----- the commands that the script prints -----

    def follow(self, line, until):
        """Run the command of each `next` line in a new shell, in a directory that is not the project and not the site.

        Write each slot that `next` prints into the file of its `page` line. Return the actions and the outputs.
        """
        elsewhere = self.tmp / 'elsewhere'
        elsewhere.mkdir(exist_ok=True)
        actions, outputs = [], []
        while len(actions) < 80:
            words = shlex.split(line)
            self.assertEqual(words[:2], ['python3', self.docgen], line)
            done = run('sh', '-c', line, cwd=elsewhere)
            self.assertEqual(done.returncode, 0, f'{line}\n{done.stdout}{done.stderr}')
            actions.append(words[2])
            outputs.append(done.stdout)
            if words[2] == until:
                break
            if re.search(r'(?m)^open slots ', done.stdout):
                page = Path(re.search(r'(?m)^page +(.+)$', done.stdout).group(1))
                name = re.search(r'(?m)^slot +([\w-]+) \(line \d+\)$', done.stdout).group(1)
                self.assertTrue(page.is_absolute(), page)
                fill(page, name, sample(next(slot for slot in docgen.slots_of(page.read_text()) if slot['id'] == name)))
            line = next_command(done.stdout)
        return actions, outputs

    def test_each_next_line_is_one_complete_command_and_the_lines_follow_the_steps(self):
        data = self.site / 'src' / 'data'
        data.mkdir()
        (data / 'projects.json').write_text('[]\n')
        (data / 'versions.json').write_text('{}\n')
        done = self.docgen_run('survey', '--repo', '.')
        # The site of this test is no Git checkout, so the `branch` command of this line cannot run here.
        # tests/test_docgen_git.py runs it. The line of `branch` names `plan`.
        self.assertEqual(next_command(done.stdout), self.command('branch'))
        actions, outputs = self.follow(self.command('plan'), 'check')
        slots = sum(len(docgen.slots_of(self.page(path).read_text())) for path in PAGES)
        self.assertGreater(slots, 20)
        # `next` runs one time for each slot and one time more. Then `scaffold` names `register`, and not `next` again.
        self.assertEqual(actions, ['plan', 'scaffold'] + ['next'] * (slots + 1) + ['scaffold', 'register', 'check'])
        self.assertIn('No open slot.', outputs[-4])
        self.assertIn('`register` sets the release. Continue.', outputs[1])
        self.assertIn('0 finding(s) in 7 page(s) of demo', outputs[-1])

    def test_scaffold_names_the_step_that_comes_after_it(self):
        self.prepare()
        self.fill_all()
        done = self.docgen_run('scaffold', '--project', 'demo')
        self.assertEqual(next_command(done.stdout), self.command('register'))
        # In an update, `status` comes after `scaffold`: it lists the pages that are stale then.
        done = self.docgen_run('scaffold', '--project', 'demo', '--refresh', 'install/index.mdx')
        self.assertEqual(next_command(done.stdout), self.command('status'))
        # An open slot comes first, also in an update.
        self.write_slot('index.mdx', 'status', 'TODO(docgen:status)')
        done = self.docgen_run('scaffold', '--project', 'demo', '--refresh', 'install/index.mdx')
        self.assertEqual(next_command(done.stdout), self.command('next'))

    def test_next_and_diagrams_print_the_absolute_path_of_the_page(self):
        self.prepare()
        done = self.docgen_run('next', '--project', 'demo')
        self.assertIn(f"page         {self.page('index.mdx')}", done.stdout)
        self.assertEqual(next_command(done.stdout), self.command('next'))
        done = self.docgen_run('diagrams', '--project', 'demo')
        self.assertIn(f"page      {self.page('index.mdx')}", done.stdout)
        self.assertIn(f"page      {self.page('develop/workflow.mdx')}", done.stdout)
        # The two commands that come after the diagrams.
        self.assertIn('check     ' + self.command('check'), done.stdout)
        self.assertIn('commit    ' + self.command('commit', '--diagrams'), done.stdout)
        # A fault in a written slot: the line names the file, and the next command.
        fill(self.page('index.mdx'), 'what-it-is', 'Give the file <name> to the tool. ' + 'word ' * 30)
        done = self.docgen_run('next', '--project', 'demo')
        self.assertRegex(done.stdout, rf"(?m)^correct      the slot what-it-is \(line \d+\) of {re.escape(str(self.page('index.mdx')))}$")
        self.assertEqual(next_command(done.stdout), self.command('next'))
        # `check` prints the diagrams command in its complete form.
        done = self.docgen_run('check', '--project', 'demo')
        self.assertIn('2 diagram(s) wait for the second pass: ' + self.command('diagrams'), done.stdout)
        self.assertRegex(done.stdout, rf"(?m)^{re.escape(str(self.page('index.mdx')))}:\d+: note: the diagram 'parts'")
        self.assertIn(f"open-slot: the slot 'parts' has no text. Fix: run `{self.command('next')}` and write the slot.", done.stdout)

    def test_a_missing_page_is_a_finding_with_the_scaffold_command(self):
        self.prepare()
        self.fill_all()
        self.page('use/commands/check.mdx').unlink()
        done = self.docgen_run('check', '--project', 'demo')
        self.assertEqual(done.returncode, 1)
        self.assertIn(f"{self.page('use/commands/check.mdx')}:1: missing-page: the state lists this page, and the file is "
                      f"absent. Fix: run `{self.command('scaffold')}`.", done.stdout.splitlines())

    # ----- the state of a project that is absent -----

    def test_an_absent_state_has_one_message_for_each_kind_of_action(self):
        self.assertEqual(self.docgen_run('survey', '--repo', '.').returncode, 0)
        # `status` and `diagrams` need a doc set that exists. `scaffold` here makes a second, empty doc set.
        for words in (('status', '--project', 'demo', '--repo', '.'), ('diagrams', '--project', 'demo')):
            with self.subTest(action=words[0]):
                done = self.docgen_run(*words)
                self.assertEqual(done.returncode, 2)
                self.assertEqual(done.stderr.strip(), "error: this checkout of the site has no doc set of 'demo': the file "
                                 'docgen/state/demo.json is absent. No branch holds it: the skill tenant-docs-generate '
                                 'makes it. Stop and tell the user this line.')
                self.assertNotIn('scaffold', done.stderr)
        # `next` and `check` are steps of a first doc set. Their hint stays.
        for action in ('next', 'check'):
            with self.subTest(action=action):
                done = self.docgen_run(action, '--project', 'demo')
                self.assertEqual(done.returncode, 2)
                self.assertIn("error: the state of 'demo' (run scaffold first) is absent", done.stderr)

    # ----- a project with no release tag -----

    def test_plan_stops_for_a_full_doc_set_of_a_project_with_no_release_tag(self):
        self.git('tag', '-d', 'portable-v0.1.0')
        done = self.docgen_run('survey', '--repo', '.')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('               A full doc set needs a release tag: `plan` stops without it.', done.stdout)
        done = self.docgen_run('plan', '--project', 'demo')
        self.assertEqual(done.returncode, 2)
        self.assertRegex(done.stderr.strip(), r"^error: '[0-9a-f]{7,40}' is not a release tag of the branch portable\. A project "
                         r'with a full doc set needs a tag of the form portable-v<major>\.<minor>\.<patch> and '
                         r'portable/<date>-<hash>\. Do not make the tag\. Stop and tell the user this line\.$')
        self.assertFalse((self.site / '.docgen' / 'demo' / 'plan.json').exists())
        # A project with an overview only keeps a commit as its release.
        done = self.docgen_run('plan', '--project', 'demo', '--doc-set', 'overview')
        self.assertEqual(done.returncode, 0, done.stderr)

    # ----- the files have no answer -----

    def template_slots(self):
        return {(template.stem, slot['id']): slot for template in sorted((ROOT / 'docgen' / 'profiles' / 'v1').glob('*.mdx'))
                for slot in docgen.slots_of(template.read_text())}

    def test_next_says_what_to_write_when_the_files_have_no_answer(self):
        slots = self.template_slots()
        part = 'Keep the form. For one cell that the files do not state, write in that cell: '
        stop = 'When the files have no answer for the full slot, stop. Tell the user the page and the slot.'
        whole = 'When the files have no answer for the full slot, write only this text: '
        cases = {
            # A table with no sentence of its own for the full slot.
            ('workflow', 'branches'): [part + 'The sources do not state this.', stop],
            # An instruction that gives its own words for one cell.
            ('install', 'requirements'): [part + 'Not stated', stop],
            ('commands', 'command-table'): [part + 'Not stated', stop],
            ('workflow', 'roles'): [part + 'The sources do not state this.', whole + 'The sources name no role.'],
            ('overview', 'audience'): ['Keep the form. For one item that the files do not state, write in that item: '
                                       'The sources do not state this.', stop],
            ('workflow', 'flow-steps'): ['Keep the form. For one item that the files do not state, write in that item: '
                                         'The sources do not state this.', stop],
            ('install', 'stage-2-steps'): ['Keep the form. For a result that the files do not state, write the line: '
                                           'Result: The sources do not state this.',
                                           whole + '1. The sources state no configuration step.'],
            ('overview', 'what-it-is'): ['Keep the form. For one fact that the files do not state, write one sentence that '
                                         'starts with `The sources do not state`.', stop],
            # A slot of one sentence and a command slot have one part.
            ('install', 'stage-2-result'): [whole + '**Result:** this stage changes nothing.'],
            ('install', 'stage-3-command'): ['When the files give no such command, write only this text: '
                                             'The sources state no command that starts the project.'],
            ('command', 'example-command'): ['When the files give no such command, stop. Tell the user the page and the slot.'],
        }
        for key, lines in cases.items():
            with self.subTest(slot=key):
                self.assertEqual(docgen.no_answer_lines(slots[key]), lines)
        for key, slot in slots.items():
            with self.subTest(slot=key):
                last = docgen.no_answer_lines(slot)[-1]
                self.assertEqual(last.endswith('stop. Tell the user the page and the slot.'), not docgen.fallback_of(slot))
        # `next` prints the lines below the length of the slot.
        self.prepare()
        done = self.docgen_run('next', '--project', 'demo')
        self.assertIn('length       30 to 90 words\n'
                      'no answer    Keep the form. For one fact that the files do not state, write one sentence that starts '
                      'with `The sources do not state`.\n'
                      '             ' + stop + '\nrules ', done.stdout)

    def test_the_steps_form_has_a_rule_for_a_step_with_no_command(self):
        self.assertIn('When the files give no command for a step, the step has no code block. Do not build a command.',
                      docgen.FORMS['steps'])

    def test_a_part_with_no_answer_keeps_the_form_of_its_slot(self):
        self.prepare()
        self.fill_all()
        self.assertEqual(self.docgen_run('scaffold', '--project', 'demo').returncode, 0)
        sentence = 'The sources do not state this.'
        words = 'word ' * 12
        parts = (
            # One cell of a table.
            ('develop/workflow.mdx', 'branches', '| Branch | What it holds | Who writes to it |\n| --- | --- | --- |\n'
             f'| `main` | The development. {words}| {sentence} |\n| `portable` | The release. | {sentence} |'),
            # One item of a list, and one item of a numbered list.
            ('index.mdx', 'audience', f'- A developer who builds a small thing. {words}\n- {sentence}'),
            ('develop/workflow.mdx', 'flow-steps', f'1. The developer makes a branch. {words}\n2. {sentence}\n'
             f'3. The owner merges the branch. {sentence}'),
            # The result of a step, and a step with no command in the sources.
            ('install/index.mdx', 'stage-2-steps', '1. Copy the example file.\n\n   ```sh\n   cp .env.example .env\n   ```\n\n'
             f'   Result: {sentence}\n\n2. Open the page of the service.\n\n   Result: {sentence}'),
            # One sentence of a text.
            ('use/commands/build.mdx', 'what-it-does', f'The action builds a small thing. {words}'
             'The sources do not state if the action writes a file.'),
        )
        for path, slot, text in parts:
            self.write_slot(path, slot, text)
        done = self.docgen_run('next', '--project', 'demo')
        self.assertIn('No open slot.', done.stdout)
        self.assertNotIn('problem', done.stdout)
        done = self.docgen_run('check', '--project', 'demo')
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertIn('0 finding(s) in 7 page(s) of demo', done.stdout)
        # The sentence is not the text of a full slot. The form check and the length check stay as they are.
        for path, slot, rule in (('develop/workflow.mdx', 'branches', 'slot-form'), ('install/index.mdx', 'goal', 'slot-length'),
                                 ('develop/workflow.mdx', 'flow-steps', 'slot-form'), ('index.mdx', 'what-it-is', 'slot-length')):
            with self.subTest(slot=slot):
                original = self.page(path).read_text()
                self.write_slot(path, slot, sentence)
                done = self.docgen_run('check', '--project', 'demo')
                self.assertEqual(done.returncode, 1)
                self.assertIn(f"{rule}: the slot '{slot}' ", done.stdout)
                self.page(path).write_text(original)


if __name__ == '__main__':
    unittest.main()
