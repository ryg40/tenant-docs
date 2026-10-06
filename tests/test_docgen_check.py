"""Tests of the gate of docgen/docgen.py: the rules of `check` and the problems that `next` reports.

Each test works in a temporary site with the fixture project of the other docgen tests.
Each sample value of one host is built at run time from parts. So this file holds no value that the scanner finds.
"""

import json
import re
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_docgen as base  # noqa: E402  The fixture project and the helpers of the other docgen tests.

ROOT = Path(__file__).resolve().parent.parent
docgen = base.docgen


def j(*parts):
    return ''.join(parts)


ADDRESS = j('192', '.168.7.20')
HOME = j('/ho', 'me/dana/demo')


class GateCase(unittest.TestCase):
    """A site with no scanner, and one project with a command line, a setup guide and a test."""

    setUp = base.DocgenTest.setUp
    git = base.DocgenTest.git
    docgen_run = base.DocgenTest.docgen_run
    prepare = base.DocgenTest.prepare
    page = base.DocgenTest.page
    command = base.DocgenTest.command
    spec = base.DocgenTest.spec
    fill_all = base.DocgenTest.fill_all
    write_slot = base.DocgenTest.write_slot
    no_tests = base.DocgenTest.no_tests

    def written(self):
        """Make a doc set with each slot written and each capture spec current. `check` passes for it."""
        self.prepare()
        self.fill_all()
        done = self.docgen_run('scaffold', '--project', 'demo')
        self.assertEqual(done.returncode, 0, done.stderr)

    def check(self):
        return self.docgen_run('check', '--project', 'demo')

    def next(self):
        return self.docgen_run('next', '--project', 'demo')

    def lines(self, done, rule):
        """The lines of one rule in the output of `check`."""
        return [line for line in done.stdout.splitlines() if re.match(rf'\S+:\d+: (?:note: )?{re.escape(rule)}: ', line)]

    def edit(self, path, old, new):
        """Replace one text of a page. Return the number of the first line of that text."""
        text = self.page(path).read_text()
        self.assertEqual(text.count(old), 1, f'{path}: {old!r}')
        self.page(path).write_text(text.replace(old, new))
        return text[:text.index(old)].count('\n') + 1

    def line_of(self, path, needle):
        """The number of the one line of a page that holds a text."""
        found = [number for number, line in enumerate(self.page(path).read_text().splitlines(), 1) if needle in line]
        self.assertEqual(len(found), 1, f'{path}: {needle!r}')
        return found[0]

    def project_file(self, path, text):
        """Write one file of the fixture project on the release branch and on the develop branch."""
        for branch in ('portable', 'main'):
            self.git('switch', '-q', branch)
            (self.repo / path).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / path).write_text(text)
            self.git('add', path)
            self.git('commit', '-q', '-m', f'Change {path}')

    def assert_passes(self, done=None):
        done = done or self.check()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn('0 finding(s) in 7 page(s) of demo', done.stdout)
        return done


MADE = {}  # One site with a written doc set for each kind of site: with no scanner, and with the scanner.


def tearDownModule():
    for maker in MADE.values():
        shutil.rmtree(maker.tmp, ignore_errors=True)
    MADE.clear()


class SharedCase(GateCase):
    """One written doc set for many tests. The `check` of the site runs each test, so the time of the tests counts.

    The first class makes the site and the project one time. Each test starts with the same files of the doc set.
    A test that changes the project, or that needs open slots, uses `GateCase`: it gets its own site and project.
    """

    PARTS = ('src/content/docs/demo', 'captures/demo', 'docgen/state', '.docgen/demo')

    @classmethod
    def setUpClass(cls):
        kind = cls.site_files.__func__
        if kind not in MADE:
            maker = GateCase()
            GateCase.setUp(maker)
            MADE[kind] = maker
            cls.site_files(maker)
            GateCase.written(maker)
            for part in cls.PARTS:
                shutil.copytree(maker.site / part, maker.tmp / 'snapshot' / part)
        cls.maker = MADE[kind]

    @classmethod
    def site_files(cls, maker):
        """A class can add files to its site here, before the first action runs."""

    def setUp(self):
        maker = self.maker
        self.tmp, self.site, self.docgen, self.docs, self.repo = maker.tmp, maker.site, maker.docgen, maker.docs, maker.repo
        for part in self.PARTS:
            shutil.rmtree(self.site / part)
            shutil.copytree(self.tmp / 'snapshot' / part, self.site / part)

    def written(self):
        """The class made the doc set. Each test starts with it."""


# ----- values of one host -----

class HostValueTest(SharedCase):
    def test_each_kind_of_host_value_has_its_own_fix(self):
        self.written()
        cases = (
            (f'The service answers at `{ADDRESS}`.', f'a private IP address: `{ADDRESS}`', 'write the example address `192.0.2.10`'),
            (f'The file is `{HOME}/.env`.', f'an absolute path of one host: `{HOME[:10]}`', 'write `~` in place of the home directory'),
            (j('The files are in `/op', 't/stacks/demo`.'), 'an absolute path of one host: `' + j('/op', 't/stacks') + '`',
             'write the path from the directory of the clone, with no `/` at its start. For the directory of the clone, '
             'write `~/demo`.'),
            (j('Open `http', '://wiki.corp', '.internal/page`.'), 'an internal URL: `' + j('http', '://wiki.corp', '.internal') + '`',
             'write the example host `docs.example` in place of the host name'),
        )
        original = self.page('index.mdx').read_text()
        for sentence, what, fix in cases:
            with self.subTest(what=what):
                line = self.write_slot('index.mdx', 'what-it-is', sentence + ' ' + self.index_slot()) + 1
                done = self.check()
                self.assertEqual(done.returncode, 1, done.stdout)
                found = self.lines(done, 'host-value')
                self.assertEqual(len(found), 1, done.stdout)
                self.assertTrue(found[0].startswith(f"{self.page('index.mdx')}:{line}: host-value: the line holds {what}. Fix: {fix}"),
                                found[0])
                self.page('index.mdx').write_text(original)

    def index_slot(self):
        """The text of the first slot of the overview page: 30 times `word`."""
        return ' '.join(['word'] * 30) + '.'

    def test_a_loopback_address_and_a_documentation_address_are_no_values_of_one_host(self):
        # The rule follows the scanner of the site. A README states the loopback address of a service.
        self.written()
        self.edit('index.mdx', self.index_slot(), j('The service listens on `127', '.0.0.1:6770`. The example address is `192',
                                                     '.0.2.10`. The data is in `/srv/demo/data`. ') + self.index_slot())
        done = self.assert_passes()
        self.assertEqual(self.lines(done, 'host-value'), [])

    def test_check_finds_the_path_of_the_site_and_the_path_of_the_clone(self):
        # `next` prints both paths. A generic rule does not know a path below a temporary directory.
        self.written()
        line = self.edit('index.mdx', self.index_slot(),
                         f'Run `python3 {self.site}/docgen/docgen.py check`.\nRun `git -C {self.repo} show portable:README.md`.\n'
                         + self.index_slot())
        done = self.check()
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertEqual(self.lines(done, 'host-value'), [
            f"{self.page('index.mdx')}:{line}: host-value: the line holds the path of the tenant-docs checkout on this machine: "
            f"`{self.site}`. Fix: remove the path. A page does not name the tenant-docs checkout.",
            f"{self.page('index.mdx')}:{line + 1}: host-value: the line holds the path of the project clone on this machine: "
            f"`{self.repo}`. Fix: remove the path. A command of a page runs in the directory of the clone, so it needs no absolute "
            "path. For the directory of the clone, write `~/demo`."])
        # A directory with a longer name is another directory.
        self.page('index.mdx').write_text(self.page('index.mdx').read_text().replace(f'{self.site}/', f'{self.site}-2/')
                                          .replace(f'{self.repo} show', f'{self.repo}.git show'))
        self.assertEqual(self.lines(self.check(), 'host-value'), [])

    def test_check_finds_the_path_of_the_site_in_a_url(self):
        # The path of a `file:` URL has a `/` before it. It is the same path of this machine.
        self.written()
        line = self.edit('index.mdx', self.index_slot(), f'Open `file://{self.site}/dist/index.html` in a browser.\n'
                         + self.index_slot())
        self.assertEqual(self.lines(self.check(), 'host-value'), [
            f"{self.page('index.mdx')}:{line}: host-value: the line holds the path of the tenant-docs checkout on this machine: "
            f"`{self.site}`. Fix: remove the path. A page does not name the tenant-docs checkout."])
        self.assertIn(f'problem      line {line} holds the path of the tenant-docs checkout on this machine: `{self.site}`. '
                      'Remove the path. A page does not name the tenant-docs checkout.', self.next().stdout.splitlines())
        # A longer path that ends with the same words is another path.
        self.page('index.mdx').write_text(self.page('index.mdx').read_text().replace(f'file://{self.site}/', f'file:///srv{self.site}/'))
        self.assertEqual(self.lines(self.check(), 'host-value'), [])

    def test_check_finds_the_clone_also_by_its_real_path(self):
        self.written()
        link = self.tmp / 'link-to-the-clone'
        link.symlink_to(self.repo)
        (self.site / '.docgen' / 'demo' / 'repo').write_text(f'{link}\n')
        self.edit('index.mdx', self.index_slot(), f'The clone is `{self.repo}`.\nThe link is `{link}`.\n' + self.index_slot())
        found = self.lines(self.check(), 'host-value')
        self.assertEqual(len(found), 2, found)
        self.assertIn(f'the path of the project clone on this machine: `{self.repo}`', found[0])
        self.assertIn(f'the path of the project clone on this machine: `{link}`', found[1])

    def test_next_reports_a_host_value_in_a_written_slot(self):
        self.written()
        page = self.page('index.mdx')
        self.write_slot('index.mdx', 'what-it-is', f'The service answers at `{ADDRESS}`. ' + self.index_slot())
        line = self.line_of('index.mdx', ADDRESS)
        done = self.next()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(f'correct      the slot what-it-is (line {line - 1}) of {page}', done.stdout.splitlines())
        self.assertIn(f'problem      line {line} holds a private IP address: `{ADDRESS}`. Write the example address `192.0.2.10` '
                      'in its place. If the files of the project give an example host, write that host.', done.stdout.splitlines())
        # After the correction, `next` has no slot to correct.
        page.write_text(page.read_text().replace(f'The service answers at `{ADDRESS}`. ', ''))
        self.assertIn('No open slot.', self.next().stdout)

    def test_check_reads_the_state_file_and_each_capture_spec(self):
        self.written()
        spec = self.spec('dev-tests')
        data = json.loads(spec.read_text())
        data['setup'].append(f'cd {HOME}')
        spec.write_text(json.dumps(data, indent=2) + '\n')
        state = self.site / 'docgen' / 'state' / 'demo.json'
        state.write_text(state.read_text().replace('{\n', '{\n "note": "' + ADDRESS + '",\n', 1))
        done = self.check()
        self.assertEqual(done.returncode, 1, done.stdout)
        found = self.lines(done, 'host-value')
        self.assertEqual(len(found), 2, done.stdout)
        self.assertRegex(found[0], rf'^{re.escape(str(spec))}:\d+: host-value: the line holds an absolute path of one host: .* '
                                   r'Fix: do not edit this file\. Correct the command slot of the page that holds the value\. '
                                   r'Then run `' + re.escape(self.command('scaffold')) + '`')
        self.assertEqual(found[1], f'{state}:2: host-value: the line holds a private IP address: `{ADDRESS}`. Fix: do not edit '
                                   'this file. The script writes it. Stop and tell the user this line.')


