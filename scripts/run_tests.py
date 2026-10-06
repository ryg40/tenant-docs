#!/usr/bin/env python3
"""Run the tests of the site: each test file in its own process, some files at the same time.

Usage: scripts/run_tests.py [--jobs <number>] [<directory>]

<directory> holds the test files (default: tests/ of this checkout). Each
file test_*.py of that directory runs in its own process, with this command:

    python3 -m unittest discover -s <directory> -p <file>

Each process starts in the directory above <directory>. So a test has the
same name and the same start directory as in the command for one process:

    python3 -m unittest discover -s tests

That command still runs each test. It takes more time. A file with no
test is no failure, as in that command.

--jobs is the number of files that run at the same time (default: the
number of processors, 8 at most).

Two test files can run at the same time. So each test makes its own
temporary directory, and no test writes to a fixed path. Each process runs
with PYTHONDONTWRITEBYTECODE=1, so no process writes a bytecode cache.

The output, in this order:
  1. The output of each file that passes, in the order of the file names.
  2. The output of each file that fails, in the order of the file names.
  3. One line for each test that fails, with the name of its file. The list
     has 10 lines at most, then one line with the number of the other tests.
  4. One line with the number of files, the number of tests and the time.
So the last lines of the output hold the failed tests.

Exit: 0 each file passes, 1 a file fails, 2 usage error or no test file.
Needs: Python 3.8 or later.
"""

import argparse
import glob
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_JOBS = 8
# The failed tests that the list at the end names. The output of each failed file is above the list.
MAX_NAMED = 10
# The line of unittest with the number of tests of one file.
RAN_RE = re.compile(r'^Ran (\d+) tests? in ', re.M)
# The first line that unittest prints for a test that fails. It follows a line of 70 `=`.
FAILED_RE = re.compile(r'^={70}\n((?:FAIL|ERROR): .+)$', re.M)
# unittest of Python 3.12 and later gives this exit code to a run with no test.
NO_TESTS = 5


def default_jobs():
    """The number of processors that this process can use, MAX_JOBS at most."""
    try:
        count = len(os.sched_getaffinity(0))
    except AttributeError:  # Not each system has this function.
        count = os.cpu_count() or 1
    return max(1, min(count, MAX_JOBS))


def files_of(directory):
    """The names of the test files of one directory, in the order of the names."""
    return sorted(path.name for path in Path(directory).glob('test_*.py') if path.is_file())


def run_file(directory, name):
    """Run one test file in its own process. Return its result."""
    start = time.monotonic()
    done = subprocess.run(
        [sys.executable or 'python3', '-m', 'unittest', 'discover', '-s', str(directory), '-p', glob.escape(name)],
        cwd=directory.parent, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace')
    ran = RAN_RE.findall(done.stdout)
    tests = int(ran[-1]) if ran else 0
    # A file with no test is no failure, as in a run of the full directory in one process.
    passed = done.returncode == 0 or (done.returncode == NO_TESTS and bool(ran) and tests == 0)
    return {'name': name, 'passed': passed, 'code': done.returncode, 'tests': tests, 'output': done.stdout,
            'seconds': time.monotonic() - start}


def show(result):
    """Print one line with the name, the result and the time of one file, then the output of the file."""
    state = 'ok' if result['passed'] else 'FAIL'
    print(f"-- {result['name']}: {state}, {result['tests']} test(s), {result['seconds']:.1f} s")
    if result['output'].strip():
        print(result['output'].strip('\n'))
    sys.stdout.flush()


def failures_of(result):
    """One text for each failed test of a failed file. A file that names no failed test gets one text for its process."""
    named = FAILED_RE.findall(result['output'])
    if named:
        return named
    code = result['code']
    ended = f'signal {-code}' if code < 0 else f'exit code {code}'
    return [f'the process ended with the {ended}, and its output names no failed test']


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run each test file in its own process, some files at the same time.',
                                     epilog='Exit: 0 each file passes, 1 a file fails, 2 usage error or no test file.')
    parser.add_argument('--jobs', metavar='NUMBER', type=int, default=default_jobs(),
                        help=f'the number of files that run at the same time (default: the number of processors, '
                             f'{MAX_JOBS} at most)')
    parser.add_argument('directory', nargs='?', default=str(ROOT / 'tests'),
                        help='the directory with the files test_*.py (default: tests/)')
    args = parser.parse_args(argv)
    if args.jobs < 1:
        parser.error('--jobs needs a number that is 1 or more.')

    directory = Path(args.directory).resolve()
    names = files_of(directory)
    if not names:
        print(f'tests: error: {args.directory} has no file test_*.py. Give the directory that holds the test files.',
              file=sys.stderr)
        return 2

    start = time.monotonic()
    results, shown = {}, 0
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        running = {pool.submit(run_file, directory, name): name for name in names}
        for ended in as_completed(running):
            results[running[ended]] = ended.result()
            # A file shows when each file before it has its result. The output of a failed file waits for the end.
            while shown < len(names) and names[shown] in results:
                if results[names[shown]]['passed']:
                    show(results[names[shown]])
                shown += 1
    failed = [results[name] for name in names if not results[name]['passed']]
    for result in failed:
        show(result)
    named = [f"FAIL  test  {result['name']}  {text}" for result in failed for text in failures_of(result)]
    for line in named[:MAX_NAMED]:
        print(line)
    if len(named) > MAX_NAMED:
        print(f'      and {len(named) - MAX_NAMED} more')
    tests = sum(result['tests'] for result in results.values())
    print(f'tests: {len(failed)} failed file(s). {len(names)} file(s), {tests} test(s), {time.monotonic() - start:.1f} s.')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
