"""Tests of scripts/lint_ste.py, the Simplified English lint."""

import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINT = ROOT / 'scripts' / 'lint_ste.py'

spec = importlib.util.spec_from_file_location('lint_ste', LINT)
lint_ste = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lint_ste)


def words(count):
    """A sentence with this number of words."""
    return 'The ' + ' '.join(['word'] * (count - 1)) + '.'


def rules(text):
    return [(line, rule) for line, rule, _ in lint_ste.lint_text(text)]


class CommandTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix='lint-test-'))
        self.addCleanup(shutil.rmtree, self.dir)

    def run_lint(self, *arguments):
        result = subprocess.run([sys.executable, str(LINT)] + list(arguments),
                                capture_output=True, universal_newlines=True)
        return result.returncode, result.stdout + result.stderr

    def test_sentence_of_40_words_is_reported_with_file_and_line(self):
        page = self.dir / 'page.mdx'
        page.write_text('---\ntitle: A page\n---\n\nA short line.\n\n' + words(40) + '\n')
        code, out = self.run_lint(str(page))
        self.assertEqual(code, 0, out)
        self.assertIn(f'{page}:7: sentence-length: 40 words in a description (25 at most)', out)
        self.assertIn('lint: 1 finding(s) in 1 of 1 page(s)', out)
        self.assertIn('Mode: report.', out)

    def test_gate(self):
        bad, good = self.dir / 'bad.md', self.dir / 'good.md'
        bad.write_text(words(26) + '\n')
        good.write_text(words(25) + '\n')
        self.assertEqual(self.run_lint(str(bad))[0], 0)
        code, out = self.run_lint('--gate', str(bad))
        self.assertEqual(code, 1, out)
        self.assertIn('Mode: gate.', out)
        self.assertEqual(self.run_lint('--gate', str(good))[0], 0)

    def test_directory(self):
        (self.dir / 'sub').mkdir()
        (self.dir / 'sub' / 'a.mdx').write_text(words(30) + '\n')
        (self.dir / 'b.md').write_text('Good.\n')
        (self.dir / 'c.txt').write_text(words(30) + '\n')
        code, out = self.run_lint(str(self.dir))
        self.assertIn('lint: 1 finding(s) in 1 of 2 page(s)', out)

    def test_path_that_does_not_exist(self):
        code, out = self.run_lint(str(self.dir / 'absent.md'))
        self.assertEqual(code, 2, out)