class ScannerTest(SharedCase):
    """A site with the scanner of the site. No file of the doc set is tracked: the site is no Git repository."""

    slot = ' '.join(['word'] * 30) + '.'

    @classmethod
    def site_files(cls, maker):
        for name in ('scan.py', 'host-values.regex', 'host-values.allow'):
            shutil.copy(ROOT / 'scripts' / name, maker.site / 'scripts' / name)
        # The local deny list of the temporary site, and not the list of this host.
        (maker.site / 'scripts' / 'host-values.local.deny').write_text('buildbox-nine\n')

    def test_check_runs_the_scanner_on_the_files_of_the_doc_set(self):
        self.written()
        unique_local = j('fd12', ':3456::1')
        url = j('http', '://buildbox:6770')
        allowed = j('/ho', 'me/alex/demo')
        line = self.edit('index.mdx', self.slot, f'The address is `{unique_local}`.\nOpen `{url}/browse`.\nThe home is `{allowed}`.\n'
                                                 'The machine is `Buildbox-Nine`.\n' + self.slot)
        done = self.check()
        self.assertEqual(done.returncode, 1, done.stdout)
        page = self.page('index.mdx')
        self.assertEqual(self.lines(done, 'host-value'), [
            f'{page}:{line}: host-value: the line holds a private IP address: `{unique_local}`. Fix: write the example address '
            '`2001:db8::1` in its place.',
            f'{page}:{line + 1}: host-value: the line holds an internal URL: `{url.rsplit(":", 1)[0]}`. Fix: write the example '
            'host `docs.example` in place of the host name, for example `https://docs.example`.',
            # The allow list of the scanner holds the home of the capture container: no finding for line + 2.
            f'{page}:{line + 3}: host-value: the line holds a value of this machine that the local deny list of the site names '
            'at column 17. Fix: the scanner does not show the value. Find the host name, the user name, the address or the path '
            'of this machine at that column. Write a placeholder in its place: `docs.example` for a host, `~` for a home '
            'directory.'])
        self.assertNotIn('uildbox-nine', done.stdout.lower().replace('buildbox-nine`.', ''))

    def test_a_credential_is_a_finding_and_its_value_does_not_show(self):
        self.written()
        token = j('ghp', '_', 'Zx9QwEr7TyUi3OpAs5DfGh1JkLz2XcVbNm4Q')
        line = self.edit('index.mdx', self.slot, f'The token is `{token}`.\n' + self.slot)
        done = self.check()
        self.assertEqual(self.lines(done, 'host-value'), [
            f"{self.page('index.mdx')}:{line}: host-value: the line holds a credential at column 15. Fix: remove the value. "
            'Write the name of the variable or of the file that holds it, and never the value.'])
        self.assertNotIn(token, done.stdout + done.stderr)

    def test_next_uses_the_scanner_too(self):
        self.written()
        url = j('http', '://buildbox:6770')
        self.write_slot('index.mdx', 'what-it-is', f'Open `{url}/browse`. ' + self.slot)
        self.assertIn(f'holds an internal URL: `{url.rsplit(":", 1)[0]}`. Write the example host `docs.example`', self.next().stdout)

    def test_the_own_list_is_the_fallback_when_the_scanner_does_not_run(self):
        self.written()
        rules = self.site / 'scripts' / 'host-values.regex'
        self.addCleanup(rules.write_text, rules.read_text())
        rules.write_text('not a rule file\n')
        self.edit('index.mdx', self.slot, f'The address is `{ADDRESS}`. ' + self.slot)
        found = self.lines(self.check(), 'host-value')
        self.assertEqual(len(found), 1, found)
        self.assertIn(f'a private IP address: `{ADDRESS}`', found[0])


# ----- the docgen lines of a page -----

