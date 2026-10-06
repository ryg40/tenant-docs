"""Tests of scripts/run_tests.py with small made-up test files in a temporary directory."""

import glob
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / 'scripts' / 'run_tests.py'

spec = importlib.util.spec_from_file_location('run_tests', RUNNER)
run_tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_tests)

# A made-up test file with one test that passes and one test that fails.
FAILING = '''import unittest


class MadeUp(unittest.TestCase):
    def test_good(self):
        self.assertTrue(True)

    def test_bad(self):
        self.assertEqual(1, 2, 'a made-up failure')
'''

# A made-up test file that passes only when the process starts in the directory above the test files,
# and when it writes no bytecode cache.
PLACE = '''import sys
import unittest
from pathlib import Path


class MadeUp(unittest.TestCase):
    def test_place(self):
        self.assertEqual(Path.cwd().resolve(), Path(__file__).resolve().parent.parent)
        self.assertEqual(__name__, 'test_c')
        self.assertTrue(sys.dont_write_bytecode)
'''

# A made-up test file that passes only while the other file runs: each file waits for the mark of the other one.
MEETING = '''import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


class MadeUp(unittest.TestCase):
    def test_the_other_file_runs_at_the_same_time(self):
        (HERE / 'NAME.started').write_text('')
        end = time.monotonic() + 60
        while not (HERE / 'OTHER.started').exists() and time.monotonic() < end:
            time.sleep(0.01)
        self.assertTrue((HERE / 'OTHER.started').exists(), 'the other file did not start')
'''


def passing(count):
    """The text of a made-up test file with a number of tests that pass."""
    tests = '\n'.join(f'    def test_{number}(self):\n        self.assertTrue(True)\n' for number in range(count))
    return f'import unittest\n\n\nclass MadeUp(unittest.TestCase):\n{tests}'


def ids(suite):
    """The id of each test of a suite."""
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from ids(item)
        else:
            yield item.id()


class RunTestsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='run-tests-test-')).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.tests = self.tmp / 'tests'
        self.tests.mkdir()

    def run_tests(self, *words, cwd=None):
        return subprocess.run([sys.executable, str(RUNNER), *words, str(self.tests)], cwd=cwd or self.tmp,
                              capture_output=True, text=True)

    def heads(self, done):
        """The line of each file in the output, without the time."""
        return [line.rsplit(', ', 1)[0] for line in done.stdout.splitlines() if line.startswith('-- ')]

    def test_each_file_passes(self):
        (self.tests / 'test_a.py').write_text(passing(2))
        (self.tests / 'test_b.py').write_text(passing(1))
        (self.tests / 'test_c.py').write_text(PLACE)
        # A file with another name is no test file. The runner does not start it.
        (self.tests / 'helper.py').write_text('raise RuntimeError("the runner started a file that is no test file")\n')
        # The directory of the caller makes no difference.
        done = self.run_tests(cwd=self.tests)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(done.stderr, '')
        self.assertEqual(self.heads(done), ['-- test_a.py: ok, 2 test(s)', '-- test_b.py: ok, 1 test(s)',
                                            '-- test_c.py: ok, 1 test(s)'])
        self.assertRegex(done.stdout.splitlines()[-1], r'^tests: 0 failed file\(s\)\. 3 file\(s\), 4 test\(s\), \d+\.\d s\.$')
        self.assertNotIn('FAIL', done.stdout)
        self.assertFalse((self.tests / '__pycache__').exists())

    def test_one_file_fails(self):
        # The first file fails. Each later file passes, and the output of the later files has more than 30 lines.
        (self.tests / 'test_a.py').write_text(FAILING)
        later = [f'test_{letter}.py' for letter in 'bcdefghi']
        for name in later:
            (self.tests / name).write_text(passing(1))
        done = self.run_tests()
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        # The output of the failed file comes after the output of each file that passes.
        self.assertEqual(self.heads(done), [f'-- {name}: ok, 1 test(s)' for name in later] + ['-- test_a.py: FAIL, 2 test(s)'])
        lines = [line for line in done.stdout.splitlines() if line.strip()]
        self.assertRegex(lines[-2], r'^FAIL  test  test_a\.py  FAIL: test_bad \(test_a\.MadeUp')
        self.assertRegex(lines[-1], r'^tests: 1 failed file\(s\)\. 9 file\(s\), 10 test\(s\), \d+\.\d s\.$')
        # `docgen.py check` prints the last 30 lines of a check that fails. They hold the failed test and its message.
        self.assertGreater(lines.index(next(line for line in lines if line.startswith('-- test_a.py: FAIL'))), 30)
        self.assertIn('AssertionError: 1 != 2 : a made-up failure', lines[-30:])
        self.assertIn('FAILED (failures=1)', lines[-30:])

    def test_no_test_file(self):
        # An empty directory, a directory with no test file, and a directory that does not exist.
        for case in ('empty', 'helper', 'absent'):
            with self.subTest(case):
                if case == 'helper':
                    (self.tests / 'helper.py').write_text(passing(1))
                elif case == 'absent':
                    shutil.rmtree(self.tests)
                done = self.run_tests()
                self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
                self.assertEqual(done.stdout, '')
                self.assertEqual(done.stderr, f'tests: error: {self.tests} has no file test_*.py. Give the directory that '
                                 'holds the test files.\n')

    def test_a_wrong_number_of_jobs_is_a_usage_error(self):
        (self.tests / 'test_a.py').write_text(passing(1))
        done = self.run_tests('--jobs', '0')
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertIn('--jobs needs a number that is 1 or more.', done.stderr)
        self.assertEqual(done.stdout, '')

    def test_two_files_run_at_the_same_time(self):
        for name, other in (('test_a', 'test_b'), ('test_b', 'test_a')):
            (self.tests / f'{name}.py').write_text(MEETING.replace('NAME', name).replace('OTHER', other))
        done = self.run_tests('--jobs', '2')
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertRegex(done.stdout.splitlines()[-1], r'^tests: 0 failed file\(s\)\. 2 file\(s\), 2 test\(s\), ')

    def test_a_process_that_ends_with_no_test_result_is_a_failed_file(self):
        # A file can stop its process: with an exit code, or because a signal ends the process.
        (self.tests / 'test_a.py').write_text('import os\nos._exit(3)\n')
        (self.tests / 'test_b.py').write_text('import os, signal\nos.kill(os.getpid(), signal.SIGKILL)\n')
        (self.tests / 'test_c.py').write_text(passing(1))
        done = self.run_tests()
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertEqual(self.heads(done), ['-- test_c.py: ok, 1 test(s)', '-- test_a.py: FAIL, 0 test(s)',
                                            '-- test_b.py: FAIL, 0 test(s)'])
        self.assertEqual(done.stdout.splitlines()[-3:-1], [
            'FAIL  test  test_a.py  the process ended with the exit code 3, and its output names no failed test',
            'FAIL  test  test_b.py  the process ended with the signal 9, and its output names no failed test'])
        self.assertRegex(done.stdout.splitlines()[-1], r'^tests: 2 failed file\(s\)\. 3 file\(s\), 1 test\(s\), ')

    def test_a_file_with_no_test_is_no_failure(self):
        # As in a run of the full directory in one process. unittest of Python 3.12 and later ends a run with no test
        # with the exit code 5. The second file ends in that way with each version of Python.
        (self.tests / 'test_a.py').write_text('import unittest\n')
        (self.tests / 'test_b.py').write_text('import os, sys\nsys.stderr.write("Ran 0 tests in 0.000s\\n\\nNO TESTS RAN\\n")\n'
                                              'sys.stderr.flush()\nos._exit(5)\n')
        (self.tests / 'test_c.py').write_text(passing(1))
        done = self.run_tests()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.heads(done), ['-- test_a.py: ok, 0 test(s)', '-- test_b.py: ok, 0 test(s)',
                                            '-- test_c.py: ok, 1 test(s)'])
        self.assertRegex(done.stdout.splitlines()[-1], r'^tests: 0 failed file\(s\)\. 3 file\(s\), 1 test\(s\), ')

    def test_the_list_of_the_failed_tests_has_a_limit(self):
        # The list is short, so the last lines of the output hold also the output of a failed file.
        count = run_tests.MAX_NAMED + 3
        tests = '\n'.join(f'    def test_{number:02}(self):\n        self.fail("made-up")\n' for number in range(count))
        (self.tests / 'test_a.py').write_text(f'import unittest\n\n\nclass MadeUp(unittest.TestCase):\n{tests}')
        done = self.run_tests()
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        lines = done.stdout.splitlines()
        named = [line for line in lines if line.startswith('FAIL  test  test_a.py  FAIL: test_')]
        self.assertEqual(len(named), run_tests.MAX_NAMED)
        self.assertEqual(lines[-2], '      and 3 more')

    def test_the_runner_runs_each_test_that_one_process_runs(self):
        # `python3 -m unittest discover -s tests` finds the tests of the site. The files of the runner hold the same tests.
        loader = unittest.TestLoader()
        directory = str(ROOT / 'tests')
        one_process = sorted(ids(loader.discover(directory)))
        by_file = sorted(name for file in run_tests.files_of(directory)
                         for name in ids(loader.discover(directory, pattern=glob.escape(file))))
        self.assertEqual(by_file, one_process)
        self.assertIn('test_run_tests.RunTestsTest.test_each_file_passes', by_file)


if __name__ == '__main__':
    unittest.main()