class SentenceLengthTest(unittest.TestCase):
    def test_limit_of_a_description(self):
        self.assertEqual(rules(words(25) + '\n'), [])
        self.assertEqual(rules(words(26) + '\n'), [(1, 'sentence-length')])

    def test_limit_of_a_step(self):
        self.assertEqual(rules('1. ' + words(20) + '\n'), [])
        self.assertEqual(rules('1. ' + words(21) + '\n'), [(1, 'sentence-length')])
        self.assertEqual(rules('- ' + words(21) + '\n'), [])

    def test_each_sentence_counts_alone(self):
        self.assertEqual(rules(' '.join([words(20), words(20), words(20)]) + '\n'), [])

    def test_line_of_a_sentence_in_a_paragraph_of_many_lines(self):
        text = 'A first sentence.\nA second one starts here.\n' + words(30) + '\n'
        self.assertEqual(rules(text), [(3, 'sentence-length')])

    def test_text_of_a_step_on_later_lines(self):
        text = '1. Run the build.\n\n   ' + words(21) + '\n\n' + words(21) + '\n'
        self.assertEqual(rules(text), [(3, 'sentence-length')])

    def test_code_is_not_read(self):
        long_code = ' '.join(['word'] * 40)
        self.assertEqual(rules(f'```sh\n{long_code}\n```\n'), [])
        self.assertEqual(rules(f'~~~\n{long_code}\n~~~\n\nGood.\n'), [])
        self.assertEqual(rules(f'Run `{long_code}` now.\n'), [])

    def test_link_counts_as_its_text(self):
        link = '[one](https://example.com/a/very/long/path "with a title of many words here")'
        self.assertEqual(rules(' '.join([link] * 25) + '.\n'), [])
        self.assertEqual(rules(' '.join([link] * 26) + '.\n'), [(1, 'sentence-length')])

    def test_abbreviation_does_not_end_a_sentence(self):
        text = 'Use a tool, e.g. ' + ' '.join(['Word'] * 24) + '.\n'
        self.assertEqual(rules(text), [(1, 'sentence-length')])

    def test_front_matter(self):
        text = f'---\ntitle: Short\ndescription: {words(26)}\nsidebar:\n  order: 1\n---\n\nGood.\n'
        self.assertEqual(rules(text), [(3, 'sentence-length')])
        text = f'---\ntitle: Short\ndescription: >-\n  A first sentence.\n  {words(26)}\n---\n'
        self.assertEqual(rules(text), [(5, 'sentence-length')])

    def test_table_cell_heading_and_attribute(self):
        self.assertEqual(rules(f'| Name | Use |\n| --- | --- |\n| `a` | {words(26)} |\n'), [(3, 'sentence-length')])
        self.assertEqual(rules('## ' + words(26) + '\n'), [(1, 'sentence-length')])
        self.assertEqual(rules(f'<LinkCard title="Install" description="{words(26)}" href="/x/" />\n'),
                         [(1, 'sentence-length')])
        self.assertEqual(rules(f'<LinkCard\n\ttitle="Install"\n\tdescription="{words(26)}"\n/>\n\nGood.\n'),
                         [(3, 'sentence-length')])

    def test_mdx_syntax_is_not_text(self):
        long_name = ', '.join(['name'] * 30)
        text = (f"import {{ {long_name} }} from 'x';\n\n<Planned issue={{7}} />\n\n"
                f"{{/* {words(40)} */}}\n\n<!-- {words(40)} -->\n\nGood.\n")
        self.assertEqual(rules(text), [])

    def test_text_in_a_component(self):
        text = f'<Aside type="note">\n\t{words(26)}\n</Aside>\n'
        self.assertEqual(rules(text), [(2, 'sentence-length')])


class WarningFormTest(unittest.TestCase):
    def test_good_forms(self):
        for text in ('Warning: The command deletes the file.\n',
                     '1. Run the command.\n\n   Warning: The command deletes the file.\n',
                     '> Warning: The command deletes the file.\n',
                     ':::danger\nWarning: The command deletes the file.\n:::\n',
                     'The build prints a warning: the site has no origin.\n',
                     'Warning signs are on each door.\n',
                     'A warning starts with `Warning:` on its own line.\n'):
            with self.subTest(text=text):
                self.assertEqual(rules(text), [])

    def test_other_labels(self):
        for text in ('**Warning:** The command deletes the file.\n', 'WARNING: The command deletes the file.\n',
                     'Caution: The command deletes the file.\n', 'Warning - the command deletes the file.\n',
                     '*Danger!* The command deletes the file.\n', '- warning: the command deletes the file.\n'):
            with self.subTest(text=text):
                self.assertEqual(rules(text), [(1, 'warning-form')])

    def test_warning_that_is_not_on_its_own_line(self):
        self.assertEqual(rules('Run the command. Warning: It deletes the file.\n'), [(1, 'warning-form')])
        self.assertEqual(rules('1. Run the command. Warning: It deletes the file.\n'), [(1, 'warning-form')])

    def test_caution_aside(self):
        self.assertEqual(rules('Text.\n\n:::caution\nThe command deletes the file.\n:::\n'), [(3, 'warning-form')])
        self.assertEqual(rules('<Aside type="danger">\n\tThe command deletes the file.\n</Aside>\n'),
                         [(1, 'warning-form')])
        self.assertEqual(rules(':::note\nThe command reads the file.\n:::\n'), [])

    def test_warning_in_a_step_is_a_description(self):
        text = '1. Run the command.\n   Warning: ' + words(24) + '\n'
        self.assertEqual(rules(text), [])