class DocgenLineTest(SharedCase):
    FIRST = ('{/* docgen:slot what-it-is | 30-90 words | text | Say what demo is and what it does, in three to five short '
             'sentences. Give each special word of the project its own sentence that says what the word means. Take the facts '
             'from the README. */}')

    def one(self, done):
        self.assertEqual(done.returncode, 1, done.stdout)
        found = self.lines(done, 'docgen-line')
        self.assertEqual(len(found), 1, done.stdout)
        self.assertIn('1 finding(s) in 7 page(s) of demo', done.stdout)
        return found[0]

    def test_a_slot_with_no_first_line_is_a_finding_with_the_exact_line(self):
        # The agent removed the comment line above the slot. The page then shows the text `TODO(docgen:...)`.
        self.written()
        text = self.page('index.mdx').read_text()
        start = text.index(self.FIRST)
        end = text.index(docgen.SLOT_END, start)
        self.page('index.mdx').write_text(text[:start] + 'TODO(docgen:what-it-is)\n' + text[end:])
        self.assertIn('No open slot.', self.next().stdout)
        above = self.line_of('index.mdx', '<DocVersion project="demo" />')
        self.assertEqual(self.one(self.check()),
                         f"{self.page('index.mdx')}:{above}: docgen-line: the page does not have the first line of the slot "
                         f"'what-it-is'. Fix: put this exact line back below line {above} of the page (<DocVersion "
                         f'project="demo" />), with one empty line between them: {self.FIRST}')
        # With the line back, the slot is open again, and `check` says so.
        self.page('index.mdx').write_text(text[:start] + self.FIRST + '\nTODO(docgen:what-it-is)\n' + text[end:])
        done = self.check()
        self.assertEqual(self.lines(done, 'docgen-line'), [])
        self.assertEqual(len(self.lines(done, 'open-slot')), 1)

    def test_a_slot_with_no_end_line_is_a_finding(self):
        self.written()
        line = self.line_of('index.mdx', 'docgen:slot what-it-is')
        text = self.page('index.mdx').read_text()
        at = text.index(docgen.SLOT_END)
        self.page('index.mdx').write_text(text[:at] + text[at + len(docgen.SLOT_END) + 1:])
        self.assertEqual(self.one(self.check()),
                         f"{self.page('index.mdx')}:{line}: docgen-line: the page does not have the line `{{/* docgen:end */}}` of "
                         "the slot 'what-it-is'. Fix: put this exact line back directly below the last line of the text of the slot "
                         "'what-it-is': {/* docgen:end */}")

    def test_a_changed_word_range_or_form_is_a_finding_and_no_form_fault(self):
        self.written()
        for old, new in (('what-it-is | 30-90 words | text', 'what-it-is | 3-900 words | text'),
                         ('what-it-is | 30-90 words | text', 'what-it-is | 30-90 words | table'),
                         ('docgen:slot what-it-is | 30-90', 'docgen:slot summary | 30-90')):
            with self.subTest(new=new):
                original = self.page('index.mdx').read_text()
                line = self.edit('index.mdx', old, new)
                done = self.check()
                self.assertEqual(self.one(done), f"{self.page('index.mdx')}:{line}: docgen-line: this line is not the first line "
                                 f"of the slot 'what-it-is' as the script wrote it. Fix: write this exact line in its place: {self.FIRST}")
                # The form and the range of a changed line give no second finding: they are not the ones of the template.
                self.assertEqual(self.lines(done, 'slot-form') + self.lines(done, 'slot-length'), [])
                self.page('index.mdx').write_text(original)
        # `next` reports the same line while the agent knows the slot.
        self.edit('index.mdx', 'what-it-is | 30-90 words | text', 'what-it-is | 30-90 words | table')
        self.assertIn('problem      the comment line above the slot is not the line that the script wrote. It must hold '
                      '`| 30-90 words | text |`. Put these values back.', self.next().stdout.splitlines())

    def test_a_removed_marker_of_a_part_is_a_finding(self):
        self.written()
        page = self.page('install/index.mdx')
        text = page.read_text()
        marker = '   {/* docgen:with stage-3-command */}\n'
        self.assertEqual(text.count(marker), 1)
        page.write_text(text.replace(marker, ''))
        # The line above it in the template is the end line of the slot `stage-3-steps`.
        above = text[:text.index(marker)].count('\n') - 1
        self.assertEqual(text.splitlines()[above - 1], '   {/* docgen:end */}')
        self.assertEqual(self.one(self.check()),
                         f"{page}:{above}: docgen-line: the page does not have the marker `docgen:with stage-3-command`. Fix: put "
                         f"this exact line back below line {above} of the page ({{/* docgen:end */}}), with one empty line between "
                         "them: {/* docgen:with stage-3-command */} Put 3 blanks before it.")

    def test_a_changed_capture_mark_and_a_removed_capture_line_are_findings(self):
        self.written()
        page = self.page('install/index.mdx')
        original = page.read_text()
        mark = '   {/* docgen:capture stage3-start | 300 | Install and start | slot stage-3-command */}'
        for new in ('   {/* docgen:capture stage3-run | 300 | Install and start | slot stage-3-command */}',
                    '   {/* docgen:capture stage3-start | 300 | Install and start | run rm -r out */}'):
            with self.subTest(new=new):
                line = self.edit('install/index.mdx', mark, new)
                done = self.check()
                self.assertEqual(self.one(done), f"{page}:{line}: docgen-line: this line is not the capture mark 'stage3-start' as "
                                 f"the script wrote it. Fix: write this exact line in its place: {mark.strip()} Put 3 blanks before it.")
                self.assertEqual(self.lines(done, 'stale-spec'), [])
                page.write_text(original)
        line = self.edit('install/index.mdx', '   <Capture id="demo/stage3-start" />\n', '')
        self.assertEqual(self.one(self.check()),
                         f"{page}:{line - 1}: docgen-line: the page does not have the `Capture` line of the capture "
                         f"'demo/stage3-start'. Fix: put this exact line back below line {line - 1} of the page ({mark.strip()[:70]}), "
                         'with no line between them: <Capture id="demo/stage3-start" /> Put 3 blanks before it.')

    def test_cast_in_place_of_capture_passes(self):
        # A person changes `Capture` to `Cast` at the review.
        self.written()
        self.edit('install/index.mdx', '<Capture id="demo/stage3-start" />', '<Cast id="demo/stage3-start" />')
        self.assert_passes()

    def test_single_quotes_around_the_id_of_a_frame_pass(self):
        # Both quotes are the same component for the build. A finding here asks for a second frame of one capture.
        self.written()
        self.edit('install/index.mdx', '<Capture id="demo/stage3-start" />', "<Capture id='demo/stage3-start' />")
        self.assert_passes()

    def test_a_docgen_line_that_the_script_does_not_read_is_a_finding_at_that_line(self):
        # The agent changed a word of a docgen line. The script does not know the line then, and the page has it.
        # The fix replaces that line. A fix that puts a second line above it leaves the changed line in the text.
        self.written()
        diagram = ('{/* docgen:diagram loop | pending | One `flowchart TD` with one node for each step of the list below, in the '
                   'same order. The first line of each node names who does the step. */}')
        cases = (('index.mdx', '{/* docgen:slot what-it-is |', '{/* docgen-slot what-it-is |',
                  "the first line of the slot 'what-it-is'", self.FIRST),
                 ('install/index.mdx', '{/* docgen:capture stage3-start |', '{/* docgen: capture stage3-start |',
                  "the capture mark 'stage3-start'", '{/* docgen:capture stage3-start | 300 | Install and start | slot '
                  'stage-3-command */} Put 3 blanks before it.'),
                 ('develop/workflow.mdx', '{/* docgen:diagram loop | pending |', '{/* docgen:diagram loop | waits |',
                  "the comment of the diagram 'loop'", diagram))
        for path, old, new, what, exact in cases:
            with self.subTest(what=what):
                original = self.page(path).read_text()
                line = self.edit(path, old, new)
                self.assertEqual(self.one(self.check()), f'{self.page(path)}:{line}: docgen-line: this line is not {what} as the '
                                 f'script wrote it. Fix: write this exact line in its place: {exact}')
                self.page(path).write_text(original)
        # The comment with the source files of a page is no changed docgen line, also when it holds the name of a slot.
        self.edit('develop/workflow.mdx', 'docgen: sources of this page, at the ref main:', 'docgen: sources of this page (loop), '
                  'at the ref main:')
        line = self.edit('develop/workflow.mdx', '{/* docgen:slot loop | 30-110 words | text | ', '{/* a slot | ')
        self.assertIn(f"docgen-line: the page does not have the first line of the slot 'loop'. Fix: put this exact line back "
                      f'below line {line - 2} of the page', self.one(self.check()))

    def test_a_capture_line_that_the_script_does_not_read_is_a_finding_at_that_line(self):
        # The agent changed the quotes of the `Capture` line. The script does not read the line then, and the page has
        # it. A fix that puts the exact line back leaves two frame lines, and the build stops at the changed one.
        self.written()
        page = self.page('install/index.mdx')
        original = page.read_text()
        exact = '<Capture id="demo/stage3-start" />'
        for new in ('<Capture id=demo/stage3-start />', '<Capture id=\'demo/stage3-start" />', '<Cast id=demo/stage3-start />',
                    '<Capture />'):
            with self.subTest(new=new):
                page.write_text(original)
                line = self.edit('install/index.mdx', exact, new)
                self.assertEqual(self.one(self.check()),
                                 f"{page}:{line}: docgen-line: this line is not the `Capture` line of the capture "
                                 f"'demo/stage3-start' as the script wrote it. Fix: write this exact line in its place: {exact} "
                                 'Put 3 blanks before it.')
        # A line below the capture mark that is no complete tag of a frame is not that line: a sentence, and the first
        # line of a tag of two lines. A fix "in its place" replaces one line, and the second line of the tag stays.
        for new in ('The frame shows the command.', '<Capture\n     id="demo/stage3-start" />'):
            with self.subTest(new=new):
                page.write_text(original)
                line = self.edit('install/index.mdx', exact, new)
                self.assertIn(f"{page}:{line - 1}: docgen-line: the page does not have the `Capture` line of the capture "
                              f"'demo/stage3-start'. Fix: put this exact line back below line {line - 1} of the page",
                              self.one(self.check()))

    def test_a_diagram_comment_can_say_done_only_with_a_diagram(self):
        self.written()
        page = self.page('develop/workflow.mdx')
        line = self.edit('develop/workflow.mdx', 'docgen:diagram loop | pending |', 'docgen:diagram loop | done |')
        self.assertEqual(self.one(self.check()),
                         f"{page}:{line}: docgen-line: the comment of the diagram 'loop' says `done`, and no `mermaid` code block is "
                         "between this line and the line `{/* docgen:end-diagram */}`. Fix: change the word `done` in this line "
                         "back to `pending`. A larger model draws the diagram.")
        # With a diagram between the two lines, `done` passes. A diagram below a `pending` comment passes too.
        diagram = '```mermaid\nflowchart TD\n    accTitle: The loop\n    a["Author"] --> b["Owner"]\n```\n{/* docgen:end-diagram */}'
        page.write_text(page.read_text().replace('{/* docgen:end-diagram */}', diagram))
        self.assert_passes()
        page.write_text(page.read_text().replace('docgen:diagram loop | done |', 'docgen:diagram loop | pending |'))
        self.assert_passes()

    def test_a_line_at_a_wrong_place_and_a_line_with_wrong_blanks_are_findings(self):
        self.written()
        page = self.page('install/index.mdx')
        original = page.read_text()
        mark = '   {/* docgen:capture stage4-check | 400 | Check the install | slot stage-4-command */}\n'
        self.assertEqual(original.count(mark), 1)
        page.write_text(original.replace(mark, '').replace('{/* docgen:slot stage-4-steps', mark + '{/* docgen:slot stage-4-steps'))
        line = self.line_of('install/index.mdx', 'docgen:capture stage4-check')
        self.assertRegex(self.one(self.check()),
                         rf"^{re.escape(str(page))}:{line}: docgen-line: the capture mark 'stage4-check' is at a wrong place\. Fix: "
                         r"move this line\. Put it below line \d+ of the page \(1\. Test the install with the command in the "
                         r"frame\.\), with one empty line between them\.$")
        page.write_text(original.replace(mark, mark.lstrip()))
        line = self.line_of('install/index.mdx', 'docgen:capture stage4-check')
        self.assertEqual(self.one(self.check()),
                         f"{page}:{line}: docgen-line: the capture mark 'stage4-check' has no blank before it, and the script "
                         "wrote it with 3 blanks. Fix: write the line with exactly 3 blanks before it.")


