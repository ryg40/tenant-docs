"""Tests of scripts/capture.py: the spec fields `ref` and `replace`, the record and the scan of a branch.

The tests start no container. They call the functions that need no Docker.
"""

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

spec = importlib.util.spec_from_file_location('capture', ROOT / 'scripts' / 'capture.py')
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)

WHERE = 'captures/demo/sample.json'
RUN_TIME = {'what': 'the run time', 'match': r'Ran \d+ tests in ([0-9.]+)s', 'with': '<seconds>'}
RELEASE = 'portable/20260103-3c4d5e6'
# A commit ID that no repository has. The test builds it from parts.
COMMIT = 'a1b2c3d' + '4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0'


def scripted(name, ref=None):
    return {'name': name, 'ref': ref}


class ReplaceRuleTests(unittest.TestCase):
    def test_rule_replaces_the_group_and_keeps_the_text_around_it(self):
        rules = capture.replace_rules([RUN_TIME], WHERE)
        raw, replaced = capture.apply_rules('Ran 363 tests in 27.268s\r\n\r\nOK\r\n', rules)
        self.assertEqual(raw, 'Ran 363 tests in <seconds>s\r\n\r\nOK\r\n')
        self.assertEqual(replaced, [{'what': 'the run time', 'with': '<seconds>', 'count': 1}])

    def test_rule_counts_each_value(self):
        rule = {'what': 'the time', 'match': r'"at": "([0-9TZ:-]+)"', 'with': '<UTC time>'}
        raw, replaced = capture.apply_rules(
            '"at": "2026-01-03T10:00:00Z"\n"at": "2026-01-03T10:00:01Z"\n', capture.replace_rules([rule], WHERE))
        self.assertEqual(raw, '"at": "<UTC time>"\n"at": "<UTC time>"\n')
        self.assertEqual(replaced[0]['count'], 2)

    def test_rule_without_a_value_has_the_count_zero(self):
        raw, replaced = capture.apply_rules('OK\n', capture.replace_rules([RUN_TIME], WHERE))
        self.assertEqual(raw, 'OK\n')
        self.assertEqual(replaced[0]['count'], 0)

    def test_two_runs_with_different_values_give_the_same_text(self):
        rules = capture.replace_rules([RUN_TIME], WHERE)
        first, _ = capture.apply_rules('Ran 363 tests in 27.268s\n', rules)
        second, _ = capture.apply_rules('Ran 363 tests in 31.004s\n', rules)
        self.assertEqual(first, second)

    def test_replacement_must_be_a_placeholder(self):
        for text in ('0.000', 'seconds', '<seconds', '<a> and <b>'):
            with self.assertRaises(capture.CaptureError, msg=text):
                capture.replace_rules([{**RUN_TIME, 'with': text}], WHERE)

    def test_match_must_have_one_group(self):
        for match in (r'Ran \d+ tests', r'Ran (\d+) tests in ([0-9.]+)s', r'Ran ('):
            with self.assertRaises(capture.CaptureError, msg=match):
                capture.replace_rules([{**RUN_TIME, 'match': match}], WHERE)

    def test_rule_needs_each_field(self):
        for field in ('what', 'match', 'with'):
            rule = {key: value for key, value in RUN_TIME.items() if key != field}
            with self.assertRaises(capture.CaptureError, msg=field):
                capture.replace_rules([rule], WHERE)
        with self.assertRaises(capture.CaptureError):
            capture.replace_rules(RUN_TIME, WHERE)


class SourceGroupTests(unittest.TestCase):
    def test_release_is_first_and_each_branch_has_one_group(self):
        specs = [scripted('stage1'), scripted('dev-a', 'main'), scripted('cmd'), scripted('dev-b', 'main')]
        groups = capture.source_groups(specs, RELEASE)
        self.assertEqual([(group['kind'], group['ref'], group['full']) for group in groups],
                         [('release', RELEASE, 'refs/tags/' + RELEASE), ('branch', 'main', 'refs/heads/main')])
        self.assertEqual([[item['name'] for item in group['specs']] for group in groups],
                         [['stage1', 'cmd'], ['dev-a', 'dev-b']])

    def test_no_group_without_a_spec(self):
        groups = capture.source_groups([scripted('dev-a', 'main')], RELEASE)
        self.assertEqual([group['kind'] for group in groups], ['branch'])

    def test_release_repository_has_the_branch_main_at_the_tag(self):
        group = capture.source_groups([scripted('stage1')], RELEASE)[0]
        script = capture.prepare_script('demo', group)
        self.assertIn(f"git fetch -q --no-tags /capture/source.bundle refs/tags/{RELEASE}:refs/tags/{RELEASE}", script)
        self.assertIn(f"git update-ref refs/heads/main 'refs/tags/{RELEASE}^{{commit}}'", script)
        self.assertNotIn('git commit', script)

    def test_branch_repository_has_the_branch_as_head(self):
        group = capture.source_groups([scripted('dev-a', 'topic/one')], RELEASE)[0]
        script = capture.prepare_script('demo', group)
        self.assertIn('refs/heads/topic/one:refs/heads/topic/one', script)
        self.assertIn('git symbolic-ref HEAD refs/heads/topic/one', script)