class ExampleFormTest(unittest.TestCase):
    GOOD = 'The output names a commit. It is not a capture.\n\n```text title="Example"\nok\n```\n'

    def test_good_form(self):
        self.assertEqual(rules(self.GOOD), [])
        self.assertEqual(rules("It is not a capture.\n\n~~~text title='Example'\nok\n~~~\n"), [])

    def test_text_block_without_the_title(self):
        self.assertEqual(rules('It is not a capture.\n\n```text\nok\n```\n'), [(3, 'example-form')])
        self.assertEqual(rules('It is not a capture.\n\n```text title="Output"\nok\n```\n'), [(3, 'example-form')])

    def test_example_block_without_the_sentence(self):
        self.assertEqual(rules('The next block is an example.\n\n```text title="Example"\nok\n```\n'),
                         [(3, 'example-form')])
        self.assertEqual(rules('```text title="Example"\nok\n```\n'), [(1, 'example-form')])

    def test_sentence_must_be_on_the_line_before_the_block(self):
        text = 'It is not a capture.\n\nMore text.\n\n```text title="Example"\nok\n```\n'
        self.assertEqual(rules(text), [(5, 'example-form')])

    def test_other_blocks_are_not_typed_output(self):
        for text in ('```sh\nnpm ci\n```\n', '```\nplain\n```\n', '```md title="notes/plan.md"\n# Plan\n```\n',
                     '````md\n```text\nok\n```\n````\n'):
            self.assertEqual(rules(text), [], text)

    def test_message_names_the_sentence(self):
        findings = lint_ste.lint_text('```text title="Example"\nok\n```\n')
        self.assertIn('It is not a capture.', findings[0][2])


class StepActionsTest(unittest.TestCase):
    def test_one_action(self):
        for text in ('1. Run `npm ci`.\n',
                     '1. Run `npm ci`. The command installs the packages.\n',
                     '1. Run `npm ci`. Check that the command prints no error.\n',
                     '1. Run `npm ci`.\n\n   Make sure that `node_modules` exists.\n',
                     '1. If the build fails, read the log.\n',
                     '1. If the build fails, then read the log.\n',
                     '1. Read the build and test logs.\n',
                     '1. Set the name and type of the field.\n',
                     '1. Run the command.\n   Warning: Stop the service first.\n',
                     '- Copy the file and set the value.\n',
                     'Copy the file and set the value.\n'):
            with self.subTest(text=text):
                self.assertEqual(rules(text), [])

    def test_two_actions_in_one_sentence(self):
        for text in ('1. Copy `.env.example` to `.env` and set `SITE_URL`.\n',
                     '1. Run the build, then open the page.\n',
                     '1. Run the build and then open the page.\n',
                     '1. Copy the file, set the value, and run the build.\n',
                     '1. If the build fails, read the log and run the build again.\n',
                     '1. Select the file; press Enter.\n'):
            with self.subTest(text=text):
                self.assertEqual(rules(text), [(1, 'step-actions')])

    def test_two_instructions_in_one_step(self):
        self.assertEqual(rules('1. Run `npm ci`. Open the page.\n'), [(1, 'step-actions')])
        self.assertEqual(rules('1. Run `npm ci`.\n\n   Open the page.\n2. Close the page.\n'), [(3, 'step-actions')])

    def test_each_step_counts_alone(self):
        self.assertEqual(rules('1. Run `npm ci`.\n2. Open the page.\n3. Close the page.\n'), [])

    def test_steps_in_a_component(self):
        text = '<Steps>\n\n1. Run `npm ci`.\n\n   ```sh\n   npm ci\n   ```\n\n2. Open the page and read it.\n\n</Steps>\n'
        self.assertEqual(rules(text), [(9, 'step-actions')])


class PagesTest(unittest.TestCase):
    def test_message_shows_the_start_of_the_sentence_with_its_code(self):
        findings = lint_ste.lint_text('1. Copy `a.txt` to `b.txt` and set `NAME`.\n')
        self.assertEqual(len(findings), 1)
        self.assertIn('"and set"', findings[0][2])
        self.assertIn('Copy `a.txt` to `b.txt` and set `NAME`.', findings[0][2])


if __name__ == '__main__':
    unittest.main()