class PartTest(SharedCase):
    """A part of the Install page that depends on a command slot, with a marker line that the agent removed."""

    def scaffold(self):
        done = self.docgen_run('scaffold', '--project', 'demo')
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def test_a_part_with_no_end_line_stays_as_it_is(self):
        self.written()
        page = self.page('install/index.mdx')
        original = page.read_text()
        opening, end = '{/* docgen:without stage-3-command */}', '{/* docgen:end-without */}'
        self.assertEqual(original.count(f'{opening}\n{end}\n'), 1)
        # The slots of stage 4 come after this part. With no end line, the next end line of this kind is the one of stage 4.
        text = original.replace(f'{opening}\n{end}\n', f'{opening}\n')
        page.write_text(text)
        line = self.line_of('install/index.mdx', opening)
        done = self.check()
        self.assertEqual(self.lines(done, 'stale-part'), [], done.stdout)
        # The fix names a line that the page has: the first marker of the part. The sentence of the part is absent.
        self.assertEqual(self.lines(done, 'docgen-line'), [
            f'{page}:{line}: docgen-line: the page does not have the marker `docgen:end-without`. Fix: put this exact line back '
            f'below line {line} of the page ({opening}), with no line between them: {end}'])
        out = self.scaffold()
        self.assertEqual(page.read_text(), text)
        self.assertIn('skipped  install/index.mdx            the part `docgen:without stage-3-command` has no line '
                      '`{/* docgen:end-without */}`, so the script does not change this part. Continue: `check` prints the line '
                      'to put back.', out.splitlines())
        self.assertNotIn('removed ', out)
        # The line of the fix gives the page of before, and no slot lost a line.
        lines = text.splitlines()
        lines.insert(line, end)
        page.write_text('\n'.join(lines) + '\n')
        self.assertEqual(page.read_text(), original)
        self.assert_passes()

    def test_an_absent_part_with_no_end_line_stays_as_it_is(self):
        # The slot states no command, so the step with the frame is absent: the part is two marker lines.
        self.written()
        page = self.page('install/index.mdx')
        self.write_slot('install/index.mdx', 'stage-3-command', 'The sources state no command that starts the project.')
        self.assertIn('removed  captures/demo/stage3-start.json', self.scaffold())
        original = page.read_text()
        opening, end = '   {/* docgen:with stage-3-command */}', '   {/* docgen:end-with */}'
        self.assertEqual(original.count(f'{opening}\n{end}\n'), 1)
        text = original.replace(f'{opening}\n{end}\n', f'{opening}\n')
        page.write_text(text)
        line = self.line_of('install/index.mdx', opening)
        done = self.check()
        self.assertEqual(self.lines(done, 'stale-part'), [], done.stdout)
        # One finding, and its place is a line of the page. The step and the frame of the template are not on this page.
        self.assertEqual(self.lines(done, 'docgen-line'), [
            f'{page}:{line}: docgen-line: the page does not have the marker `docgen:end-with`. Fix: put this exact line back '
            f'below line {line} of the page ({opening.strip()}), with no line between them: {end.strip()} Put 3 blanks before it.'])
        slots = [slot['id'] for slot in docgen.slots_of(text)]
        out = self.scaffold()
        self.assertEqual(page.read_text(), text)
        self.assertEqual([slot['id'] for slot in docgen.slots_of(page.read_text())], slots)
        self.assertIn('skipped  install/index.mdx            the part `docgen:with stage-3-command` has no line '
                      '`{/* docgen:end-with */}`, so the script does not change this part. Continue: `check` prints the line '
                      'to put back.', out.splitlines())
        # A part of the same slot below it is complete, and it keeps its own lines.
        self.assertIn('{/* docgen:without stage-3-command */}\nThe sources state no command that starts the project.\n'
                      '{/* docgen:end-without */}\n', page.read_text())

    def test_a_part_ends_at_its_own_end_line_only(self):
        text = ('{/* docgen:with a-command */}\nA step.\n\n{/* docgen:slot a-result | 1-9 words | text | Say it. */}\nDone.\n'
                '{/* docgen:end */}\n\n{/* docgen:with b-command */}\nA frame.\n{/* docgen:end-with */}\n'
                '{/* docgen:without b-command */}\n{/* docgen:end-without */}\n{/* docgen:with c-command */}\nNo end.\n')
        parts = [(part['kind'], part['slot'], part['body'], part['end']) for part in docgen.parts_of(text)]
        self.assertEqual(parts, [('with', 'a-command', ['A step.', ''], None), ('with', 'b-command', ['A frame.'], 9),
                                 ('without', 'b-command', [], 11), ('with', 'c-command', ['No end.'], None)])


class NoFactsTest(SharedCase):
    def test_check_says_which_rules_did_not_run_with_no_facts(self):
        # The work files are not tracked. A new clone of the branch has no facts.
        self.written()
        self.edit('index.mdx', ' '.join(['word'] * 30) + '.', 'Run `scripts/absent.py` now. ' + ' '.join(['word'] * 30) + '.')
        self.assertEqual(len(self.lines(self.check(), 'unknown-path')), 1)
        facts = self.site / '.docgen' / 'demo' / 'facts.json'
        facts.unlink()
        done = self.check()
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertEqual(self.lines(done, 'unknown-path'), [])
        lines = done.stdout.splitlines()
        note = ("note     the rules `unknown-path`, `unverified-command` and `unused-fact` did not run, and `docgen-line` did not "
                f"compare the pages with their templates: this checkout has no facts of 'demo' ({facts} is absent). The other "
                "rules ran. This is no finding. `survey` in the project repository writes the facts and records the repository.")
        self.assertIn(note, lines)
        # The line is a part of the summary: it comes after the count of the findings.
        self.assertGreater(lines.index(note), lines.index('0 finding(s) in 7 page(s) of demo'))

    def test_the_docgen_lines_have_a_check_that_needs_no_facts(self):
        self.written()
        (self.site / '.docgen' / 'demo' / 'facts.json').unlink()
        page = self.page('index.mdx')
        text = page.read_text()
        first = self.line_of('index.mdx', 'docgen:slot what-it-is')
        start, end = text.index('{/* docgen:slot what-it-is'), text.index(docgen.SLOT_END)
        # No first line: the text `TODO(docgen:...)` shows on the page, and the end line ends no slot.
        page.write_text(text[:start] + 'TODO(docgen:what-it-is)\n' + text[end:])
        found = self.lines(self.check(), 'docgen-line')
        self.assertEqual(len(found), 2, found)
        self.assertIn(f"{page}:{first}: docgen-line: the text `TODO(docgen:what-it-is)` is in no slot: the first line of the slot "
                      "'what-it-is' is absent, and the page shows this text. Fix: run `survey` in the project repository, then run "
                      "`check` again. It then prints the exact line to put back.", found)
        self.assertIn(f'{page}:{first + 1}: docgen-line: this line `{{/* docgen:end */}}` ends no slot: the first line of its slot '
                      'is absent. Fix: run `survey` in the project repository, then run `check` again. It then prints the exact '
                      'line to put back.', found)
        # No end line: the template gives the exact line with no facts.
        page.write_text(text[:end] + text[end + len(docgen.SLOT_END) + 1:])
        self.assertEqual(self.lines(self.check(), 'docgen-line'), [
            f"{page}:{first}: docgen-line: the slot 'what-it-is' has no line `{{/* docgen:end */}}` below its text. Fix: put this "
            "exact line back directly below the last line of the text of the slot: {/* docgen:end */}"])


# ----- the form of a slot -----