class BranchScanTests(unittest.TestCase):
    def setUp(self):
        self.history = {'dev-a.txt': ('main', {COMMIT})}

    def test_commit_id_of_the_branch_is_a_finding(self):
        for token in (COMMIT, COMMIT[:12], COMMIT[:7]):
            findings = capture.scan({'dev-a.txt': f'ok\nmerge {token} done\n'}, self.history)
            self.assertEqual(findings, ['dev-a.txt:2: a commit ID of the branch main'], token)

    def test_other_text_is_no_finding(self):
        text = f'Ran 366 tests\n{COMMIT[:6]}\n1234567\n{COMMIT[:7]}x\n'
        self.assertEqual(capture.scan({'dev-a.txt': text}, self.history), [])

    def test_file_of_the_release_can_show_its_commit(self):
        self.assertEqual(capture.scan({'cmd-list.txt': f'"kitCommit": "{COMMIT}"\n'}, self.history), [])


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.results = {
            'cmd': {'ref': RELEASE, 'commit': COMMIT, 'code': 0, 'replaced': []},
            'dev-a': {'ref': 'main', 'commit': None, 'code': 1,
                      'replaced': [{'what': 'the run time', 'with': '<seconds>', 'count': 1}]},
        }

    def record(self, old, written, names):
        return json.loads(capture.record_text('demo', old, self.results, written, names))

    def test_record_names_the_ref_and_the_replaced_values(self):
        record = self.record({}, {'cmd', 'dev-a'}, ['dev-a', 'cmd'])
        self.assertEqual(record['project'], 'demo')
        self.assertEqual(list(record['captures']), ['cmd', 'dev-a'])
        self.assertEqual(record['captures']['cmd'], {'ref': RELEASE, 'commit': COMMIT, 'exit': 0, 'replaced': []})
        self.assertEqual(record['captures']['dev-a'], {
            'ref': 'main', 'exit': 1, 'replaced': [{'what': 'the run time', 'with': '<seconds>', 'count': 1}]})

    def test_branch_entry_has_no_commit(self):
        self.assertNotIn('commit', self.record({}, {'dev-a'}, ['dev-a'])['captures']['dev-a'])

    def test_failed_capture_keeps_its_old_entry(self):
        old = {'dev-a': {'ref': 'main', 'exit': 0, 'replaced': []}, 'removed': {'ref': RELEASE}}
        record = self.record(old, {'cmd'}, ['cmd', 'dev-a', 'dev-new'])
        self.assertEqual(record['captures']['dev-a'], old['dev-a'])
        self.assertEqual(list(record['captures']), ['cmd', 'dev-a'])

    def test_same_results_give_the_same_text(self):
        first = capture.record_text('demo', {}, self.results, {'cmd', 'dev-a'}, ['cmd', 'dev-a'])
        second = capture.record_text('demo', {}, self.results, {'dev-a', 'cmd'}, ['dev-a', 'cmd'])
        self.assertEqual(first, second)
        self.assertTrue(first.endswith('}\n'))


class SpecTests(unittest.TestCase):
    def test_each_spec_of_the_repository_loads(self):
        for project in sorted(path.name for path in (ROOT / 'captures').iterdir() if path.is_dir()):
            scripted_specs, manual = capture.load_specs(project)
            self.assertTrue(scripted_specs or manual, project)

    def test_each_dev_capture_of_tenant_pi_runs_on_main(self):
        scripted_specs, manual = capture.load_specs('tenant-pi')
        refs = {item['name']: item['ref'] for item in scripted_specs}
        dev = [name for name in refs if name.startswith('dev-')]
        self.assertTrue(dev)
        self.assertEqual({name for name in refs if refs[name] == 'main'}, set(dev))
        self.assertEqual([name for name in manual if name.startswith('dev-')], [])


if __name__ == '__main__':
    unittest.main()