class CommandSlotTest(SharedCase):
    def problems(self, slot, text, path='install/index.mdx'):
        """Write one slot. Return the `problem` lines of `next` and the `slot-form` lines of `check`."""
        line = self.write_slot(path, slot, text)
        done = self.next()
        self.assertIn(f'correct      the slot {slot} (line {line}) of {self.page(path)}', done.stdout.splitlines(), done.stdout)
        problems = [entry.split(None, 1)[1] for entry in done.stdout.splitlines() if entry.startswith('problem ')]
        found = self.lines(self.check(), 'slot-form')
        self.assertEqual([f"{self.page(path)}:{line}: slot-form: the slot '{slot}' has a fault of its form: {problem} Fix: correct "
                          f"the slot. `{self.command('next')}` prints the rules of the form." for problem in problems], found)
        return problems

    def test_a_command_in_backticks_is_a_problem(self):
        self.written()
        self.assertEqual(self.problems('stage-3-command', '`python3 scripts/cli.py build`'),
                         ['the command is in backticks. Remove the backtick before it and the backtick after it.'])
        # A command with a backtick inside it is a command.
        self.write_slot('install/index.mdx', 'stage-3-command', 'python3 scripts/cli.py build `date`')
        self.assertIn('No open slot.', self.next().stdout)

    def test_a_placeholder_in_angle_brackets_is_a_problem(self):
        self.written()
        self.assertEqual(self.problems('stage-4-command', 'python3 scripts/cli.py check --host <your host>'),
                         ['the command holds the placeholder `<your host>`. The command must run as it is. Write the example '
                          'value of the files in its place.'])
        # A redirect is no placeholder, with a blank between two redirects and with no blank.
        for command in ('python3 scripts/cli.py check <in.txt >out.txt', 'sort <in.txt>out.txt', 'sort <data/in>data/out'):
            with self.subTest(command=command):
                self.write_slot('install/index.mdx', 'stage-4-command', command)
                self.assertIn('No open slot.', self.next().stdout)
        # A name in angle brackets with a point is a placeholder still, when no file name follows it.
        self.assertEqual(self.problems('stage-4-command', 'python3 scripts/cli.py check --host <host.name>:80'),
                         ['the command holds the placeholder `<host.name>`. The command must run as it is. Write the example '
                          'value of the files in its place.'])

    def test_a_sentence_in_a_command_slot_gives_the_exact_sentence_of_the_slot(self):
        self.written()
        wanted = ['the slot holds a sentence for "no answer", and it needs one command line. If the files have no answer, write '
                  'exactly this text and no other text: The sources state no test of the install. If the files give the command, '
                  'write that command line.']
        for text in ('The sources state no test for the install.', 'The sources state no test of the install',
                     'the sources state no test of the install.', '`The sources state no test of the install.`',
                     'The sources do not state this.', 'The README states no test.'):
            with self.subTest(text=text):
                self.assertEqual(self.problems('stage-4-command', text), wanted)
        # Short words for "no answer" are no command. Without the problem, the capture spec gets them as its command.
        for text in ('n/a', 'N/A', 'None.', 'Not stated', 'No command.', 'No test.', 'unknown', 'TBD', '-'):
            with self.subTest(text=text):
                self.assertEqual(self.problems('stage-4-command', text), wanted)
        self.write_slot('install/index.mdx', 'stage-4-command', 'python3 scripts/cli.py build')
        # A command slot with no `write:` sentence has no text for this case: the agent stops.
        self.assertEqual(self.problems('example-command', 'The sources do not state this.', 'use/commands/build.mdx'),
                         ['the slot holds a sentence for "no answer", and it needs one command line. If the files have no '
                          'answer, stop. Tell the user the page and the slot. If the files give the command, write that '
                          'command line.'])

    def test_a_sentence_near_to_the_write_sentence_gives_the_exact_sentence_in_each_form(self):
        self.written()
        cases = (('install/index.mdx', 'problems', 'The sources name no known problems.', 'The sources name no known problem.'),
                 ('install/index.mdx', 'stage-2-steps', '1. The sources state no configuration steps.',
                  '1. The sources state no configuration step.'),
                 ('index.mdx', 'limits', 'The sources do not state this.', 'The README states no limit.'))
        for path, slot, text, sentence in cases:
            with self.subTest(slot=slot):
                self.assertEqual(self.problems(slot, text, path),
                                 ['the slot holds a sentence for "no answer", and it is not the exact sentence of this slot for '
                                  f'that case. If the files have no answer, write exactly this text and no other text: {sentence} '
                                  'If the files have an answer, write the answer in the form of the slot.'])
                self.write_slot(path, slot, sentence)
                self.assertIn('No open slot.', self.next().stdout)

    def test_one_fact_with_no_answer_and_one_fact_with_an_answer_pass(self):
        # `next` gives this form for one fact that the files do not state. The text is no copy of the `write:` sentence.
        self.written()
        self.write_slot('use/commands/index.mdx', 'output', 'The sources do not state the output. The exit code is 0.')
        self.assertIn('No open slot.', self.next().stdout)
        self.assertEqual(self.lines(self.check(), 'slot-form'), [])
        # One sentence that is near to the `write:` sentence is a copy with a change.
        self.assertEqual(self.problems('output', 'The sources do not state the output or the exit code.', 'use/commands/index.mdx'),
                         ['the slot holds a sentence for "no answer", and it is not the exact sentence of this slot for that '
                          'case. If the files have no answer, write exactly this text and no other text: The sources do not '
                          'state the output or the exit codes. If the files have an answer, write the answer in the form of the '
                          'slot.'])

    def test_a_docgen_comment_line_in_the_text_of_a_slot_is_a_problem(self):
        # In backticks, the build passes and the page shows the instruction of the script. So the line goes.
        self.written()
        comment = '{/* docgen-slot what-it-is | 30-90 words | text | Say what demo is and what it does. */}'
        words = ' '.join(['word'] * 30) + '.'
        self.assertEqual(self.problems('what-it-is', comment + '\n' + words, 'index.mdx'),
                         [f'the line `{comment[:40]}` is a docgen comment line inside the text of the slot. Remove this line. '
                          'Do not put it in backticks.'])
        # The same line with backticks at its two ends, also with blanks around it: the page shows it as code.
        for line in (f'`{comment}`', f'  `` {comment} ``  '):
            with self.subTest(line=line):
                self.assertEqual(self.problems('what-it-is', line + '\n' + words, 'index.mdx'),
                                 [f'the line `{comment[:40]}` is a docgen comment line in backticks inside the text of the slot. '
                                  'The page shows it as text. Remove this line.'])
        # A docgen comment in backticks inside a sentence is text of the page. So is a line that does not name the slot.
        for text in (f'The script reads the line `{comment}` of a page.\n{words}',
                     f'`{{/* docgen-slot summary | 15-70 words | text | Say how the reader starts the commands. */}}`\n{words}'):
            with self.subTest(text=text):
                self.write_slot('index.mdx', 'what-it-is', text)
                self.assertIn('No open slot.', self.next().stdout)
                self.assertEqual(self.lines(self.check(), 'slot-form'), [])

    def test_a_docgen_comment_in_backticks_is_a_problem_only_when_no_other_text_is_on_its_line(self):
        # The line with backticks at its two ends is a fault. The same comment in backticks inside a sentence is text of
        # the page, also at the start of the sentence.
        self.written()
        comment = '{/* docgen-slot what-it-is | 30-90 words | text | Say what demo is and what it does. */}'
        # The instruction of a slot can hold backticks.
        ticks = '{/* docgen-slot what-it-is | 30-90 words | text | Start with `demo`. Say what it does. */}'
        words = ' '.join(['word'] * 30) + '.'
        # No other word on the line: the comment, the comment with backticks in it, the comment with no end, and the
        # comment with a point after the last backtick.
        for line in (f'`{comment}`', f'`{ticks}`', f'`{comment[:60]}`', f'`{comment}`.'):
            with self.subTest(alone=line):
                self.assertEqual(self.problems('what-it-is', f'{line}\n{words}', 'index.mdx'),
                                 [f'the line `{comment[:40]}` is a docgen comment line in backticks inside the text of the slot. '
                                  'The page shows it as text. Remove this line.'])
        # Other words on the line: the comment at the start, in the middle and at the end of a sentence.
        for line in (f'`{comment}` is the first line of this slot in the page file.',
                     f'`{ticks}` is the first line of this slot in the page file.',
                     f'The line `{comment}` is the first line of this slot.',
                     f'The first line of this slot in the page file is `{comment}`'):
            with self.subTest(sentence=line):
                self.write_slot('index.mdx', 'what-it-is', f'{line}\n{words}')
                out = self.next().stdout
                self.assertEqual(out.splitlines()[0], 'No open slot.', out)
                self.assertNotIn('problem', out)
                self.assertEqual(self.lines(self.check(), 'slot-form'), [])

    def test_a_second_comment_line_in_a_command_slot_is_a_problem(self):
        # The second line `*/}` is text of the page: the comment ends at the first one.
        self.written()
        page = self.page('install/index.mdx')
        slot = self.line_of('install/index.mdx', 'docgen:slot stage-3-command')
        lines = page.read_text().splitlines()
        self.assertEqual(lines[slot:slot + 4], ['{/* docgen:command', 'python3 scripts/cli.py build', '*/}', '{/* docgen:end */}'])
        doubled = lines[:slot] + ['{/* docgen:command', '{/* docgen:command', 'python3 scripts/cli.py build', '*/}', '*/}'] \
            + lines[slot + 3:]
        page.write_text('\n'.join(doubled) + '\n')

        def one_problem(problem):
            self.assertEqual([entry.split(None, 1)[1] for entry in self.next().stdout.splitlines()
                              if entry.startswith('problem ')], [problem])
            found = self.lines(self.check(), 'slot-form')
            self.assertEqual(len(found), 1, found)
            self.assertTrue(found[0].startswith(f"{page}:{slot}: slot-form: the slot 'stage-3-command' has a fault of its "
                                                f'form: {problem}'), found[0])

        # One line at a time: the line number of the second `*/}` changes when the first line goes.
        one_problem(f'the slot has 2 lines `{{/* docgen:command`, and it needs one. Remove line {slot + 2} of the page: it is '
                    'the second line `{/* docgen:command`.')
        del doubled[slot + 1]
        page.write_text('\n'.join(doubled) + '\n')
        one_problem(f'the slot has 2 lines `*/}}`, and it needs one. Remove line {slot + 4} of the page: it is the second line '
                    '`*/}`.')
        # With each second line removed, the slot is as the script wrote it.
        del doubled[slot + 3]
        self.assertEqual(doubled, lines)
        page.write_text('\n'.join(doubled) + '\n')
        self.assertIn('No open slot.', self.next().stdout)

    def test_a_code_block_in_a_command_slot_gives_one_finding(self):
        self.written()
        self.assertEqual(self.problems('stage-3-command', '```sh\npython3 scripts/cli.py build\n```'),
                         ['the command is in a code block. Remove each line with ``` and keep the command line. The command '
                          'has no code block.'])
        done = self.check()
        # The frame of the capture and this slot hold the same command. That is no second place of the command.
        self.assertEqual(self.lines(done, 'command-twice'), [])
        self.assertIn('1 finding(s) in 7 page(s) of demo', done.stdout)

    def test_the_write_sentence_with_no_comment_lines_is_a_problem(self):
        # Without the two lines around it, the page shows the sentence at the place of the slot and in the part below it.
        self.written()
        page = self.page('install/index.mdx')
        line = self.edit('install/index.mdx', '{/* docgen:command\npython3 scripts/cli.py build\n*/}\n{/* docgen:end */}\n\n'
                         '{/* docgen:with stage-3-command', 'The sources state no command that starts the project.\n'
                         '{/* docgen:end */}\n\n{/* docgen:with stage-3-command')
        problem = ('the text of the slot is not between the line `{/* docgen:command` and the line `*/}`. Put these two lines '
                   'back: one above the text and one below it. Use no backticks.')
        self.assertIn(f'problem      {problem}', self.next().stdout.splitlines())
        found = self.lines(self.check(), 'slot-form')
        self.assertEqual(len(found), 1, found)
        self.assertTrue(found[0].startswith(f"{page}:{line - 1}: slot-form: the slot 'stage-3-command' has a fault of its form: "
                                            f"{problem}"), found[0])


class StepsTest(SharedCase):
    def test_the_end_line_of_a_steps_slot_has_the_blanks_of_its_template(self):
        # With the wrong blanks, the end line ends the list of steps at the wrong place, and the build of the site stops.
        self.written()
        page = self.page('install/index.mdx')
        original = page.read_text()
        cases = (('stage-3-steps', '   {/* docgen:end */}\n\n   {/* docgen:with stage-3-command */}',
                  '{/* docgen:end */}\n\n   {/* docgen:with stage-3-command */}', 'no blank', '3 blanks'),
                 ('stage-2-steps', '{/* docgen:end */}\n\n</Steps>\n\n{/* docgen:slot stage-2-result',
                  '   {/* docgen:end */}\n\n</Steps>\n\n{/* docgen:slot stage-2-result', '3 blanks', 'no blank'))
        for slot, old, new, have, want in cases:
            with self.subTest(slot=slot):
                self.edit('install/index.mdx', old, new)
                line = self.line_of('install/index.mdx', f'docgen:slot {slot} ')
                problem = (f'the line `{{/* docgen:end */}}` below the slot has {have} before it, and the script wrote it with '
                           f'{want}. Write that line with exactly {want} before it.')
                done = self.next()
                self.assertIn(f'correct      the slot {slot} (line {line}) of {page}', done.stdout.splitlines())
                self.assertIn(f'problem      {problem}', done.stdout.splitlines())
                done = self.check()
                self.assertEqual(self.lines(done, 'slot-form'), [
                    f"{page}:{line}: slot-form: the slot '{slot}' has a fault of its form: {problem} Fix: correct the slot. "
                    f"`{self.command('next')}` prints the rules of the form."])
                # One finding for the one line.
                self.assertEqual(self.lines(done, 'docgen-line'), [])
                page.write_text(original)
        self.assert_passes()


# ----- capture specs and commands -----

class SpecTest(SharedCase):
    def test_check_finds_a_spec_that_does_not_hold_the_command_of_its_slot(self):
        self.written()
        self.write_slot('install/index.mdx', 'stage-4-command', 'python3 scripts/cli.py check')
        line = self.line_of('install/index.mdx', 'docgen:capture stage4-check')
        done = self.check()
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertEqual(self.lines(done, 'stale-spec'), [
            f"{self.page('install/index.mdx')}:{line}: stale-spec: the capture spec {self.spec('stage4-check')} does not hold the "
            "command of the slot 'stage-4-command', so the frame does not show that command. Fix: run "
            f"`{self.command('scaffold')}`. It copies the command of the slot into the spec."])
        self.assertEqual(self.docgen_run('scaffold', '--project', 'demo').returncode, 0)
        self.assert_passes()


    def test_a_capture_mark_with_no_spec_is_a_finding(self):
        # The page has a capture mark of the template, and the last `scaffold` did not see it: the state does not list
        # the capture, and no spec exists. Without the finding, the commit holds a frame with no spec.
        self.written()
        state_file = self.site / 'docgen' / 'state' / 'demo.json'
        state = json.loads(state_file.read_text())
        del state['captures']['help']
        state_file.write_text(json.dumps(state, indent=1, sort_keys=True) + '\n')
        self.spec('help').unlink()
        line = self.line_of('use/commands/index.mdx', 'docgen:capture help ')
        done = self.check()
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertEqual(self.lines(done, 'stale-spec'), [
            f"{self.page('use/commands/index.mdx')}:{line}: stale-spec: the capture 'help' has no capture spec: the file "
            f"{self.spec('help')} is absent, so its frame shows nothing. Fix: run `{self.command('scaffold')}`. It writes the spec."])
        self.assertIn('1 finding(s) in 7 page(s) of demo', done.stdout)
        out = self.docgen_run('scaffold', '--project', 'demo').stdout
        self.assertIn('wrote    captures/demo/help.json: scripted', out.splitlines())
        self.assert_passes()

    def test_a_spec_that_is_not_valid_json_gives_no_finding_of_this_rule(self):
        # `scaffold` cannot read such a file, so its run is no fix. The tests and the build of the site report the file.
        self.written()
        self.spec('stage3-start').write_text(self.spec('stage3-start').read_text().rstrip().rstrip('}'))
        self.assertEqual(self.lines(self.check(), 'stale-spec'), [])


class TwiceTest(SharedCase):
    def test_blanks_a_prompt_and_a_backslash_make_no_other_command(self):
        self.written()
        page = self.page('install/index.mdx')
        original = page.read_text()
        self.assertEqual(original.count('   mkdir -p out\n'), 3)
        for code in ('   python3  scripts/cli.py   build', '   python3\tscripts/cli.py build', '   $ python3 scripts/cli.py build',
                     '   python3 scripts/cli.py \\\n     build', '   python3 \\\n     scripts/cli.py \\\n     build'):
            with self.subTest(code=code):
                page.write_text(original.replace('   mkdir -p out\n', code + '\n', 1))
                line = self.line_of('install/index.mdx', code.split('\n')[0])
                found = self.lines(self.check(), 'command-twice')
                self.assertEqual(len(found), 1, found)
                self.assertTrue(found[0].startswith(f"{page}:{line}: command-twice: this code block and the frames of the "
                                                    "captures 'stage3-start' and 'stage4-check' show the same command."), found[0])
        # Another command is another command.
        page.write_text(original.replace('   mkdir -p out\n', '   python3 scripts/cli.py build --all\n', 1))
        self.assertEqual(self.lines(self.check(), 'command-twice'), [])


class FactTest(SharedCase):
    SENTENCE = 'The sources state no test of the install.'

    def test_no_test_in_stage_4_is_a_note_while_the_facts_hold_a_test_command(self):
        # The project has unit tests, and no file of it states a test of its install. So the sentence is the true text
        # of the slot. The script does not know what a test command of the facts tests.
        self.written()
        self.write_slot('install/index.mdx', 'stage-4-command', self.SENTENCE)
        self.write_slot('install/index.mdx', 'stage-3-command', 'The sources state no command that starts the project.')
        self.assertEqual(self.docgen_run('scaffold', '--project', 'demo').returncode, 0)
        page = self.page('install/index.mdx')
        line = self.line_of('install/index.mdx', 'docgen:slot stage-4-command')
        done = self.assert_passes()
        # One note names the command of the facts. The slot of the start command has no such rule.
        self.assertEqual(self.lines(done, 'unused-fact'), [
            f"{page}:{line}: note: unused-fact: the slot 'stage-4-command' says that the sources state no test of the install, "
            "and the facts of the survey hold this test command: `python3 -m unittest discover -s tests -q`. If a source file "
            "of this page says that this command tests the install, write the command into the slot in place of the sentence. "
            f"Then correct the slot 'stage-4-result', and run `{self.command('scaffold')}`. If no source file says so, the "
            "sentence is correct, and you change nothing. This is no finding. Put this line into your report."])
        # The summary counts the note in its own line, below the count of the other notes. The exit code stays 0.
        lines = done.stdout.splitlines()
        count = ('1 note(s) with `unused-fact`: a note is no finding. Put each of these lines into your report. The reviewer '
                 'decides if a test command of the facts tests the install.')
        self.assertEqual(lines.index(count), lines.index('0 finding(s) in 7 page(s) of demo') + 2)
        self.assertRegex(lines[lines.index(count) - 1], r'^\d+ note\(s\) with `unverified-command`: a note is no finding\. ')
        # `next` has no problem for the sentence.
        out = self.next().stdout
        self.assertEqual(out.splitlines()[0], 'No open slot.')
        self.assertNotIn('problem', out)
        # The page keeps the sentence, and the stage has no frame and no spec. One more `scaffold` changes no file.
        text = page.read_text()
        self.assertIn('{/* docgen:command\n' + self.SENTENCE + '\n*/}\n', text)
        self.assertIn('{/* docgen:without stage-4-command */}\n' + self.SENTENCE + '\n{/* docgen:end-without */}\n', text)
        self.assertNotIn('stage4-check', text)
        self.assertFalse(self.spec('stage4-check').exists())
        again = self.docgen_run('scaffold', '--project', 'demo').stdout
        self.assertNotIn('updated', again)
        self.assertNotIn('removed', again)
        self.assertEqual(page.read_text(), text)

    def test_the_test_command_of_the_facts_in_stage_4_gives_no_note(self):
        # A source file can give the test command of the facts as the test of the install. The slot then holds it.
        self.written()
        self.write_slot('install/index.mdx', 'stage-4-command', 'python3 -m unittest discover -s tests -q')
        self.assertEqual(self.docgen_run('scaffold', '--project', 'demo').returncode, 0)
        done = self.assert_passes()
        self.assertEqual(self.lines(done, 'unused-fact'), [])
        self.assertNotIn('note(s) with `unused-fact`', done.stdout)


class PathTest(SharedCase):
    FIX = ('Fix: write the path of a file of the project, or a path that a source file of this page states. The top of the page '
           'lists its source files. If no file states the path, remove the sentence or the command that holds it.')

    def unknown(self, word, ref='portable'):
        return f'unknown-path: `{word}` is not a file of the project at {ref}, and no source file of this page holds this path. {self.FIX}'

    def test_check_reads_a_path_in_the_code_block_of_a_step_and_in_a_command(self):
        self.written()
        page = self.page('install/index.mdx')
        original = page.read_text()
        slot = ' '.join(['word'] * 15) + '.'
        cases = (
            # The code block of a step has three blanks before it.
            ('   mkdir -p out\n', '   python3 scripts/absent.py out\n', 'scripts/absent.py'),
            # A command in backticks in a sentence.
            (slot, 'Run `python3 scripts/absent.py --all` first. ' + slot, 'scripts/absent.py'),
            # A path with no extension, and a path below another directory of the project.
            (slot, 'The hook is `scripts/hooks/pre-commit`. ' + slot, 'scripts/hooks/pre-commit'),
            (slot, 'Read `docs/absent` first. ' + slot, 'docs/absent'),
        )
        for old, new, word in cases:
            with self.subTest(new=new):
                page.write_text(original.replace(old, new, 1))
                line = self.line_of('install/index.mdx', new.strip().split('. ')[0])
                self.assertEqual(self.lines(self.check(), 'unknown-path'), [f'{page}:{line}: {self.unknown(word)}'])
        # A file and a directory of the project pass in each of these places.
        page.write_text(original.replace('   mkdir -p out\n', '   python3 scripts/cli.py build docs/setup.md\n', 1)
                        .replace(slot, 'The files are in `scripts/` and in `docs`. Run `python3 scripts/cli.py --help`. ' + slot, 1))
        self.assertEqual(self.lines(self.check(), 'unknown-path'), [])


class NoteTest(SharedCase):
    NOTE = ('note: unverified-command: no file of the project at portable, no saved help text and no command of the facts holds '
            'this command line: `{}`. This is no finding. Put this line into your report.')

    def test_the_command_of_a_command_slot_is_a_note_when_no_source_states_it(self):
        self.written()
        self.write_slot('install/index.mdx', 'stage-3-command', 'python3 scripts/cli.py build')
        self.write_slot('install/index.mdx', 'stage-4-command', 'python3 scripts/cli.py check --strict')
        self.assertEqual(self.docgen_run('scaffold', '--project', 'demo').returncode, 0)
        page = self.page('install/index.mdx')
        line = self.line_of('install/index.mdx', 'python3 scripts/cli.py check --strict')
        found = [entry for entry in self.lines(self.assert_passes(), 'unverified-command') if 'cli.py' in entry]
        self.assertEqual(found, [f"{page}:{line}: {self.NOTE.format('python3 scripts/cli.py check --strict')}"])


    def test_a_diagram_in_a_slot_gives_no_note_and_its_paths_are_read(self):
        # A line of a diagram is no command. A path in a label is a path of the page.
        self.written()
        line = self.edit('develop/workflow.mdx', '\n{/* docgen:end */}\n\n## The roles', '\n\n```mermaid\nflowchart TD\n'
                         '    a["Author"] --> b["scripts/absent.py"]\n```\n{/* docgen:end */}\n\n## The roles') + 2
        done = self.check()
        self.assertEqual([entry for entry in self.lines(done, 'unverified-command') if 'flowchart' in entry or '-->' in entry], [])
        self.assertEqual(len(self.lines(done, 'unknown-path')), 1, done.stdout)
        self.assertIn(f"{self.page('develop/workflow.mdx')}:{line + 2}: unknown-path: `scripts/absent.py`", done.stdout)
        # A label is text for a reader. Two words with a slash between them are no path: only a file name is one.
        page = self.page('develop/workflow.mdx')
        page.write_text(page.read_text().replace('b["scripts/absent.py"]', 'b["Author<br/>docs/tests pass"]'))
        self.assertEqual(self.lines(self.check(), 'unknown-path'), [])


class FrontmatterTest(SharedCase):
    def test_the_finding_names_the_line_that_is_absent_and_the_text_that_the_script_wrote(self):
        self.written()
        page = self.page('install/index.mdx')
        original = page.read_text()
        page.write_text(original.replace('title: Install\n', ''))
        self.assertEqual(self.lines(self.check(), 'frontmatter'), [
            f'{page}:1: frontmatter: the frontmatter has no line `title:` with a text. Fix: put this exact line back as line 2, '
            'directly below the first line `---`: title: Install'])
        description = 'description: "The four stages of the install of demo, from the sources to a checked result."'
        page.write_text(original.replace(description + '\n', ''))
        self.assertEqual(self.lines(self.check(), 'frontmatter'), [
            f'{page}:1: frontmatter: the frontmatter has no line `description:` with a text. Fix: put this exact line back '
            f'directly below the line `title:`: {description}'])
        # A line with the key and no text: a second line with that key stops the build. The fix replaces the line.
        page.write_text(original.replace('title: Install\n', 'title:\n').replace(description + '\n', 'description: \n'))
        self.assertEqual(self.lines(self.check(), 'frontmatter'), [
            f'{page}:2: frontmatter: the frontmatter has no line `title:` with a text. Fix: write this exact line in place of '
            'line 2: title: Install',
            f'{page}:3: frontmatter: the frontmatter has no line `description:` with a text. Fix: write this exact line in place '
            f'of line 3: {description}'])
        page.write_text(original.replace(description + '\n', ''))
        # With no facts, the finding names the line. The script cannot give the text then.
        (self.site / '.docgen' / 'demo' / 'facts.json').unlink()
        self.assertEqual(self.lines(self.check(), 'frontmatter'), [
            f'{page}:1: frontmatter: the frontmatter has no line `description:` with a text. Fix: write the line `description:` '
            'with one short text directly below the line `title:`.'])


# ----- tests with their own project -----

class OwnProjectTest(GateCase):
    """Each test here changes the fixture project, or needs a doc set in another state. So each test makes its own."""

    unknown, FIX, NOTE = PathTest.unknown, PathTest.FIX, NoteTest.NOTE

    def test_a_stage_with_no_command_has_no_finding_for_the_lines_of_its_frame(self):
        # `scaffold` removes the step with the frame while the slot states no command. The template still has those lines.
        self.no_tests()
        self.written()
        for slot, sentence in (('stage-3-command', 'The sources state no command that starts the project.'),
                               ('stage-4-command', 'The sources state no test of the install.')):
            self.write_slot('install/index.mdx', slot, sentence)
        # Before the next `scaffold`, `stale-part` has the fix. `docgen-line` gives no second finding for the same part.
        done = self.check()
        self.assertEqual(self.lines(done, 'docgen-line'), [], done.stdout)
        self.assertEqual(len(self.lines(done, 'stale-part')), 6, done.stdout)
        self.assertEqual(self.docgen_run('scaffold', '--project', 'demo').returncode, 0)
        self.assert_passes()

    def test_a_frame_that_the_template_gives_later_has_a_place_on_the_page_and_needs_its_spec(self):
        # The project has no Python command line at first. The template of the summary page then gives no frame of a help
        # text: the sentence above the frame, the capture mark and the `Capture` line are in one block of the template.
        self.project_file('scripts/cli.py', 'print("no command line")\n')
        self.project_file('scripts/run.sh', '#!/bin/sh\n# Run the thing.\necho run\n')
        self.prepare()
        state_file = self.site / 'docgen' / 'state' / 'demo.json'
        for path in json.loads(state_file.read_text())['pages']:
            base.fill(self.page(path))
        self.assertEqual(self.docgen_run('scaffold', '--project', 'demo').returncode, 0)
        page = self.page('use/commands/index.mdx')
        self.assertNotIn('docgen:capture help', page.read_text())
        self.assertEqual(self.lines(self.check(), 'docgen-line'), [])

        # The project gets its command line. The template now gives the frame, and the page never had these lines.
        self.project_file('scripts/cli.py', base.CLI)
        for words in (('survey', '--repo', '.'), ('plan', '--project', 'demo')):
            self.assertEqual(self.docgen_run(*words).returncode, 0)
        end = self.line_of('use/commands/index.mdx', 'docgen:slot summary') + 2
        self.assertEqual(page.read_text().splitlines()[end - 1], '{/* docgen:end */}')
        mark = '{/* docgen:capture help | 150 | The help text of the command line | run python3 scripts/cli.py --help */}'
        self.assertEqual(self.lines(self.check(), 'docgen-line'), [
            # The place is a line that the page has: the end line of the slot above, with its number.
            f"{page}:{end}: docgen-line: the page does not have the capture mark 'help'. Fix: put this exact line back below "
            f'line {end} of the page ({{/* docgen:end */}}), with one empty line between them: {mark}',
            f"{page}:{end}: docgen-line: the page does not have the `Capture` line of the capture 'demo/help'. Fix: put this "
            f'exact line back below the line ({mark[:70]}), with no line between them: <Capture id="demo/help" />'])
        lines = page.read_text().splitlines()
        page.write_text('\n'.join(lines[:end] + ['', mark, '<Capture id="demo/help" />'] + lines[end:]) + '\n')

        # The two lines are on the page, and no spec exists for the frame. `scaffold` writes it.
        done = self.check()
        self.assertEqual(self.lines(done, 'docgen-line'), [])
        self.assertEqual(self.lines(done, 'stale-spec'), [
            f"{page}:{end + 2}: stale-spec: the capture 'help' has no capture spec: the file {self.spec('help')} is absent, so "
            f"its frame shows nothing. Fix: run `{self.command('scaffold')}`. It writes the spec."])
        self.assertNotEqual(done.returncode, 0)
        out = self.docgen_run('scaffold', '--project', 'demo').stdout
        self.assertIn('wrote    captures/demo/help.json: scripted', out.splitlines())
        self.assertEqual(json.loads(self.spec('help').read_text())['command'], 'python3 scripts/cli.py --help')
        done = self.check()
        self.assertEqual(self.lines(done, 'docgen-line') + self.lines(done, 'stale-spec'), [])

    def test_check_says_so_when_git_cannot_read_the_project_repository(self):
        self.written()
        shutil.move(self.repo, self.tmp / 'moved')
        done = base.run('python3', self.docgen, 'check', '--project', 'demo', cwd=self.tmp)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn('note     the rules `unknown-path` and `unverified-command` did not run: Git cannot read the project '
                      'repository of the last survey. The other rules ran. This is no finding. `survey` in the project repository '
                      'writes the facts and records the repository.', done.stdout.splitlines())

    def test_next_prints_no_rule_about_backticks_for_a_command_slot(self):
        self.prepare()
        page = self.page('install/index.mdx')
        for slot in docgen.slots_of(page.read_text()):
            if slot['id'] == 'stage-3-command':
                break
            base.fill(page, only=slot['id'])
        for path in ('index.mdx',):
            base.fill(self.page(path))
        done = self.next()
        self.assertIn('slot         stage-3-command ', done.stdout)
        self.assertIn('One command line and no other text. Do not put it in backticks.', done.stdout)
        self.assertNotIn('Put each command, path, option and file name in backticks.', done.stdout)
        self.assertIn('rules        Copy the command from one of the files. Do not build a command, and do not change it.',
                      done.stdout.splitlines())
        self.assertIn('             Write no host name, no IP address, no user name, no home path, no internal URL, no password '
                      'and no key.', done.stdout.splitlines())

    def test_check_finds_a_spec_that_waits_for_its_command_and_a_spec_that_is_absent(self):
        # Each slot is written, and no `scaffold` ran after it: each spec of a command slot has no command.
        self.prepare()
        self.fill_all()
        done = self.check()
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertEqual(len(self.lines(done, 'stale-spec')), 4, done.stdout)
        self.assertEqual(self.docgen_run('scaffold', '--project', 'demo').returncode, 0)
        self.spec('cmd-build').unlink()
        found = self.lines(self.check(), 'stale-spec')
        self.assertEqual(len(found), 1, found)
        self.assertIn(f"stale-spec: the capture spec {self.spec('cmd-build')} is absent, so the frame does not show that command.",
                      found[0])

    def test_a_spec_that_a_person_wrote_gives_no_finding(self):
        # `scaffold` does not change such a spec, so its command is not the command of the slot.
        own = {'title': 'A capture of a person', 'order': 600, 'command': 'python3 scripts/cli.py build --own', 'setup': [],
               'mode': 'scripted'}
        self.spec('cmd-build').parent.mkdir(parents=True)
        self.spec('cmd-build').write_text(json.dumps(own, indent=2) + '\n')
        self.written()
        self.assertEqual(json.loads(self.spec('cmd-build').read_text()), own)
        self.assert_passes()

    def test_a_path_that_a_source_file_of_the_page_states_passes(self):
        # A source can name a file that the project makes, or a Git ref. It is no file of the tree.
        self.project_file('docs/setup.md', '# Setup\n\n## Steps\n\nRun `python3 scripts/cli.py build`.\n\n'
                          'The build writes `out/report.txt` and the tag `refs/tags/portable-v0.1.0`.\n'
                          'It reads ./config/local.toml. The copy is in data/cache/index.json.old now.\n')
        self.written()
        slot = ' '.join(['word'] * 15) + '.'
        line = self.edit('install/index.mdx', slot, 'The build writes `out/report.txt` and the tag `refs/tags/portable-v0.1.0`.\n'
                         'It reads `config/local.toml` and `data/cache/index.json`.\nIt writes `out/report.md` too.\n' + slot)
        page = self.page('install/index.mdx')
        # The longer name `index.json.old` of the source is another path. No source states `out/report.md`.
        self.assertEqual(self.lines(self.check(), 'unknown-path'), [
            f"{page}:{line + 1}: {self.unknown('data/cache/index.json')}", f"{page}:{line + 2}: {self.unknown('out/report.md')}"])

    def test_a_command_that_no_source_states_is_a_note_and_no_finding(self):
        # The setup guide is a source file of the Install page. Its command has two blanks at one place.
        self.project_file('docs/setup.md', '# Setup\n\n## Steps\n\nRun `python3 scripts/cli.py build`.\n\n'
                          'Then run `tar -c  -f out.tar out` in the clone.\n')
        self.written()
        page = self.page('install/index.mdx')
        original = page.read_text()
        self.assertEqual(original.count('   mkdir -p out\n'), 3)
        # One command of a source file, one command of the facts, one command that is in no file, with two blanks.
        page.write_text(original.replace('   cp .env.example .env\n', '   tar -c -f out.tar   out\n')
                        .replace('   mkdir -p out\n', '   python3 -m unittest discover -s tests -q\n', 2)
                        .replace('   mkdir -p out\n', '   systemctl  start demo\n'))
        line = self.line_of('install/index.mdx', 'systemctl')
        done = self.assert_passes()
        self.assertEqual(self.lines(done, 'unverified-command'), [f"{page}:{line}: {self.NOTE.format('systemctl start demo')}"])
        # The summary counts the notes, and a note does not change the exit code.
        lines = done.stdout.splitlines()
        count = ('1 note(s) with `unverified-command`: a note is no finding. Put each of these lines into your report. The reviewer '
                 'reads those commands first.')
        self.assertEqual(lines.index(count), lines.index('0 finding(s) in 7 page(s) of demo') + 1)

    def test_the_note_of_stage_4_names_each_test_command_of_the_facts(self):
        # A second manifest gives a second test command. The note then asks for one of them.
        self.project_file('Cargo.toml', '[package]\nname = "demo"\n')
        self.written()
        self.write_slot('install/index.mdx', 'stage-4-command', FactTest.SENTENCE)
        self.assertEqual(self.docgen_run('scaffold', '--project', 'demo').returncode, 0)
        done = self.assert_passes()
        found = self.lines(done, 'unused-fact')
        self.assertEqual(len(found), 1, done.stdout)
        self.assertIn('hold these test commands: `python3 -m unittest discover -s tests -q`, `cargo test`. If a source file of '
                      'this page says that one of these commands tests the install, write that command into the slot in place '
                      'of the sentence. Then correct', found[0])
        # Each kind of note has its own line in the summary, and the exit code stays 0.
        self.assertIn('1 note(s) with `unused-fact`: a note is no finding.', done.stdout)

    def test_a_command_of_a_help_text_or_of_another_file_of_the_project_gives_no_note(self):
        # A file of the project that is no source of the page, and a saved help text.
        self.project_file('Makefile', 'install:\n\tinstall -m 755   scripts/cli.py /usr/local/bin/demo\n')
        self.written()
        (self.site / '.docgen' / 'demo' / 'help').mkdir()
        (self.site / '.docgen' / 'demo' / 'help' / 'scripts__cli.py.txt').write_text('usage: demo render --all [--out DIR]\n')
        page = self.page('install/index.mdx')
        page.write_text(page.read_text().replace('   cp .env.example .env\n', '   install -m 755 scripts/cli.py /usr/local/bin/demo\n')
                        .replace('   mkdir -p out\n', '   demo render --all\n'))
        self.assertEqual(self.lines(self.assert_passes(), 'unverified-command'), [])


if __name__ == '__main__':
    unittest.main()
